"""Replacement Finder Engine (Phase 5B.2).
Ranks candidate replacements for a departing player or role gap,
using role fit, tactical fit, age profile, value, and availability.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Player, PlayerRoleProfile, Transfer
from app.market.context import build_player_market_context
from app.market.valuation import BaselineValuationEngine
from app.market.comparables import ComparableTransferEngine
from app.roles.registry import map_position_to_group


# ─── Schemas ──────────────────────────────────────────────────

class ReplacementCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    player_name: str
    age: float | None = None
    position_group: str | None = None
    primary_position: str | None = None
    role_archetype: str | None = None
    current_club_name: str | None = None

    # Fit scores (0.0 – 1.0)
    role_fit_score: float = 0.0
    age_fit_score: float = 0.0
    value_fit_score: float = 0.0
    composite_fit_score: float = 0.0

    # Valuation context
    estimated_value_eur: float | None = None
    last_transfer_fee_eur: float | None = None
    value_assessment: str | None = None  # 'WITHIN_BUDGET', 'ABOVE_BUDGET', 'BELOW_BUDGET'

    evidence: list[str] = Field(default_factory=list)
    fit_breakdown: dict[str, float] = Field(default_factory=dict)


class ReplacementFinderRequest(BaseModel):
    """Request payload for replacement search."""
    target_player_id: uuid.UUID | None = None
    target_role: str | None = None
    target_position_group: str | None = None
    max_age: float | None = None
    max_value_eur: float | None = None
    limit: int = 15


class ReplacementFinderResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    as_of: datetime
    target_description: str
    target_role: str | None = None
    target_position_group: str | None = None
    total_candidates: int
    candidates: list[ReplacementCandidate] = Field(default_factory=list)
    methodology: str = "Multi-Dimensional Replacement Ranking v1"


# ─── Engine ──────────────────────────────────────────────────

class ReplacementFinderEngine:
    """Finds and ranks replacement candidates based on role, age, and value fit."""

    # Composite weights (sum to 1.0)
    WEIGHT_ROLE = 0.45
    WEIGHT_AGE = 0.25
    WEIGHT_VALUE = 0.30

    def __init__(self) -> None:
        self.comparable_engine = ComparableTransferEngine()
        self.valuation_engine = BaselineValuationEngine(self.comparable_engine)

    @staticmethod
    def compute_role_fit(
        target_role: str | None,
        candidate_role: str | None,
        target_position: str | None,
        candidate_position: str | None,
    ) -> float:
        """Computes role fit between target profile and candidate."""
        score = 0.0

        # Position group match (baseline)
        if target_position and candidate_position:
            if target_position.upper() == candidate_position.upper():
                score += 0.40
            else:
                score += 0.10
        else:
            score += 0.25

        # Role archetype match (higher fidelity)
        if target_role and candidate_role:
            if target_role.lower() == candidate_role.lower():
                score += 0.60
            elif (
                target_role.lower().split("_")[0] == candidate_role.lower().split("_")[0]
            ):
                # Partial archetype match (e.g., "deep_playmaker" vs "deep_distributor")
                score += 0.35
            else:
                score += 0.10
        else:
            score += 0.25

        return round(min(1.0, score), 3)

    @staticmethod
    def compute_age_fit(
        target_age: float | None,
        candidate_age: float | None,
        max_age: float | None = None,
    ) -> float:
        """Age fit: prefers candidates near the target age or younger."""
        if candidate_age is None:
            return 0.50

        # Hard gate: reject if over max age
        if max_age is not None and candidate_age > max_age:
            return 0.0

        if target_age is not None:
            age_diff = abs(target_age - candidate_age)
            # Exponential decay: perfect match at 0 diff, decays with lambda=0.15
            score = math.exp(-0.15 * age_diff)
        else:
            # No target age — prefer prime age window (22-28)
            if 22.0 <= candidate_age <= 28.0:
                score = 0.90
            elif candidate_age < 22.0:
                score = 0.75
            elif candidate_age <= 31.0:
                score = 0.60
            else:
                score = 0.35

        return round(min(1.0, score), 3)

    @staticmethod
    def compute_value_fit(
        estimated_value_eur: float | None,
        max_value_eur: float | None = None,
    ) -> float:
        """Value fit: preference for players within budget."""
        if estimated_value_eur is None:
            return 0.50  # Unknown value, neutral

        if max_value_eur is not None:
            if estimated_value_eur <= max_value_eur:
                # Within budget — closer to the budget ceiling is more realistic
                ratio = estimated_value_eur / max(1.0, max_value_eur)
                return round(0.60 + 0.40 * ratio, 3)
            else:
                # Over budget — penalize proportionally
                over_ratio = estimated_value_eur / max(1.0, max_value_eur)
                return round(max(0.05, 1.0 - 0.50 * (over_ratio - 1.0)), 3)

        # No budget constraint — normalize on a reasonable scale
        return 0.65

    async def find_replacements(
        self,
        session: AsyncSession,
        request: ReplacementFinderRequest,
    ) -> ReplacementFinderResponse:
        """Finds and ranks replacement candidates."""
        eval_time = datetime.now(timezone.utc)

        # 1. Resolve target profile
        target_role = request.target_role
        target_position = request.target_position_group
        target_age = None
        target_description = "Role gap"

        if request.target_player_id:
            ctx = await build_player_market_context(session, request.target_player_id, as_of=eval_time)
            if ctx:
                target_role = target_role or ctx.role_archetype
                target_position = target_position or ctx.position_group
                target_age = ctx.age_at_as_of
                target_description = f"Replacement for player (role: {target_role or 'unspecified'}, position: {target_position or 'any'})"

        # 2. Fetch candidate players (exclude the target)
        stmt = select(Player).options(selectinload(Player.transfers))
        players = list((await session.execute(stmt)).scalars().all())

        candidates: list[ReplacementCandidate] = []

        for player in players:
            # Exclude the target player
            if request.target_player_id and player.id == request.target_player_id:
                continue

            try:
                ctx = await build_player_market_context(session, player.id, as_of=eval_time)
                if not ctx:
                    continue

                # Compute fit scores
                role_fit = self.compute_role_fit(
                    target_role, ctx.role_archetype,
                    target_position, ctx.position_group,
                )
                age_fit = self.compute_age_fit(
                    target_age, ctx.age_at_as_of,
                    request.max_age,
                )

                # Skip hard-gated age candidates
                if age_fit == 0.0:
                    continue

                # Get valuation
                estimated_value = None
                try:
                    baseline = await self.valuation_engine.compute_valuation_baseline(
                        session, player.id, as_of=eval_time, min_sample_size=3
                    )
                    if baseline.valuation_status == "VALUATION_AVAILABLE":
                        estimated_value = baseline.estimated_value_eur
                except Exception:
                    pass

                value_fit = self.compute_value_fit(estimated_value, request.max_value_eur)

                # Composite score
                composite = round(
                    self.WEIGHT_ROLE * role_fit
                    + self.WEIGHT_AGE * age_fit
                    + self.WEIGHT_VALUE * value_fit,
                    3,
                )

                # Value assessment
                value_assessment = None
                if estimated_value is not None and request.max_value_eur is not None:
                    if estimated_value <= request.max_value_eur:
                        value_assessment = "WITHIN_BUDGET"
                    elif estimated_value <= request.max_value_eur * 1.2:
                        value_assessment = "ABOVE_BUDGET"
                    else:
                        value_assessment = "SIGNIFICANTLY_ABOVE_BUDGET"

                # Evidence
                evidence = []
                if ctx.role_archetype:
                    evidence.append(f"Role: {ctx.role_archetype}")
                if ctx.age_at_as_of:
                    evidence.append(f"Age: {ctx.age_at_as_of:.1f}")
                if estimated_value:
                    evidence.append(f"Est. value: €{estimated_value / 1_000_000:.1f}M")
                evidence.append(f"Composite fit: {composite * 100:.0f}%")

                candidate = ReplacementCandidate(
                    player_id=player.id,
                    player_name=player.name,
                    age=ctx.age_at_as_of,
                    position_group=ctx.position_group,
                    primary_position=player.primary_position,
                    role_archetype=ctx.role_archetype,
                    current_club_name=ctx.current_club_name,
                    role_fit_score=role_fit,
                    age_fit_score=age_fit,
                    value_fit_score=value_fit,
                    composite_fit_score=composite,
                    estimated_value_eur=estimated_value,
                    last_transfer_fee_eur=ctx.last_transfer_fee_eur,
                    value_assessment=value_assessment,
                    evidence=evidence,
                    fit_breakdown={
                        "role_fit": role_fit,
                        "age_fit": age_fit,
                        "value_fit": value_fit,
                    },
                )
                candidates.append(candidate)

            except Exception:
                continue

        # 3. Sort by composite fit score (descending)
        candidates.sort(key=lambda c: c.composite_fit_score, reverse=True)
        result = candidates[:request.limit]

        return ReplacementFinderResponse(
            as_of=eval_time,
            target_description=target_description,
            target_role=target_role,
            target_position_group=target_position,
            total_candidates=len(result),
            candidates=result,
        )
