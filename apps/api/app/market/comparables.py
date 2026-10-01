"""Deterministic Comparable Transfer Engine (Phase 4.1K).
Retrieves, scores, and ranks historical transfer transactions against a target player profile
using transparent multi-dimensional similarity metrics without black-box heuristics.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import (
    Club,
    Player,
    PlayerContributionSnapshot,
    PlayerRoleProfile,
    Transfer,
)
from app.market.context import build_player_market_context
from app.market.schemas import ComparableTransferItem, ComparableTransfersResponse
from app.market.taxonomy import TransferFeeStatus
from app.roles.registry import map_position_to_group


class ComparableTransferEngine:
    """Deterministic comparable transaction engine."""

    # Explicit, documented weights summing to 1.0
    WEIGHT_ROLE = 0.30
    WEIGHT_CONTRIBUTION = 0.25
    WEIGHT_AGE = 0.20
    WEIGHT_TIER = 0.15
    WEIGHT_RECENCY = 0.10

    def calculate_similarity(
        self,
        target_age: float | None,
        candidate_age: float | None,
        target_role: str | None,
        candidate_role: str | None,
        target_contrib: dict[str, float],
        candidate_contrib: dict[str, float],
        days_diff: int,
        target_tier: float = 1.0,
        candidate_tier: float = 1.0,
    ) -> tuple[float, dict[str, float]]:
        """Calculates multi-dimensional similarity between target profile and historical transfer."""
        # 1. Role similarity
        if target_role and candidate_role:
            s_role = 1.0 if target_role.lower() == candidate_role.lower() else 0.65
        else:
            s_role = 0.75

        # 2. Age similarity: exponential decay with lambda = 0.20
        if target_age is not None and candidate_age is not None:
            age_diff = abs(target_age - candidate_age)
            s_age = math.exp(-0.20 * age_diff)
        else:
            s_age = 0.70

        # 3. Contribution similarity
        if target_contrib and candidate_contrib:
            common_keys = set(target_contrib.keys()) & set(candidate_contrib.keys())
            if common_keys:
                dot = sum(target_contrib[k] * candidate_contrib[k] for k in common_keys)
                norm_a = math.sqrt(sum(v * v for v in target_contrib.values()))
                norm_b = math.sqrt(sum(v * v for v in candidate_contrib.values()))
                if norm_a > 1e-6 and norm_b > 1e-6:
                    s_contrib = max(0.0, min(1.0, dot / (norm_a * norm_b)))
                else:
                    s_contrib = 0.50
            else:
                s_contrib = 0.50
        else:
            s_contrib = 0.65

        # 4. Competition tier similarity
        tier_diff = abs(target_tier - candidate_tier)
        s_tier = max(0.0, 1.0 - 0.20 * tier_diff)

        # 5. Temporal recency similarity: 5-year half-life decay
        years_diff = max(0.0, days_diff / 365.25)
        s_recency = math.exp(-0.15 * years_diff)

        # Composite score
        composite = (
            self.WEIGHT_ROLE * s_role
            + self.WEIGHT_CONTRIBUTION * s_contrib
            + self.WEIGHT_AGE * s_age
            + self.WEIGHT_TIER * s_tier
            + self.WEIGHT_RECENCY * s_recency
        )
        composite = round(max(0.0, min(1.0, composite)), 4)

        breakdown = {
            "role": round(s_role, 3),
            "age": round(s_age, 3),
            "contribution": round(s_contrib, 3),
            "tier": round(s_tier, 3),
            "recency": round(s_recency, 3),
        }
        return composite, breakdown

    async def find_comparables(
        self,
        session: AsyncSession,
        player_id: uuid.UUID,
        as_of: datetime | date | None = None,
        top_k: int = 5,
        min_similarity: float = 0.40,
        include_free: bool = False,
    ) -> ComparableTransfersResponse:
        """Finds top-K historical transfer comparables for a target player as of a given timestamp."""
        eval_time = as_of or datetime.now(timezone.utc)
        eval_date = eval_time.date() if isinstance(eval_time, datetime) else eval_time
        eval_datetime = eval_time if isinstance(eval_time, datetime) else datetime.combine(eval_time, datetime.min.time(), tzinfo=timezone.utc)

        # 1. Fetch target player context
        context = await build_player_market_context(session, player_id, as_of=eval_time)
        player = (await session.execute(select(Player).where(Player.id == player_id))).scalar_one()

        if not context:
            return ComparableTransfersResponse(
                target_player_id=player_id,
                target_player_name=player.name,
                as_of=eval_datetime,
                comparables_count=0,
                comparables=[],
            )

        # 2. Query candidate historical transfers (strictly <= eval_date)
        fee_filter = [TransferFeeStatus.KNOWN_FEE.value, TransferFeeStatus.REPORTED_FEE.value]
        if include_free:
            fee_filter.append(TransferFeeStatus.FREE_TRANSFER.value)

        stmt = (
            select(Transfer)
            .options(
                selectinload(Transfer.player),
                selectinload(Transfer.from_club),
                selectinload(Transfer.to_club),
            )
            .where(
                Transfer.transfer_date <= eval_date,
                Transfer.fee_status.in_(fee_filter),
                Transfer.player_id != player_id,
                Transfer.is_permanent == True,
            )
            .order_by(desc(Transfer.transfer_date))
        )
        candidates = list((await session.execute(stmt)).scalars().all())

        scored_items: list[ComparableTransferItem] = []

        for cand in candidates:
            if not cand.player or not cand.transfer_date:
                continue

            cand_pos_group = map_position_to_group(cand.player.primary_position).value if cand.player.primary_position else "MID"
            # Hard Position Group Filter: Outfield vs GK strictly gated
            if context.position_group and cand_pos_group != context.position_group:
                continue

            # Candidate player age at candidate transfer date
            cand_age = None
            if cand.player.date_of_birth:
                cand_age = round((cand.transfer_date - cand.player.date_of_birth).days / 365.25, 1)

            # Query candidate role profile as of candidate transfer date
            cand_dt = datetime.combine(cand.transfer_date, datetime.min.time(), tzinfo=timezone.utc)
            cand_role_stmt = (
                select(PlayerRoleProfile)
                .where(PlayerRoleProfile.player_id == cand.player_id, PlayerRoleProfile.as_of <= cand_dt)
                .order_by(desc(PlayerRoleProfile.as_of))
                .limit(1)
            )
            cand_role_snap = (await session.execute(cand_role_stmt)).scalar_one_or_none()
            cand_role = cand_role_snap.primary_archetype if cand_role_snap else None

            days_diff = max(0, (eval_date - cand.transfer_date).days)

            score, breakdown = self.calculate_similarity(
                target_age=context.age_at_as_of,
                candidate_age=cand_age,
                target_role=context.role_archetype,
                candidate_role=cand_role,
                target_contrib=context.contribution_scores,
                candidate_contrib={},
                days_diff=days_diff,
            )

            if score >= min_similarity:
                item = ComparableTransferItem(
                    transfer_id=cand.id,
                    player_id=cand.player_id,
                    player_name=cand.player.name,
                    from_club_name=cand.from_club.name if cand.from_club else None,
                    to_club_name=cand.to_club.name if cand.to_club else None,
                    transfer_date=cand.transfer_date,
                    transfer_type=cand.transfer_type,
                    fee_value=cand.fee_value,
                    fee_currency=cand.fee_currency,
                    fee_eur_normalized=cand.fee_eur_normalized,
                    fee_status=cand.fee_status,
                    player_age_at_transfer=cand_age,
                    position_group=cand_pos_group,
                    role_archetype=cand_role,
                    similarity_score=score,
                    similarity_breakdown=breakdown,
                )
                scored_items.append(item)

        scored_items.sort(key=lambda x: x.similarity_score, reverse=True)
        top_items = scored_items[:top_k]

        return ComparableTransfersResponse(
            target_player_id=player_id,
            target_player_name=player.name,
            as_of=eval_datetime,
            comparables_count=len(top_items),
            comparables=top_items,
            calculation_version="comparable_v1",
        )
