"""Contribution Service handling temporal queries, calculation, caching, and persistence (Phase 3.1).
"""
from __future__ import annotations

import datetime
import uuid
from types import SimpleNamespace
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.models import CanonicalAction
from app.actions.normalizer import normalize_match_event, normalize_player_match_stats
from app.contributions.calculator import compute_player_contribution_metrics
from app.contributions.models import PlayerContributionSnapshot
from app.contributions.schemas import ContributionDimensionItem, PlayerContributionResponse
from app.db.models.canonical import (
    Match,
    MatchEvent,
    Player,
    PlayerMatchStats,
    PlayerSeasonStats,
)
from app.roles.registry import map_position_to_group


CALCULATION_VERSION = "1.0"
FEATURE_SET_VERSION = "contribution_v1"


class ContributionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_player_contribution_profile(
        self,
        player_id: uuid.UUID,
        as_of: datetime.datetime | None = None,
    ) -> PlayerContributionResponse:
        """Retrieves or computes the temporal-safe contribution profile for a player."""
        cutoff = as_of or datetime.datetime.now(datetime.timezone.utc)

        # 1. Fetch Player entity
        p_res = await self.session.execute(select(Player).where(Player.id == player_id))
        player = p_res.scalar_one_or_none()
        if not player:
            raise ValueError(f"Player {player_id} not found")

        pos_group = map_position_to_group(player.primary_position).value

        # 2. Check for existing snapshot
        snap_res = await self.session.execute(
            select(PlayerContributionSnapshot).where(
                PlayerContributionSnapshot.player_id == player_id,
                PlayerContributionSnapshot.as_of == cutoff,
                PlayerContributionSnapshot.calculation_version == CALCULATION_VERSION,
            )
        )
        existing = snap_res.scalar_one_or_none()
        if existing:
            dims: dict[str, ContributionDimensionItem] = {}
            for k, d in (existing.dimension_scores or {}).items():
                dims[k] = ContributionDimensionItem(**d)
            return PlayerContributionResponse(
                player_id=existing.player_id,
                player_name=player.name,
                as_of=existing.as_of,
                position_group=existing.position_group,
                sample_minutes=existing.sample_minutes,
                sample_matches=existing.sample_matches,
                confidence=existing.confidence,
                contribution_status=existing.contribution_status,
                dimensions=dims,
                raw_metrics=existing.raw_metrics,
                strengths=existing.strengths,
                weaknesses=existing.weaknesses,
                calculation_version=existing.calculation_version,
                provenance=existing.provenance,
            )

        # 3. Query historical match performance strictly respecting temporal safety (match.date < cutoff)
        stmt = (
            select(PlayerMatchStats)
            .join(Match, PlayerMatchStats.match_id == Match.id)
            .where(
                PlayerMatchStats.player_id == player_id,
                Match.date < cutoff,
            )
            .order_by(desc(Match.date))
        )
        res = await self.session.execute(stmt)
        stats_list = list(res.scalars().all())

        # 3b. No per-match rows do not mean no evidence. The provider supplies
        # season aggregates for every indexed player, so fall back to the
        # season window and label it as such instead of reporting zero minutes.
        season_row: PlayerSeasonStats | None = None
        stats_list, season_row = await self._with_season_fallback(player_id, stats_list)
        window = "season_aggregate" if season_row is not None else "match_log"

        # 4. Compute metrics using pure deterministic calculator
        calc_result = compute_player_contribution_metrics(stats_list, pos_group)
        if season_row is not None:
            appearances = max(int(season_row.appearances or 0), 1)
            calc_result["sample_matches"] = appearances
            calc_result["raw_metrics"]["matches"] = float(appearances)

        dimensions_dict = {k: v.model_dump() for k, v in calc_result["dimensions"].items()}

        provenance = {
            "calculation_version": CALCULATION_VERSION,
            "feature_set_version": FEATURE_SET_VERSION,
            "match_count": len(stats_list),
            "window": window,
            "as_of": cutoff.isoformat(),
            "source_snapshots": [
                str(s.snapshot_id) for s in stats_list if getattr(s, "snapshot_id", None)
            ],
        }
        if season_row is not None:
            provenance["source"] = "player_season_stats"
            provenance["season_stats_id"] = str(season_row.id)
            provenance["season_minutes"] = int(season_row.minutes or 0)

        # 5. Persist snapshot
        snapshot = PlayerContributionSnapshot(
            id=uuid.uuid4(),
            player_id=player_id,
            as_of=cutoff,
            feature_set_version=FEATURE_SET_VERSION,
            calculation_version=CALCULATION_VERSION,
            position_group=pos_group,
            sample_minutes=calc_result["sample_minutes"],
            sample_matches=calc_result["sample_matches"],
            confidence=calc_result["confidence"],
            contribution_status=calc_result["contribution_status"],
            dimension_scores=dimensions_dict,
            raw_metrics=calc_result["raw_metrics"],
            strengths=calc_result["strengths"],
            weaknesses=calc_result["weaknesses"],
            provenance=provenance,
        )
        self.session.add(snapshot)
        await self.session.flush()

        return PlayerContributionResponse(
            player_id=player_id,
            player_name=player.name,
            as_of=cutoff,
            position_group=pos_group,
            sample_minutes=calc_result["sample_minutes"],
            sample_matches=calc_result["sample_matches"],
            confidence=calc_result["confidence"],
            contribution_status=calc_result["contribution_status"],
            dimensions=calc_result["dimensions"],
            raw_metrics=calc_result["raw_metrics"],
            strengths=calc_result["strengths"],
            weaknesses=calc_result["weaknesses"],
            calculation_version=CALCULATION_VERSION,
            provenance=provenance,
        )

    async def _with_season_fallback(
        self,
        player_id: uuid.UUID,
        stats_list: list[PlayerMatchStats],
    ) -> tuple[list[Any], PlayerSeasonStats | None]:
        """Returns match rows, or one aggregate row built from the player's latest season.

        The aggregate is a real provider total (minutes, appearances and
        counting stats) expressed once so the same deterministic calculator can
        run on it. Nothing is imputed: absent provider fields stay at zero in
        the total, and the response is labelled ``season_aggregate``.
        """
        if stats_list:
            return stats_list, None

        stmt = (
            select(PlayerSeasonStats)
            .where(
                PlayerSeasonStats.player_id == player_id,
                PlayerSeasonStats.minutes > 0,
            )
            .order_by(desc(PlayerSeasonStats.minutes))
            .limit(1)
        )
        season_row = (await self.session.execute(stmt)).scalar_one_or_none()
        if season_row is None:
            return stats_list, None
        return [self._season_aggregate(season_row)], season_row

    @staticmethod
    def _season_aggregate(row: PlayerSeasonStats) -> Any:
        """Adapter exposing season totals through the per-match stats contract."""
        raw = row.raw_stats or {}
        goals = raw.get("goals") or {}
        shots = raw.get("shots") or {}
        passes = raw.get("passes") or {}
        tackles = raw.get("tackles") or {}
        duels = raw.get("duels") or {}
        dribbles = raw.get("dribbles") or {}
        fouls = raw.get("fouls") or {}

        def _num(value: Any) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _int(value: Any) -> int:
            parsed = _num(value)
            return int(parsed) if parsed is not None else 0

        return SimpleNamespace(
            minutes=int(row.minutes or 0),
            goals=int(row.goals or 0),
            assists=int(row.assists or 0),
            shots_total=_int(shots.get("total")),
            shots_on_target=_int(shots.get("on")),
            passes_total=_int(passes.get("total")),
            passes_key=_int(passes.get("key")),
            tackles_total=_int(tackles.get("total")),
            interceptions=_int(tackles.get("interceptions")),
            blocks=_int(tackles.get("blocks")),
            duels_total=_int(duels.get("total")),
            duels_won=_int(duels.get("won")),
            dribbles_attempts=_int(dribbles.get("attempts")),
            dribbles_success=_int(dribbles.get("success")),
            fouls_committed=_int(fouls.get("committed")),
            fouls_drawn=_int(fouls.get("drawn")),
            saves=_int(goals.get("saves")),
            goals_conceded=_int(goals.get("conceded") or row.conceded),
            pass_accuracy=_num(passes.get("accuracy")),
            snapshot_id=row.snapshot_id,
        )

    async def get_player_actions(
        self,
        player_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[CanonicalAction]]:
        """Queries canonical actions for a player with pagination.
        If canonical_actions table is unpopulated for this player, synchronizes from raw records on the fly.
        """
        # Check action count
        c_res = await self.session.execute(
            select(CanonicalAction).where(CanonicalAction.player_id == player_id)
        )
        actions = list(c_res.scalars().all())

        if not actions:
            # Sync actions from PlayerMatchStats and MatchEvent
            pms_res = await self.session.execute(
                select(PlayerMatchStats).where(PlayerMatchStats.player_id == player_id)
            )
            for pms in pms_res.scalars().all():
                normalized = normalize_player_match_stats(pms)
                for act in normalized:
                    self.session.add(act)

            ev_res = await self.session.execute(
                select(MatchEvent).where(
                    (MatchEvent.player_id == player_id) | (MatchEvent.assist_player_id == player_id)
                )
            )
            for ev in ev_res.scalars().all():
                normalized_ev = normalize_match_event(ev)
                for act in normalized_ev:
                    if act.player_id == player_id:
                        self.session.add(act)

            await self.session.flush()

            # Re-query
            c_res = await self.session.execute(
                select(CanonicalAction)
                .where(CanonicalAction.player_id == player_id)
                .order_by(desc(CanonicalAction.minute))
            )
            actions = list(c_res.scalars().all())

        total = len(actions)
        paginated = actions[offset : offset + limit]
        return total, paginated
