"""Tactical Fit Service (Phase 2 Slice 3).
Orchestrates point-in-time tactical fit calculation, canonical persistence in PostgreSQL,
head-to-head comparison, and explainability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Player, PlayerRoleProfile, PlayerTacticalFit
from app.roles.registry import PositionGroup, map_position_to_group
from app.roles.service import RoleService
from app.tactical.calculator import TacticalFitCalculator
from app.tactical.contexts import (
    STANDARD_TACTICAL_CONTEXTS,
    TacticalContext,
    build_custom_context,
    get_standard_context,
)
from app.tactical.explain import generate_tactical_explanations
from app.tactical.schemas import (
    PlayerTacticalFitResponse,
    TacticalFitComparisonResponse,
)

logger = logging.getLogger(__name__)

CALCULATION_VERSION = "tactical_fit_v1"


class TacticalFitService:
    """Service layer for evaluating player tactical compatibility with systems and roles."""

    def __init__(
        self,
        session: AsyncSession,
        calculator: TacticalFitCalculator | None = None,
    ) -> None:
        self.session = session
        self.calculator = calculator or TacticalFitCalculator()
        self.role_service = RoleService(session)

    async def calculate_and_save_tactical_fit(
        self,
        player_id: uuid.UUID,
        context: TacticalContext,
        as_of: datetime | None = None,
        team_id: uuid.UUID | None = None,
        season_id: uuid.UUID | None = None,
    ) -> PlayerTacticalFit:
        """Calculates a temporal-safe tactical fit score for a player and persists to PostgreSQL idempotently."""
        eval_time = as_of or datetime.now(timezone.utc)

        # 1. Fetch player
        p_stmt = select(Player).where(Player.id == player_id)
        player_res = await self.session.execute(p_stmt)
        player = player_res.scalar_one_or_none()
        if not player:
            raise ValueError(f"Player {player_id} not found.")

        player_pos_group = map_position_to_group(player.primary_position)

        # 2. Retrieve or compute player role profile as of eval_time
        profile = await self.role_service.get_role_profile(player_id, as_of=eval_time)
        if not profile:
            profile = await self.role_service.compute_and_save_role_profile(player_id, as_of=eval_time)

        # 3. Calculate component fits
        pos_fit = self.calculator.calculate_position_fit(
            player_position=player.primary_position,
            player_position_group=player_pos_group,
            target_position=context.target_position,
            target_position_group=context.position_group,
        )

        role_fit = self.calculator.calculate_role_fit(
            player_primary_archetype=profile.primary_archetype,
            player_secondary_archetype=profile.secondary_archetype,
            target_role=context.target_role,
            profile_scores=profile.profile_scores,
            target_position_group=context.position_group,
        )

        dim_fit, dimension_breakdown = self.calculator.calculate_dimensional_fit(
            profile_scores=profile.profile_scores,
            requirements=context.requirements,
        )

        style_fit = self.calculator.calculate_style_fit(
            profile_scores=profile.profile_scores,
            context=context,
        )

        contextual_fit = self.calculator.calculate_contextual_fit(
            sample_minutes=profile.sample_minutes,
        )

        composite_fit = self.calculator.calculate_composite_fit(
            position_fit=pos_fit,
            role_fit=role_fit,
            dimension_fit=dim_fit,
            style_fit=style_fit,
            contextual_fit=contextual_fit,
        )

        confidence, fit_status = self.calculator.evaluate_confidence_and_status(
            sample_minutes=profile.sample_minutes,
            sample_matches=profile.sample_matches,
            role_status=profile.role_status,
            composite_fit=composite_fit,
        )

        # 4. Generate structured explanations
        explanations = generate_tactical_explanations(
            player_name=player.name,
            player_position=player.primary_position,
            position_fit=pos_fit,
            role_fit=role_fit,
            dimension_breakdown=dimension_breakdown,
            style_fit=style_fit,
            context=context,
            confidence=confidence,
            sample_minutes=profile.sample_minutes,
        )

        provenance = {
            "source_role_profile_id": str(profile.id),
            "sample_minutes": profile.sample_minutes,
            "sample_matches": profile.sample_matches,
            "role_status": profile.role_status,
            "evaluation_time": eval_time.isoformat(),
            "context_version": context.version,
        }

        # 5. Idempotent upsert
        fit_stmt = select(PlayerTacticalFit).where(
            PlayerTacticalFit.player_id == player_id,
            PlayerTacticalFit.tactical_context_id == context.context_id,
            PlayerTacticalFit.feature_set_version == profile.feature_set_version,
            PlayerTacticalFit.calculation_version == CALCULATION_VERSION,
            PlayerTacticalFit.as_of == eval_time,
        )
        existing_res = await self.session.execute(fit_stmt)
        fit_record = existing_res.scalar_one_or_none()

        if fit_record:
            fit_record.team_id = team_id
            fit_record.season_id = season_id
            fit_record.formation = context.formation
            fit_record.target_position = context.target_position
            fit_record.position_group = context.position_group.value
            fit_record.target_role = context.target_role
            fit_record.fit_score = composite_fit
            fit_record.position_fit = pos_fit
            fit_record.role_fit = role_fit
            fit_record.dimension_fit = dim_fit
            fit_record.style_fit = style_fit
            fit_record.contextual_fit = contextual_fit
            fit_record.confidence = confidence
            fit_record.fit_status = fit_status
            fit_record.dimension_breakdown = dimension_breakdown
            fit_record.why_fit = explanations["why_fit"]
            fit_record.why_not_fit = explanations["why_not_fit"]
            fit_record.provenance = provenance
        else:
            fit_record = PlayerTacticalFit(
                player_id=player_id,
                team_id=team_id,
                season_id=season_id,
                tactical_context_id=context.context_id,
                formation=context.formation,
                target_position=context.target_position,
                position_group=context.position_group.value,
                target_role=context.target_role,
                fit_score=composite_fit,
                position_fit=pos_fit,
                role_fit=role_fit,
                dimension_fit=dim_fit,
                style_fit=style_fit,
                contextual_fit=contextual_fit,
                confidence=confidence,
                fit_status=fit_status,
                dimension_breakdown=dimension_breakdown,
                why_fit=explanations["why_fit"],
                why_not_fit=explanations["why_not_fit"],
                calculation_version=CALCULATION_VERSION,
                feature_set_version=profile.feature_set_version,
                as_of=eval_time,
                provenance=provenance,
            )
            self.session.add(fit_record)

        await self.session.flush()
        return fit_record

    async def get_tactical_fit(
        self,
        player_id: uuid.UUID,
        context_id: str,
        as_of: datetime | None = None,
    ) -> PlayerTacticalFit | None:
        """Retrieves the latest tactical fit evaluation for a player and context."""
        stmt = (
            select(PlayerTacticalFit)
            .options(selectinload(PlayerTacticalFit.player))
            .where(
                PlayerTacticalFit.player_id == player_id,
                PlayerTacticalFit.tactical_context_id == context_id,
            )
        )
        if as_of:
            stmt = stmt.where(PlayerTacticalFit.as_of <= as_of)

        stmt = stmt.order_by(desc(PlayerTacticalFit.as_of)).limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def compare_players(
        self,
        player_a_id: uuid.UUID,
        player_b_id: uuid.UUID,
        context: TacticalContext,
        as_of: datetime | None = None,
    ) -> TacticalFitComparisonResponse:
        """Compares two players side-by-side against the same tactical context."""
        eval_time = as_of or datetime.now(timezone.utc)

        fit_a = await self.get_tactical_fit(player_a_id, context.context_id, eval_time)
        if not fit_a:
            fit_a = await self.calculate_and_save_tactical_fit(player_a_id, context, eval_time)

        fit_b = await self.get_tactical_fit(player_b_id, context.context_id, eval_time)
        if not fit_b:
            fit_b = await self.calculate_and_save_tactical_fit(player_b_id, context, eval_time)

        p1_res = await self.session.execute(select(Player).where(Player.id == player_a_id))
        p1 = p1_res.scalar_one()
        p2_res = await self.session.execute(select(Player).where(Player.id == player_b_id))
        p2 = p2_res.scalar_one()

        # Build dimensional deltas
        all_dims = set(fit_a.dimension_breakdown.keys()) | set(fit_b.dimension_breakdown.keys())
        deltas: dict[str, dict[str, float]] = {}
        for dim in all_dims:
            score_a = fit_a.dimension_breakdown.get(dim, {}).get("fit_score", 0.0)
            score_b = fit_b.dimension_breakdown.get(dim, {}).get("fit_score", 0.0)
            deltas[dim] = {
                p1.name: score_a,
                p2.name: score_b,
                "delta": round(abs(score_a - score_b), 4),
            }

        diff = fit_a.fit_score - fit_b.fit_score
        if abs(diff) < 0.05:
            summary = f"{p1.name} ({fit_a.fit_score:.2f}) and {p2.name} ({fit_b.fit_score:.2f}) have comparable tactical fit for {context.target_role} in {context.formation}."
        elif diff > 0:
            summary = f"{p1.name} ({fit_a.fit_score:.2f}) exhibits stronger overall tactical fit than {p2.name} ({fit_b.fit_score:.2f}) for {context.target_role}."
        else:
            summary = f"{p2.name} ({fit_b.fit_score:.2f}) exhibits stronger overall tactical fit than {p1.name} ({fit_a.fit_score:.2f}) for {context.target_role}."

        resp_a = PlayerTacticalFitResponse(
            id=fit_a.id,
            player_id=fit_a.player_id,
            player_name=p1.name,
            team_id=fit_a.team_id,
            season_id=fit_a.season_id,
            tactical_context_id=fit_a.tactical_context_id,
            formation=fit_a.formation,
            target_position=fit_a.target_position,
            position_group=fit_a.position_group,
            target_role=fit_a.target_role,
            fit_score=fit_a.fit_score,
            position_fit=fit_a.position_fit,
            role_fit=fit_a.role_fit,
            dimension_fit=fit_a.dimension_fit,
            style_fit=fit_a.style_fit,
            contextual_fit=fit_a.contextual_fit,
            confidence=fit_a.confidence,
            fit_status=fit_a.fit_status,
            dimension_breakdown=fit_a.dimension_breakdown,
            why_fit=fit_a.why_fit,
            why_not_fit=fit_a.why_not_fit,
            calculation_version=fit_a.calculation_version,
            feature_set_version=fit_a.feature_set_version,
            as_of=fit_a.as_of,
            provenance=fit_a.provenance,
            created_at=fit_a.created_at,
        )

        resp_b = PlayerTacticalFitResponse(
            id=fit_b.id,
            player_id=fit_b.player_id,
            player_name=p2.name,
            team_id=fit_b.team_id,
            season_id=fit_b.season_id,
            tactical_context_id=fit_b.tactical_context_id,
            formation=fit_b.formation,
            target_position=fit_b.target_position,
            position_group=fit_b.position_group,
            target_role=fit_b.target_role,
            fit_score=fit_b.fit_score,
            position_fit=fit_b.position_fit,
            role_fit=fit_b.role_fit,
            dimension_fit=fit_b.dimension_fit,
            style_fit=fit_b.style_fit,
            contextual_fit=fit_b.contextual_fit,
            confidence=fit_b.confidence,
            fit_status=fit_b.fit_status,
            dimension_breakdown=fit_b.dimension_breakdown,
            why_fit=fit_b.why_fit,
            why_not_fit=fit_b.why_not_fit,
            calculation_version=fit_b.calculation_version,
            feature_set_version=fit_b.feature_set_version,
            as_of=fit_b.as_of,
            provenance=fit_b.provenance,
            created_at=fit_b.created_at,
        )

        return TacticalFitComparisonResponse(
            context_id=context.context_id,
            formation=context.formation,
            target_position=context.target_position,
            target_role=context.target_role,
            player_a=resp_a,
            player_b=resp_b,
            comparison_summary=summary,
            dimensional_deltas=deltas,
        )
