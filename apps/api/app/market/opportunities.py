"""Market Opportunities Engine (Phase 5B.1).
Identifies players where estimated value diverges from reference market value,
with transparent evidence and deterministic methodology — no fabricated scores.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Player, Transfer
from app.market.context import build_player_market_context
from app.market.comparables import ComparableTransferEngine
from app.market.valuation import BaselineValuationEngine
from app.roles.registry import map_position_to_group


# ─── Schemas ──────────────────────────────────────────────────

class OpportunityCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    player_name: str
    age: float | None = None
    position_group: str | None = None
    role_archetype: str | None = None
    current_club_name: str | None = None

    estimated_value_eur: float | None = None
    comparable_median_eur: float | None = None
    last_transfer_fee_eur: float | None = None
    last_fee_status: str | None = None

    value_gap_eur: float | None = None
    value_gap_pct: float | None = None
    opportunity_class: str  # 'UNDERVALUED', 'FAIRLY_VALUED', 'PREMIUM', 'INSUFFICIENT_DATA'

    evidence: list[str] = Field(default_factory=list)
    comparable_count: int = 0
    confidence: str = "LOW"  # 'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT_DATA'


class MarketOpportunitiesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    as_of: datetime
    total_candidates: int
    opportunities: list[OpportunityCandidate] = Field(default_factory=list)
    methodology: str = "Comparable Median Gap Analysis v1"
    filters_applied: dict[str, Any] = Field(default_factory=dict)


# ─── Engine ──────────────────────────────────────────────────

class MarketOpportunitiesEngine:
    """Identifies market value gaps across the canonical player universe."""

    # Thresholds for opportunity classification
    UNDERVALUED_THRESHOLD = -0.15   # Estimated >= 15% below comparable median
    PREMIUM_THRESHOLD = 0.20        # Estimated >= 20% above comparable median

    def __init__(self) -> None:
        self.comparable_engine = ComparableTransferEngine()
        self.valuation_engine = BaselineValuationEngine(self.comparable_engine)

    def classify_opportunity(
        self,
        value_gap_pct: float | None,
    ) -> str:
        """Classifies a player's market opportunity based on the value gap percentage."""
        if value_gap_pct is None:
            return "INSUFFICIENT_DATA"
        if value_gap_pct <= self.UNDERVALUED_THRESHOLD:
            return "UNDERVALUED"
        elif value_gap_pct >= self.PREMIUM_THRESHOLD:
            return "PREMIUM"
        return "FAIRLY_VALUED"

    async def scan_opportunities(
        self,
        session: AsyncSession,
        position_group: str | None = None,
        min_gap_pct: float | None = None,
        opportunity_class: str | None = None,
        limit: int = 25,
    ) -> MarketOpportunitiesResponse:
        """Scans all canonical players and identifies value gap opportunities."""
        eval_time = datetime.now(timezone.utc)

        # 1. Fetch eligible players
        stmt = select(Player).options(selectinload(Player.transfers))
        if position_group and position_group != "ALL":
            pos_filter = position_group.upper()
            if pos_filter == "GK":
                stmt = stmt.where(Player.primary_position.ilike("%Goalkeeper%"))
            elif pos_filter == "DEF":
                stmt = stmt.where(Player.primary_position.ilike("%Defender%"))
            elif pos_filter == "MID":
                stmt = stmt.where(Player.primary_position.ilike("%Midfielder%"))
            elif pos_filter in ("ATT", "FWD"):
                stmt = stmt.where(
                    Player.primary_position.ilike("%Attacker%")
                    | Player.primary_position.ilike("%Forward%")
                )

        players = list((await session.execute(stmt)).scalars().all())

        candidates: list[OpportunityCandidate] = []

        for player in players:
            try:
                # Build market context
                ctx = await build_player_market_context(session, player.id, as_of=eval_time)
                if not ctx:
                    continue

                # Get valuation baseline
                baseline = await self.valuation_engine.compute_valuation_baseline(
                    session, player.id, as_of=eval_time, min_sample_size=3
                )

                if baseline.valuation_status != "VALUATION_AVAILABLE":
                    candidates.append(OpportunityCandidate(
                        player_id=player.id,
                        player_name=player.name,
                        age=ctx.age_at_as_of,
                        position_group=ctx.position_group,
                        role_archetype=ctx.role_archetype,
                        current_club_name=ctx.current_club_name,
                        opportunity_class="INSUFFICIENT_DATA",
                        confidence="INSUFFICIENT_DATA",
                        evidence=["Insufficient comparable transfers for valuation baseline."],
                    ))
                    continue

                # Compute value gap
                est_val = baseline.estimated_value_eur
                cohort_med = baseline.cohort_median_fee_eur

                value_gap_eur = None
                value_gap_pct = None

                if est_val is not None and cohort_med is not None and cohort_med > 0:
                    value_gap_eur = round(est_val - cohort_med, 2)
                    value_gap_pct = round((est_val - cohort_med) / cohort_med, 4)

                opp_class = self.classify_opportunity(value_gap_pct)

                # Build evidence strings
                evidence = []
                if est_val is not None:
                    evidence.append(f"Estimated value: €{est_val / 1_000_000:.1f}M")
                if cohort_med is not None:
                    evidence.append(f"Cohort comparable median: €{cohort_med / 1_000_000:.1f}M")
                if value_gap_pct is not None:
                    direction = "below" if value_gap_pct < 0 else "above"
                    evidence.append(f"Value gap: {abs(value_gap_pct) * 100:.1f}% {direction} median")
                if baseline.comparable_sample_size:
                    evidence.append(f"Based on {baseline.comparable_sample_size} comparable transfers")

                candidate = OpportunityCandidate(
                    player_id=player.id,
                    player_name=player.name,
                    age=ctx.age_at_as_of,
                    position_group=ctx.position_group,
                    role_archetype=ctx.role_archetype,
                    current_club_name=ctx.current_club_name,
                    estimated_value_eur=est_val,
                    comparable_median_eur=cohort_med,
                    last_transfer_fee_eur=ctx.last_transfer_fee_eur,
                    last_fee_status=ctx.last_fee_status,
                    value_gap_eur=value_gap_eur,
                    value_gap_pct=value_gap_pct,
                    opportunity_class=opp_class,
                    evidence=evidence,
                    comparable_count=baseline.comparable_sample_size,
                    confidence=baseline.confidence,
                )
                candidates.append(candidate)

            except Exception:
                # Graceful degradation: skip individual player failures
                continue

        # 2. Apply filters
        if opportunity_class:
            candidates = [c for c in candidates if c.opportunity_class == opportunity_class.upper()]
        if min_gap_pct is not None:
            candidates = [
                c for c in candidates
                if c.value_gap_pct is not None and abs(c.value_gap_pct) >= abs(min_gap_pct)
            ]

        # 3. Sort by absolute value gap (largest gaps first)
        candidates.sort(
            key=lambda c: abs(c.value_gap_pct) if c.value_gap_pct is not None else -1.0,
            reverse=True,
        )

        result = candidates[:limit]

        filters = {}
        if position_group:
            filters["position_group"] = position_group
        if min_gap_pct is not None:
            filters["min_gap_pct"] = min_gap_pct
        if opportunity_class:
            filters["opportunity_class"] = opportunity_class

        return MarketOpportunitiesResponse(
            as_of=eval_time,
            total_candidates=len(result),
            opportunities=result,
            filters_applied=filters,
        )
