"""Role Service (Phase 2 Slice 2).
Coordinates role profile calculation from FeatureSnapshots, persistence in PostgreSQL,
multi-dimensional similarity searches, and explainable comparisons.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import FeatureSnapshot, Player, PlayerRoleProfile
from app.roles.profiler import MINIMUM_MINUTES_THRESHOLD, RoleProfiler
from app.roles.registry import (
    DIMENSIONS,
    PositionGroup,
    ROLE_FEATURE_SET_VERSION,
    map_position_to_group,
)
from app.roles.schemas import (
    PlayerComparisonResponse,
    RoleArchetypeResponse,
    SimilarPlayerItem,
    SimilarPlayersResponse,
)
from app.roles.similarity import PlayerSimilarityEngine

logger = logging.getLogger(__name__)


class RoleService:
    """Service layer for player role intelligence and multi-dimensional similarity."""

    def __init__(
        self,
        session: AsyncSession,
        profiler: RoleProfiler | None = None,
        similarity_engine: PlayerSimilarityEngine | None = None,
    ) -> None:
        self.session = session
        self.profiler = profiler or RoleProfiler()
        self.similarity_engine = similarity_engine or PlayerSimilarityEngine()

    async def compute_and_save_role_profile(
        self,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
        feature_set_version: str = ROLE_FEATURE_SET_VERSION,
        custom_min_minutes: int | None = None,
    ) -> PlayerRoleProfile:
        """Derives a functional role profile from the latest FeatureSnapshot as of the given timestamp
        and saves it to PostgreSQL idempotently.
        """
        eval_time = as_of or datetime.now(timezone.utc)

        # 1. Fetch player
        player_stmt = select(Player).where(Player.id == player_id)
        player_res = await self.session.execute(player_stmt)
        player = player_res.scalar_one_or_none()
        if not player:
            raise ValueError(f"Player {player_id} does not exist.")

        position_group = map_position_to_group(player.primary_position)

        # 2. Fetch latest FeatureSnapshot strictly <= eval_time (leakage safe)
        snap_stmt = (
            select(FeatureSnapshot)
            .where(
                FeatureSnapshot.entity_type == "player",
                FeatureSnapshot.entity_id == player_id,
                FeatureSnapshot.as_of <= eval_time,
            )
            .order_by(desc(FeatureSnapshot.as_of))
            .limit(1)
        )
        snap_res = await self.session.execute(snap_stmt)
        snapshot = snap_res.scalar_one_or_none()

        raw_features = snapshot.features if snapshot else {}
        snapshot_id = str(snapshot.id) if snapshot else None

        # Determine sample minutes and matches
        sample_minutes = int(
            raw_features.get("minutes_last_5")
            or raw_features.get("minutes_season_to_date")
            or raw_features.get("minutes")
            or 0
        )
        sample_matches = int(
            raw_features.get("sample_matches_last_5")
            or raw_features.get("appearances_last_5")
            or raw_features.get("appearances")
            or 0
        )

        # 3. Extract & Standardize features
        extracted = self.profiler.extract_role_features(raw_features, position_group)
        standardized = self.profiler.standardize(extracted)

        # 4. Compute continuous 9-dimension scores [0.0, 1.0]
        profile_scores = self.profiler.compute_dimensional_scores(standardized, position_group)

        # 5. Check Sample-Size Gate
        min_threshold = (
            custom_min_minutes
            if custom_min_minutes is not None
            else self.profiler.min_minutes
        )
        is_qualified = self.profiler.is_sample_sufficient(sample_minutes, sample_matches) and (sample_minutes >= min_threshold)

        if not is_qualified:
            role_status = "INSUFFICIENT_SAMPLE"
            primary_archetype = None
            secondary_archetype = None
            archetype_confidence = None
        else:
            role_status = "QUALIFIED"
            primary_archetype, secondary_archetype, archetype_confidence = (
                self.profiler.assign_archetype(profile_scores, position_group)
            )

        provenance = {
            "source_feature_snapshot_id": snapshot_id,
            "feature_set_version": feature_set_version,
            "min_minutes_threshold": min_threshold,
            "evaluation_time": eval_time.isoformat(),
        }

        # 6. Idempotent upsert
        profile_stmt = select(PlayerRoleProfile).where(
            PlayerRoleProfile.player_id == player_id,
            PlayerRoleProfile.feature_set_version == feature_set_version,
            PlayerRoleProfile.as_of == eval_time,
        )
        existing_res = await self.session.execute(profile_stmt)
        profile = existing_res.scalar_one_or_none()

        if profile:
            profile.role_status = role_status
            profile.sample_minutes = sample_minutes
            profile.sample_matches = sample_matches
            profile.position_group = position_group.value
            profile.primary_archetype = primary_archetype
            profile.secondary_archetype = secondary_archetype
            profile.archetype_confidence = archetype_confidence
            profile.profile_scores = profile_scores
            profile.feature_vector = standardized
            profile.provenance = provenance
        else:
            profile = PlayerRoleProfile(
                player_id=player_id,
                as_of=eval_time,
                feature_set_version=feature_set_version,
                role_status=role_status,
                sample_minutes=sample_minutes,
                sample_matches=sample_matches,
                position_group=position_group.value,
                primary_archetype=primary_archetype,
                secondary_archetype=secondary_archetype,
                archetype_confidence=archetype_confidence,
                profile_scores=profile_scores,
                feature_vector=standardized,
                provenance=provenance,
            )
            self.session.add(profile)

        await self.session.flush()
        return profile

    async def get_role_profile(
        self,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> PlayerRoleProfile | None:
        """Retrieves the latest role profile for a player as of the specified time."""
        stmt = (
            select(PlayerRoleProfile)
            .options(selectinload(PlayerRoleProfile.player))
            .where(PlayerRoleProfile.player_id == player_id)
        )
        if as_of:
            stmt = stmt.where(PlayerRoleProfile.as_of <= as_of)

        stmt = stmt.order_by(desc(PlayerRoleProfile.as_of)).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_archetype_summary(
        self,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> RoleArchetypeResponse:
        """Returns concise human-readable role archetype classification."""
        profile = await self.get_role_profile(player_id, as_of)
        if not profile:
            # Try computing on the fly
            profile = await self.compute_and_save_role_profile(player_id, as_of)

        # Get player details
        player_stmt = select(Player).where(Player.id == player_id)
        p_res = await self.session.execute(player_stmt)
        player = p_res.scalar_one_or_none()
        player_name = player.name if player else "Unknown Player"

        if profile.role_status == "INSUFFICIENT_SAMPLE":
            return RoleArchetypeResponse(
                player_id=player_id,
                player_name=player_name,
                role_status=profile.role_status,
                position_group=profile.position_group,
                sample_minutes=profile.sample_minutes,
                sample_matches=profile.sample_matches,
                primary_archetype=None,
                secondary_archetype=None,
                archetype_confidence=None,
                dominant_dimensions=[],
                summary=(
                    f"{player_name} has {profile.sample_minutes} minutes across {profile.sample_matches} matches. "
                    f"Sample is below the minimum threshold ({MINIMUM_MINUTES_THRESHOLD} mins) for stable archetype assignment."
                ),
            )

        # Identify dominant dimensions (highest scores)
        sorted_dims = sorted(profile.profile_scores.items(), key=lambda x: x[1], reverse=True)
        dominant = [f"{dim} ({score:.2f})" for dim, score in sorted_dims[:3]]

        summary = (
            f"{player_name} operates primarily as a {profile.primary_archetype}"
            + (f" with strong {profile.secondary_archetype} characteristics." if profile.secondary_archetype else ".")
            + f" Dominant tendencies: {', '.join(dominant)}."
        )

        return RoleArchetypeResponse(
            player_id=player_id,
            player_name=player_name,
            role_status=profile.role_status,
            position_group=profile.position_group,
            sample_minutes=profile.sample_minutes,
            sample_matches=profile.sample_matches,
            primary_archetype=profile.primary_archetype,
            secondary_archetype=profile.secondary_archetype,
            archetype_confidence=profile.archetype_confidence,
            dominant_dimensions=dominant,
            summary=summary,
        )

    async def find_similar_players(
        self,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
        limit: int = 10,
        position_filter: str | None = None,
        min_minutes: int | None = None,
    ) -> SimilarPlayersResponse:
        """Finds top-N multi-dimensionally similar players with explainable contribution breakdowns."""
        eval_time = as_of or datetime.now(timezone.utc)

        target_profile = await self.get_role_profile(player_id, eval_time)
        if not target_profile:
            target_profile = await self.compute_and_save_role_profile(player_id, eval_time)

        # Candidate profiles query
        stmt = (
            select(PlayerRoleProfile)
            .options(selectinload(PlayerRoleProfile.player))
            .where(
                PlayerRoleProfile.player_id != player_id,
                PlayerRoleProfile.as_of <= eval_time,
            )
        )

        if position_filter:
            norm_pos = position_filter.strip().upper()
            stmt = stmt.where(
                (PlayerRoleProfile.position_group == norm_pos)
                | (PlayerRoleProfile.player.has(primary_position=norm_pos))
            )

        if min_minutes is not None:
            stmt = stmt.where(PlayerRoleProfile.sample_minutes >= min_minutes)

        res = await self.session.execute(stmt)
        candidates = res.scalars().all()

        evaluated: list[SimilarPlayerItem] = []
        target_name = target_profile.player.name if target_profile.player else "Target Player"

        for cand in candidates:
            cand_name = cand.player.name if cand.player else "Candidate Player"

            stat_sim = self.similarity_engine.compute_statistical_similarity(
                target_profile.feature_vector, cand.feature_vector
            )
            role_sim = self.similarity_engine.compute_role_similarity(
                target_profile.profile_scores, cand.profile_scores
            )
            context_sim = self.similarity_engine.compute_contextual_similarity(
                target_profile.position_group,
                cand.position_group,
                target_profile.sample_minutes,
                cand.sample_minutes,
            )
            overall = self.similarity_engine.compute_overall_similarity(
                stat_sim, role_sim, context_sim
            )

            explanations = self.similarity_engine.generate_explanations(
                target_profile.profile_scores,
                cand.profile_scores,
                target_profile.feature_vector,
                cand.feature_vector,
                target_name,
                cand_name,
            )

            evaluated.append(
                SimilarPlayerItem(
                    player_id=cand.player_id,
                    player_name=cand_name,
                    primary_position=cand.player.primary_position if cand.player else None,
                    position_group=cand.position_group,
                    sample_minutes=cand.sample_minutes,
                    primary_archetype=cand.primary_archetype,
                    overall_similarity=overall,
                    statistical_similarity=stat_sim,
                    role_similarity=role_sim,
                    contextual_similarity=context_sim,
                    why_similar=explanations["why_similar"],
                    why_different=explanations["why_different"],
                )
            )

        evaluated.sort(key=lambda x: x.overall_similarity, reverse=True)

        return SimilarPlayersResponse(
            target_player_id=player_id,
            target_player_name=target_name,
            as_of=eval_time,
            total_evaluated=len(evaluated),
            results=evaluated[:limit],
        )

    async def compare_players(
        self,
        player_a_id: uuid.UUID,
        player_b_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> PlayerComparisonResponse:
        """Detailed head-to-head functional comparison of two players."""
        eval_time = as_of or datetime.now(timezone.utc)

        prof_a = await self.get_role_profile(player_a_id, eval_time)
        if not prof_a:
            prof_a = await self.compute_and_save_role_profile(player_a_id, eval_time)

        prof_b = await self.get_role_profile(player_b_id, eval_time)
        if not prof_b:
            prof_b = await self.compute_and_save_role_profile(player_b_id, eval_time)

        name_a = prof_a.player.name if prof_a.player else "Player A"
        name_b = prof_b.player.name if prof_b.player else "Player B"

        stat_sim = self.similarity_engine.compute_statistical_similarity(
            prof_a.feature_vector, prof_b.feature_vector
        )
        role_sim = self.similarity_engine.compute_role_similarity(
            prof_a.profile_scores, prof_b.profile_scores
        )
        context_sim = self.similarity_engine.compute_contextual_similarity(
            prof_a.position_group, prof_b.position_group, prof_a.sample_minutes, prof_b.sample_minutes
        )
        overall = self.similarity_engine.compute_overall_similarity(
            stat_sim, role_sim, context_sim
        )

        explanations = self.similarity_engine.generate_explanations(
            prof_a.profile_scores,
            prof_b.profile_scores,
            prof_a.feature_vector,
            prof_b.feature_vector,
            name_a,
            name_b,
        )

        profile_comp = {}
        for dim in DIMENSIONS:
            profile_comp[dim] = {
                name_a: prof_a.profile_scores.get(dim, 0.0),
                name_b: prof_b.profile_scores.get(dim, 0.0),
                "delta": round(abs(prof_a.profile_scores.get(dim, 0.0) - prof_b.profile_scores.get(dim, 0.0)), 4),
            }

        return PlayerComparisonResponse(
            player_a_id=player_a_id,
            player_a_name=name_a,
            player_b_id=player_b_id,
            player_b_name=name_b,
            overall_similarity=overall,
            statistical_similarity=stat_sim,
            role_similarity=role_sim,
            contextual_similarity=context_sim,
            profile_comparison=profile_comp,
            why_similar=explanations["why_similar"],
            why_different=explanations["why_different"],
        )
