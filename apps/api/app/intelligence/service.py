"""Player Intelligence Service (Phase 3.2).
Orchestrates point-in-time player intelligence generation, temporal-safe queries,
snapshot caching, and PostgreSQL persistence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.action_value.action_impact import ActionImpactModel
from app.contributions.service import ContributionService
from app.db.models.canonical import (
    Competition,
    CompetitionSeason,
    Match,
    Player,
    PlayerIntelligenceSnapshot,
    PlayerMatchStats,
    PlayerRoleProfile,
    PlayerTacticalFit,
)
from app.intelligence.benchmarks import PeerBenchmarkingEngine
from app.intelligence.context import ContextualEngine
from app.intelligence.explanations import DeterministicExplanationGenerator
from app.intelligence.schemas import (
    BenchmarkMetricItem,
    PlayerBenchmarksResponse,
    PlayerIntelligenceResponse,
    PlayerTrajectoryResponse,
)
from app.intelligence.taxonomy import (
    ConfidenceTier,
    DataStatus,
    INTELLIGENCE_CALCULATION_VERSION,
    INTELLIGENCE_FEATURE_SET_VERSION,
)
from app.intelligence.trajectory import TrajectoryCompiler
from app.intelligence.vector import PlayerIntelligenceVectorCompiler
from app.roles.registry import map_position_to_group
from app.roles.service import RoleService

logger = logging.getLogger(__name__)


class PlayerIntelligenceService:
    """Orchestrates comprehensive player intelligence compilation and persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.contribution_service = ContributionService(session)
        self.role_service = RoleService(session)
        self.context_engine = ContextualEngine()
        self.benchmark_engine = PeerBenchmarkingEngine()
        self.vector_compiler = PlayerIntelligenceVectorCompiler()
        self.trajectory_compiler = TrajectoryCompiler()
        self.explanation_generator = DeterministicExplanationGenerator()
        self.action_impact_model = ActionImpactModel()

    async def get_player_intelligence(
        self,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> PlayerIntelligenceResponse:
        """Retrieves or computes point-in-time player intelligence snapshot."""
        cutoff = as_of or datetime.now(timezone.utc)

        # 1. Fetch player
        p_res = await self.session.execute(select(Player).where(Player.id == player_id))
        player = p_res.scalar_one_or_none()
        if not player:
            raise ValueError(f"Player {player_id} not found")

        pos_group = map_position_to_group(player.primary_position).value

        # 2. Check for existing snapshot at cutoff
        existing_res = await self.session.execute(
            select(PlayerIntelligenceSnapshot).where(
                PlayerIntelligenceSnapshot.player_id == player_id,
                PlayerIntelligenceSnapshot.as_of == cutoff,
                PlayerIntelligenceSnapshot.calculation_version == INTELLIGENCE_CALCULATION_VERSION,
            )
        )
        existing = existing_res.scalar_one_or_none()
        if existing:
            return PlayerIntelligenceResponse(
                player_id=existing.player_id,
                player_name=player.name,
                position_group=existing.position_group,
                as_of=existing.as_of,
                calculation_version=existing.calculation_version,
                data_status=existing.data_status,
                sample_minutes=existing.sample_minutes,
                sample_matches=existing.sample_matches,
                confidence=existing.confidence,
                contribution_vector=existing.contribution_vector,
                intelligence_vector=existing.intelligence_vector,
                peer_benchmarks=existing.peer_benchmarks,
                contextual_adjustments=existing.contextual_adjustments,
                explanations=existing.explanations,
                trajectory=existing.trajectory,
                provenance=existing.provenance,
            )

        # 3. Retrieve temporal-safe Contribution Profile
        contrib_profile = await self.contribution_service.get_player_contribution_profile(
            player_id=player_id,
            as_of=cutoff,
        )

        # 4. Query chronological match stats strictly respecting temporal safety (Match.date < cutoff)
        stmt = (
            select(PlayerMatchStats, Match)
            .join(Match, PlayerMatchStats.match_id == Match.id)
            .where(
                PlayerMatchStats.player_id == player_id,
                Match.date < cutoff,
            )
            .order_by(Match.date.asc())
        )
        records = (await self.session.execute(stmt)).all()
        stats_list = [r[0] for r in records]

        # Extract primary competition if available
        comp_name = None
        comp_country = None
        if records:
            first_cs_id = records[0][1].competition_season_id
            if first_cs_id:
                cs_stmt = (
                    select(Competition.name, Competition.country)
                    .join(CompetitionSeason, CompetitionSeason.competition_id == Competition.id)
                    .where(CompetitionSeason.id == first_cs_id)
                )
                cs_row = (await self.session.execute(cs_stmt)).first()
                if cs_row:
                    comp_name = cs_row[0]
                    comp_country = cs_row[1]

        # 5. Evaluate Context
        context_data = self.context_engine.evaluate_player_context(
            stats_list=stats_list,
            competition_name=comp_name,
            competition_country=comp_country,
        )

        # 6. Evaluate Peer Benchmarks
        peer_benchmarks = self.benchmark_engine.evaluate_benchmarks(
            raw_metrics=contrib_profile.raw_metrics,
            position_group=pos_group,
            sample_minutes=contrib_profile.sample_minutes,
        )

        # 7. Compile Trajectory
        trajectory_data = self.trajectory_compiler.compile_trajectory(records)

        # 8. Retrieve Role Profile and Action Values
        role_profile = await self.role_service.get_role_profile(player_id, as_of=cutoff)
        role_dict = (
            {
                "primary_archetype": role_profile.primary_archetype,
                "secondary_archetype": role_profile.secondary_archetype,
                "archetype_confidence": role_profile.archetype_confidence,
                "profile_scores": role_profile.profile_scores,
            }
            if role_profile
            else None
        )

        # Action impact evaluation
        _, actions = await self.contribution_service.get_player_actions(player_id, limit=300)
        action_val_res = self.action_impact_model.evaluate(player_id, actions, contrib_profile.sample_minutes)
        action_val_dict = action_val_res.model_dump()

        # 9. Compile Contribution and Intelligence Vectors
        contrib_vector = self.vector_compiler.compile_contribution_vector(
            dimensions=contrib_profile.dimensions,
            raw_metrics=contrib_profile.raw_metrics,
            confidence=contrib_profile.confidence,
            status=contrib_profile.contribution_status,
        )

        intel_vector = self.vector_compiler.compile_intelligence_vector(
            player_id=str(player_id),
            position_group=pos_group,
            raw_metrics=contrib_profile.raw_metrics,
            contribution_vector=contrib_vector,
            role_profile=role_dict,
            context=context_data,
            action_values=action_val_dict,
            confidence=contrib_profile.confidence,
            status=contrib_profile.contribution_status,
        )

        # 10. Generate Deterministic Explanations
        explanations = self.explanation_generator.generate_explanations(
            dimensions=contrib_profile.dimensions,
            raw_metrics=contrib_profile.raw_metrics,
            peer_benchmarks=peer_benchmarks,
            sample_minutes=contrib_profile.sample_minutes,
            sample_matches=contrib_profile.sample_matches,
            confidence=contrib_profile.confidence,
            status=contrib_profile.contribution_status,
        )

        provenance = {
            "calculation_version": INTELLIGENCE_CALCULATION_VERSION,
            "feature_set_version": INTELLIGENCE_FEATURE_SET_VERSION,
            "as_of": cutoff.isoformat(),
            "sample_matches": contrib_profile.sample_matches,
            "sample_minutes": contrib_profile.sample_minutes,
            "source_snapshots": contrib_profile.provenance.get("source_snapshots", []),
            "upstream_contribution_version": contrib_profile.calculation_version,
        }

        # 11. Persist Snapshot
        snapshot = PlayerIntelligenceSnapshot(
            id=uuid.uuid4(),
            player_id=player_id,
            as_of=cutoff,
            calculation_version=INTELLIGENCE_CALCULATION_VERSION,
            data_status=contrib_profile.contribution_status,
            sample_minutes=contrib_profile.sample_minutes,
            sample_matches=contrib_profile.sample_matches,
            confidence=contrib_profile.confidence,
            position_group=pos_group,
            contribution_vector=contrib_vector,
            intelligence_vector=intel_vector,
            peer_benchmarks=peer_benchmarks,
            contextual_adjustments=context_data,
            explanations=explanations,
            trajectory=trajectory_data.get("timeline", []),
            role_profile_id=role_profile.id if role_profile else None,
            provenance=provenance,
        )
        self.session.add(snapshot)
        await self.session.flush()

        return PlayerIntelligenceResponse(
            player_id=player_id,
            player_name=player.name,
            position_group=pos_group,
            as_of=cutoff,
            calculation_version=INTELLIGENCE_CALCULATION_VERSION,
            data_status=contrib_profile.contribution_status,
            sample_minutes=contrib_profile.sample_minutes,
            sample_matches=contrib_profile.sample_matches,
            confidence=contrib_profile.confidence,
            contribution_vector=contrib_vector,
            intelligence_vector=intel_vector,
            peer_benchmarks=peer_benchmarks,
            contextual_adjustments=context_data,
            explanations=explanations,
            trajectory=trajectory_data.get("timeline", []),
            provenance=provenance,
        )

    async def get_player_trajectory(
        self,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> PlayerTrajectoryResponse:
        """Returns longitudinal chronological performance trajectory for a player."""
        cutoff = as_of or datetime.now(timezone.utc)

        p_res = await self.session.execute(select(Player).where(Player.id == player_id))
        player = p_res.scalar_one_or_none()
        if not player:
            raise ValueError(f"Player {player_id} not found")

        stmt = (
            select(PlayerMatchStats, Match)
            .join(Match, PlayerMatchStats.match_id == Match.id)
            .where(
                PlayerMatchStats.player_id == player_id,
                Match.date < cutoff,
            )
            .order_by(Match.date.asc())
        )
        records = (await self.session.execute(stmt)).all()
        trajectory_data = self.trajectory_compiler.compile_trajectory(records)

        return PlayerTrajectoryResponse(
            player_id=player_id,
            player_name=player.name,
            trajectory_status=trajectory_data["trajectory_status"],
            total_recorded_matches=trajectory_data["total_recorded_matches"],
            cumulative_minutes=trajectory_data["cumulative_minutes"],
            volatility_score=trajectory_data["volatility_score"],
            timeline=trajectory_data["timeline"],
            seasonal_trend=trajectory_data["seasonal_trend"],
        )

    async def get_player_benchmarks(
        self,
        player_id: uuid.UUID,
        as_of: datetime | None = None,
    ) -> PlayerBenchmarksResponse:
        """Returns position-aware peer benchmarks and percentile metrics."""
        cutoff = as_of or datetime.now(timezone.utc)

        p_res = await self.session.execute(select(Player).where(Player.id == player_id))
        player = p_res.scalar_one_or_none()
        if not player:
            raise ValueError(f"Player {player_id} not found")

        pos_group = map_position_to_group(player.primary_position).value

        contrib_profile = await self.contribution_service.get_player_contribution_profile(
            player_id=player_id,
            as_of=cutoff,
        )

        benchmarks = self.benchmark_engine.evaluate_benchmarks(
            raw_metrics=contrib_profile.raw_metrics,
            position_group=pos_group,
            sample_minutes=contrib_profile.sample_minutes,
        )

        metric_items = {
            k: BenchmarkMetricItem(**v) for k, v in benchmarks["metrics"].items()
        }

        return PlayerBenchmarksResponse(
            player_id=player_id,
            player_name=player.name,
            position_group=pos_group,
            benchmark_status=benchmarks["benchmark_status"],
            sample_minutes=benchmarks["sample_minutes"],
            peer_sample_size=benchmarks.get("peer_sample_size", 0),
            average_percentile=benchmarks.get("average_percentile"),
            metrics=metric_items,
        )
