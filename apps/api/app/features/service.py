"""Feature engineering service orchestrator (Phase 2 Slice 1).
Coordinates historical pre-match queries, feature computation, persistence,
and model-ready dataset extraction while strictly preventing temporal leakage.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import (
    Club,
    FeatureSnapshot,
    Match,
    MatchTeam,
    Player,
    PlayerMatchStats,
)
from app.features.calculator import (
    calculate_opponent_strength_baseline,
    calculate_player_features,
    calculate_rest_days,
    calculate_team_features,
)


class FeatureService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def compute_player_features(
        self,
        player_id: uuid.UUID,
        as_of: datetime,
        match_id: uuid.UUID | None = None,
        save: bool = True,
        calculation_version: str = "1.0.0",
        feature_set: str = "player_match_v1",
    ) -> FeatureSnapshot:
        """Computes player analytical features strictly before as_of and optionally saves snapshot."""
        # 1. Resolve player position
        player_stmt = select(Player).where(Player.id == player_id)
        player = (await self._session.execute(player_stmt)).scalar_one_or_none()
        if player is None:
            raise ValueError(f"Player {player_id} not found")

        position = player.primary_position

        # 2. Query historical PlayerMatchStats strictly before as_of
        stmt = (
            select(PlayerMatchStats)
            .join(Match, PlayerMatchStats.match_id == Match.id)
            .where(
                PlayerMatchStats.player_id == player_id,
                Match.date < as_of,
            )
            .options(selectinload(PlayerMatchStats.match))
            .order_by(Match.date.asc())
        )
        history = (await self._session.execute(stmt)).scalars().all()

        # Update position from history if available
        if not position:
            for rec in reversed(history):
                if rec.position:
                    position = rec.position
                    break

        # 3. Compute pure features
        match_record = None
        season_id = None
        competition_id = None
        if match_id is not None:
            m_stmt = (
                select(Match)
                .where(Match.id == match_id)
                .options(selectinload(Match.competition_season))
            )
            match_record = (await self._session.execute(m_stmt)).scalar_one_or_none()
            if match_record and match_record.competition_season:
                season_id = match_record.competition_season.season_id
                competition_id = match_record.competition_season.competition_id

        calculated_features = calculate_player_features(
            history=history,
            as_of=as_of,
            position=position,
            season_id=season_id,
        )

        provenance = {
            "source_entity": "player_match_stats",
            "source_match_ids": [str(h.match_id) for h in history],
            "record_count": len(history),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "calculation_version": calculation_version,
            "as_of": as_of.isoformat(),
        }

        snapshot = None
        if save:
            # Check for existing snapshot to preserve idempotency
            existing_stmt = select(FeatureSnapshot).where(
                FeatureSnapshot.entity_type == "player",
                FeatureSnapshot.entity_id == player_id,
                FeatureSnapshot.feature_set == feature_set,
                FeatureSnapshot.calculation_version == calculation_version,
                FeatureSnapshot.as_of == as_of,
            )
            snapshot = (await self._session.execute(existing_stmt)).scalar_one_or_none()
            if snapshot is not None:
                snapshot.features = calculated_features
                snapshot.provenance = provenance
                snapshot.match_id = match_id
                snapshot.season_id = season_id
                snapshot.competition_id = competition_id
            else:
                snapshot = FeatureSnapshot(
                    entity_type="player",
                    entity_id=player_id,
                    match_id=match_id,
                    feature_set=feature_set,
                    calculation_version=calculation_version,
                    as_of=as_of,
                    season_id=season_id,
                    competition_id=competition_id,
                    features=calculated_features,
                    provenance=provenance,
                )
                self._session.add(snapshot)

            await self._session.flush()
        else:
            snapshot = FeatureSnapshot(
                entity_type="player",
                entity_id=player_id,
                match_id=match_id,
                feature_set=feature_set,
                calculation_version=calculation_version,
                as_of=as_of,
                season_id=season_id,
                competition_id=competition_id,
                features=calculated_features,
                provenance=provenance,
            )

        return snapshot

    async def compute_team_features(
        self,
        club_id: uuid.UUID,
        as_of: datetime,
        match_id: uuid.UUID | None = None,
        save: bool = True,
        calculation_version: str = "1.0.0",
        feature_set: str = "team_match_v1",
    ) -> FeatureSnapshot:
        """Computes team analytical features strictly before as_of."""
        club_stmt = select(Club).where(Club.id == club_id)
        club = (await self._session.execute(club_stmt)).scalar_one_or_none()
        if club is None:
            raise ValueError(f"Club {club_id} not found")

        stmt = (
            select(MatchTeam)
            .join(Match, MatchTeam.match_id == Match.id)
            .where(
                MatchTeam.club_id == club_id,
                Match.date < as_of,
            )
            .options(selectinload(MatchTeam.match))
            .order_by(Match.date.asc())
        )
        history = (await self._session.execute(stmt)).scalars().all()

        match_record = None
        season_id = None
        competition_id = None
        if match_id is not None:
            m_stmt = (
                select(Match)
                .where(Match.id == match_id)
                .options(selectinload(Match.competition_season))
            )
            match_record = (await self._session.execute(m_stmt)).scalar_one_or_none()
            if match_record and match_record.competition_season:
                season_id = match_record.competition_season.season_id
                competition_id = match_record.competition_season.competition_id

        calculated_features = calculate_team_features(
            history=history,
            as_of=as_of,
            season_id=season_id,
        )

        provenance = {
            "source_entity": "match_teams",
            "source_match_ids": [str(h.match_id) for h in history],
            "record_count": len(history),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "calculation_version": calculation_version,
            "as_of": as_of.isoformat(),
        }

        snapshot = None
        if save:
            existing_stmt = select(FeatureSnapshot).where(
                FeatureSnapshot.entity_type == "team",
                FeatureSnapshot.entity_id == club_id,
                FeatureSnapshot.feature_set == feature_set,
                FeatureSnapshot.calculation_version == calculation_version,
                FeatureSnapshot.as_of == as_of,
            )
            snapshot = (await self._session.execute(existing_stmt)).scalar_one_or_none()
            if snapshot is not None:
                snapshot.features = calculated_features
                snapshot.provenance = provenance
                snapshot.match_id = match_id
                snapshot.season_id = season_id
                snapshot.competition_id = competition_id
            else:
                snapshot = FeatureSnapshot(
                    entity_type="team",
                    entity_id=club_id,
                    match_id=match_id,
                    feature_set=feature_set,
                    calculation_version=calculation_version,
                    as_of=as_of,
                    season_id=season_id,
                    competition_id=competition_id,
                    features=calculated_features,
                    provenance=provenance,
                )
                self._session.add(snapshot)

            await self._session.flush()
        else:
            snapshot = FeatureSnapshot(
                entity_type="team",
                entity_id=club_id,
                match_id=match_id,
                feature_set=feature_set,
                calculation_version=calculation_version,
                as_of=as_of,
                season_id=season_id,
                competition_id=competition_id,
                features=calculated_features,
                provenance=provenance,
            )

        return snapshot

    async def compute_match_features(
        self,
        match_id: uuid.UUID,
        as_of: datetime | None = None,
        save: bool = True,
        calculation_version: str = "1.0.0",
    ) -> dict[str, Any]:
        """Computes pre-match context, home team features, and away team features for a target match."""
        m_stmt = (
            select(Match)
            .where(Match.id == match_id)
            .options(
                selectinload(Match.teams),
                selectinload(Match.competition_season),
            )
        )
        match = (await self._session.execute(m_stmt)).scalar_one_or_none()
        if match is None:
            raise ValueError(f"Match {match_id} not found")

        match_date = as_of or match.date
        home_mt = next((t for t in match.teams if t.is_home), None)
        away_mt = next((t for t in match.teams if not t.is_home), None)

        if home_mt is None or away_mt is None:
            raise ValueError(f"Match {match_id} does not have both home and away teams")

        home_club_id = home_mt.club_id
        away_club_id = away_mt.club_id

        # 1. Compute team features
        home_snapshot = await self.compute_team_features(
            club_id=home_club_id,
            as_of=match_date,
            match_id=match_id,
            save=save,
            calculation_version=calculation_version,
        )
        away_snapshot = await self.compute_team_features(
            club_id=away_club_id,
            as_of=match_date,
            match_id=match_id,
            save=save,
            calculation_version=calculation_version,
        )

        # 2. Query previous matches for rest day computation
        async def get_prev_match(club_id: uuid.UUID) -> Match | None:
            q = (
                select(Match)
                .join(MatchTeam, Match.id == MatchTeam.match_id)
                .where(
                    MatchTeam.club_id == club_id,
                    Match.date < match_date,
                )
                .order_by(Match.date.desc())
                .limit(1)
            )
            return (await self._session.execute(q)).scalar_one_or_none()

        home_prev = await get_prev_match(home_club_id)
        away_prev = await get_prev_match(away_club_id)

        home_rest = calculate_rest_days(match_date, home_prev.date if home_prev else None)
        away_rest = calculate_rest_days(match_date, away_prev.date if away_prev else None)

        # 3. Query opponent history for strength baselines
        async def get_team_history(club_id: uuid.UUID) -> list[MatchTeam]:
            q = (
                select(MatchTeam)
                .join(Match, MatchTeam.match_id == Match.id)
                .where(
                    MatchTeam.club_id == club_id,
                    Match.date < match_date,
                )
                .options(selectinload(MatchTeam.match))
                .order_by(Match.date.asc())
            )
            return list((await self._session.execute(q)).scalars().all())

        home_history = await get_team_history(home_club_id)
        away_history = await get_team_history(away_club_id)

        home_opp_strength = calculate_opponent_strength_baseline(away_history, match_date)
        away_opp_strength = calculate_opponent_strength_baseline(home_history, match_date)

        match_context = {
            "home_days_since_previous_match": home_rest,
            "away_days_since_previous_match": away_rest,
            "home_team_strength_baseline_points_per_match": home_snapshot.features.get("points_per_match_last_5"),
            "home_team_strength_baseline_goal_diff": home_snapshot.features.get("goal_difference_last_5"),
            "away_team_strength_baseline_points_per_match": away_snapshot.features.get("points_per_match_last_5"),
            "away_team_strength_baseline_goal_diff": away_snapshot.features.get("goal_difference_last_5"),
            "home_opponent_strength": home_opp_strength,
            "away_opponent_strength": away_opp_strength,
        }

        # Save match snapshot
        match_features_payload = {
            "home_club_id": str(home_club_id),
            "away_club_id": str(away_club_id),
            "home_rest_days": home_rest,
            "away_rest_days": away_rest,
            **home_opp_strength,
            **away_opp_strength,
        }

        match_snapshot = None
        if save:
            existing_stmt = select(FeatureSnapshot).where(
                FeatureSnapshot.entity_type == "match",
                FeatureSnapshot.entity_id == match_id,
                FeatureSnapshot.feature_set == "match_context_v1",
                FeatureSnapshot.calculation_version == calculation_version,
                FeatureSnapshot.as_of == match_date,
            )
            match_snapshot = (await self._session.execute(existing_stmt)).scalar_one_or_none()
            if match_snapshot is not None:
                match_snapshot.features = match_features_payload
                match_snapshot.provenance = {
                    "source_entity": "matches",
                    "calculated_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                season_id = match.competition_season.season_id if match.competition_season else None
                competition_id = match.competition_season.competition_id if match.competition_season else None
                match_snapshot = FeatureSnapshot(
                    entity_type="match",
                    entity_id=match_id,
                    match_id=match_id,
                    feature_set="match_context_v1",
                    calculation_version=calculation_version,
                    as_of=match_date,
                    season_id=season_id,
                    competition_id=competition_id,
                    features=match_features_payload,
                    provenance={
                        "source_entity": "matches",
                        "calculated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                self._session.add(match_snapshot)

            await self._session.flush()

        return {
            "match_id": match_id,
            "as_of": match_date,
            "home_club_id": home_club_id,
            "away_club_id": away_club_id,
            "home_features": home_snapshot.features,
            "away_features": away_snapshot.features,
            "match_context": match_context,
            "provenance": {
                "home_provenance": home_snapshot.provenance,
                "away_provenance": away_snapshot.provenance,
            },
        }

    async def build_model_ready_dataset(
        self,
        entity_type: str,
        feature_set: str,
        start_date: datetime,
        end_date: datetime,
        target_column: str | None = None,
    ) -> list[dict[str, Any]]:
        """Assembles a model-ready tabular dataset guaranteeing feature_timestamp < target_timestamp."""
        stmt = (
            select(FeatureSnapshot)
            .where(
                FeatureSnapshot.entity_type == entity_type,
                FeatureSnapshot.feature_set == feature_set,
                FeatureSnapshot.as_of >= start_date,
                FeatureSnapshot.as_of <= end_date,
            )
            .options(selectinload(FeatureSnapshot.match))
            .order_by(FeatureSnapshot.as_of.asc())
        )
        snapshots = (await self._session.execute(stmt)).scalars().all()

        dataset: list[dict[str, Any]] = []
        for snap in snapshots:
            row: dict[str, Any] = {
                "entity_type": snap.entity_type,
                "entity_id": str(snap.entity_id),
                "match_id": str(snap.match_id) if snap.match_id else None,
                "as_of": snap.as_of.isoformat(),
                **snap.features,
            }

            # If target column requested, attach target value from target match
            if target_column and snap.match is not None:
                # E.g. target_column == 'result' from MatchTeam
                if snap.entity_type == "team":
                    mt_stmt = select(MatchTeam).where(
                        MatchTeam.match_id == snap.match_id,
                        MatchTeam.club_id == snap.entity_id,
                    )
                    mt = (await self._session.execute(mt_stmt)).scalar_one_or_none()
                    row["target"] = getattr(mt, target_column, None) if mt else None
                elif snap.entity_type == "player":
                    p_stmt = select(PlayerMatchStats).where(
                        PlayerMatchStats.match_id == snap.match_id,
                        PlayerMatchStats.player_id == snap.entity_id,
                    )
                    pms = (await self._session.execute(p_stmt)).scalar_one_or_none()
                    row["target"] = getattr(pms, target_column, None) if pms else None

            dataset.append(row)

        return dataset
