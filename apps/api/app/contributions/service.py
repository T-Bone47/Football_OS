"""Contribution Service handling temporal queries, calculation, caching, and persistence (Phase 3.1).
"""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.models import CanonicalAction
from app.actions.normalizer import normalize_match_event, normalize_player_match_stats
from app.contributions.calculator import compute_player_contribution_metrics
from app.contributions.models import PlayerContributionSnapshot
from app.contributions.schemas import ContributionDimensionItem, PlayerContributionResponse
from app.db.models.canonical import Match, MatchEvent, Player, PlayerMatchStats
from app.roles.registry import map_position_to_group


CALCULATION_VERSION = "1.0"
FEATURE_SET_VERSION = "contribution_v1"



async def _provider_for_snapshot(session, snapshot_id) -> str:
    """Name of the data source behind a snapshot, or UNKNOWN_SOURCE when the
    event has no snapshot (its origin cannot be shown)."""
    if snapshot_id is None:
        return "UNKNOWN_SOURCE"
    from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
    row = await session.execute(
        select(DataSource.name)
        .join(IngestionRun, IngestionRun.data_source_id == DataSource.id)
        .join(DataSnapshot, DataSnapshot.ingestion_run_id == IngestionRun.id)
        .where(DataSnapshot.id == snapshot_id)
    )
    return row.scalar_one_or_none() or "UNKNOWN_SOURCE"

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

        # 4. Compute metrics using pure deterministic calculator
        calc_result = compute_player_contribution_metrics(stats_list, pos_group)

        dimensions_dict = {k: v.model_dump() for k, v in calc_result["dimensions"].items()}

        provenance = {
            "calculation_version": CALCULATION_VERSION,
            "feature_set_version": FEATURE_SET_VERSION,
            "match_count": len(stats_list),
            "as_of": cutoff.isoformat(),
            "source_snapshots": [str(s.snapshot_id) for s in stats_list if s.snapshot_id],
        }

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
            provider_by_snapshot: dict = {}
            for ev in ev_res.scalars().all():
                # The action carries the provider that actually produced the
                # event (snapshot -> ingestion run -> data source).
                if ev.snapshot_id not in provider_by_snapshot:
                    provider_by_snapshot[ev.snapshot_id] = await _provider_for_snapshot(self.session, ev.snapshot_id)
                normalized_ev = normalize_match_event(ev, provider=provider_by_snapshot[ev.snapshot_id])
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
