"""Transfer Risk Classification Engine (Phase 5B.3).
Evaluates performance risk, adaptation risk, financial risk, availability risk,
and league-translation risk for transfer targets — classified only when
backend evidence is sufficient, never fabricated.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import (
    Player,
    PlayerSeasonStats,
    Transfer,
)
from app.market.context import build_player_market_context
from app.market.valuation import BaselineValuationEngine
from app.market.comparables import ComparableTransferEngine


# ─── Schemas ──────────────────────────────────────────────────

class RiskDimension(BaseModel):
    """Individual risk dimension assessment."""
    model_config = ConfigDict(extra="ignore")

    dimension: str  # e.g. 'PERFORMANCE', 'ADAPTATION', 'FINANCIAL', 'AVAILABILITY', 'LEAGUE_TRANSLATION'
    risk_level: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'INSUFFICIENT_DATA'
    score: float  # 0.0 (no risk) – 1.0 (extreme risk)
    evidence: list[str] = Field(default_factory=list)
    factors: dict[str, Any] = Field(default_factory=dict)


class TransferRiskProfile(BaseModel):
    """Complete transfer risk assessment for a player."""
    model_config = ConfigDict(extra="ignore")

    player_id: uuid.UUID
    player_name: str
    age: float | None = None
    position_group: str | None = None
    current_club_name: str | None = None

    overall_risk_level: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'INSUFFICIENT_DATA'
    overall_risk_score: float = 0.0
    dimensions: list[RiskDimension] = Field(default_factory=list)
    risk_summary: str = ""
    data_quality: str = "STANDARD"  # 'HIGH', 'STANDARD', 'LIMITED'
    assessment_version: str = "risk_v1"


class TransferRiskBatchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    as_of: datetime
    total_assessed: int
    profiles: list[TransferRiskProfile] = Field(default_factory=list)
    methodology: str = "Multi-Dimensional Transfer Risk Assessment v1"


# ─── Engine ──────────────────────────────────────────────────

MIN_SCORED_DIMENSIONS = 2


class TransferRiskEngine:
    """Evaluates multi-dimensional transfer risk with transparent evidence."""

    def __init__(self) -> None:
        self.comparable_engine = ComparableTransferEngine()
        self.valuation_engine = BaselineValuationEngine(self.comparable_engine)

    @staticmethod
    def classify_risk_level(score: float) -> str:
        """Classifies a numeric risk score (0-1) into a categorical risk level."""
        if score >= 0.75:
            return "CRITICAL"
        elif score >= 0.55:
            return "HIGH"
        elif score >= 0.30:
            return "MEDIUM"
        else:
            return "LOW"

    def evaluate_performance_risk(
        self,
        ctx: Any,
        season_stats: list[Any],
    ) -> RiskDimension:
        """Assesses risk that a player's performance regresses after transfer."""
        evidence = []
        factors = {}
        score = 0.50  # Baseline moderate risk

        # Sample size risk: fewer minutes = higher uncertainty. Phase 18 (R23):
        # minutes come from the contribution snapshot, else provider-reported
        # season minutes; with neither the sample is unknown, not zero.
        mins = ctx.sample_minutes if ctx and ctx.sample_minutes else None
        matches = ctx.sample_matches if ctx and ctx.sample_matches else None
        if mins is None:
            reported = [st for st in season_stats if st.minutes is not None]
            if reported:
                mins = sum(st.minutes for st in reported)
                apps = [st.appearances for st in reported if st.appearances is not None]
                matches = sum(apps) if apps else None
        if mins is None:
            return RiskDimension(
                dimension="PERFORMANCE", risk_level="INSUFFICIENT_DATA", score=0.0,
                evidence=["No contribution sample and no provider-reported minutes — performance risk unknown."],
                factors={},
            )
        matches_txt = f"{matches} matches" if matches is not None else "unreported matches"

        if mins < 500:
            score += 0.25
            evidence.append(f"Limited sample: {mins} minutes across {matches_txt} — high regression risk.")
            factors["sample_minutes"] = mins
        elif mins < 1500:
            score += 0.10
            evidence.append(f"Moderate sample: {mins} minutes — some regression uncertainty.")
        else:
            score -= 0.10
            evidence.append(f"Strong sample: {mins} minutes — lower regression risk.")

        # Age-based performance trajectory risk
        age = ctx.age_at_as_of if ctx else None
        if age is not None:
            if age >= 31.0:
                score += 0.20
                evidence.append(f"Age {age:.1f} — elevated risk of performance decline.")
            elif age >= 28.0:
                score += 0.05
                evidence.append(f"Age {age:.1f} — moderate age-related risk.")
            elif age < 21.0:
                score += 0.10
                evidence.append(f"Age {age:.1f} — developmental volatility risk.")
            else:
                score -= 0.05
                evidence.append(f"Age {age:.1f} — prime career window, lower performance risk.")
            factors["age"] = age

        # Season consistency (if we have multiple seasons)
        if len(season_stats) >= 2:
            ratings = [s.rating for s in season_stats if s.rating is not None]
            if len(ratings) >= 2:
                avg = sum(ratings) / len(ratings)
                variance = sum((r - avg) ** 2 for r in ratings) / len(ratings)
                if variance > 0.5:
                    score += 0.15
                    evidence.append(f"High season-to-season variability (σ²={variance:.2f}).")
                else:
                    score -= 0.05
                    evidence.append("Consistent season-to-season performance.")
                factors["rating_variance"] = round(variance, 3)

        score = max(0.0, min(1.0, score))
        return RiskDimension(
            dimension="PERFORMANCE",
            risk_level=self.classify_risk_level(score),
            score=round(score, 3),
            evidence=evidence,
            factors=factors,
        )

    def evaluate_adaptation_risk(
        self,
        ctx: Any,
        transfers: list[Any],
    ) -> RiskDimension:
        """Assesses risk that a player fails to adapt to a new environment."""
        evidence = []
        factors = {}
        score = 0.40  # Baseline

        # Transfer history: more transfers might indicate adaptability (or instability).
        # Phase 18 (R21/R23): only provider-verified transfers count, and no
        # history means the adaptation profile is unknown, not "risky".
        verified = [t for t in transfers if getattr(t, "provenance_status", "VERIFIED_SOURCE") == "VERIFIED_SOURCE"]
        total_transfers = len(verified)
        factors["total_transfers"] = total_transfers
        factors["unverified_transfers_ignored"] = len(transfers) - total_transfers

        if total_transfers == 0:
            return RiskDimension(
                dimension="ADAPTATION", risk_level="INSUFFICIENT_DATA", score=0.0,
                evidence=["No verified transfer history — adaptation profile unknown."], factors=factors,
            )
        elif total_transfers == 1:
            score += 0.05
            evidence.append("Single prior move — limited adaptation evidence.")
        elif total_transfers <= 3:
            score -= 0.10
            evidence.append(f"{total_transfers} prior transfers — some demonstrated adaptability.")
        else:
            # Many moves could mean either strong adaptability or instability
            score += 0.05
            evidence.append(f"{total_transfers} transfers — frequent moves may indicate either adaptability or instability.")

        # Age factor for adaptation
        age = ctx.age_at_as_of if ctx else None
        if age is not None:
            if age < 23.0:
                score -= 0.05
                evidence.append("Young age improves adaptation ceiling.")
            elif age >= 30.0:
                score += 0.10
                evidence.append("Senior player — harder adaptation to new tactical systems.")
            factors["age_adaptation"] = age

        score = max(0.0, min(1.0, score))
        return RiskDimension(
            dimension="ADAPTATION",
            risk_level=self.classify_risk_level(score),
            score=round(score, 3),
            evidence=evidence,
            factors=factors,
        )

    def evaluate_financial_risk(
        self,
        ctx: Any,
        estimated_value_eur: float | None,
    ) -> RiskDimension:
        """Assesses financial risk of the transfer investment."""
        evidence = []
        factors = {}
        score = 0.40  # Baseline

        age = ctx.age_at_as_of if ctx else None

        if estimated_value_eur is not None:
            factors["estimated_value_eur"] = estimated_value_eur

            # High absolute value = higher financial risk
            m_eur = estimated_value_eur / 1_000_000
            if m_eur >= 70.0:
                score += 0.25
                evidence.append(f"High estimated value (€{m_eur:.1f}M) — significant financial exposure.")
            elif m_eur >= 30.0:
                score += 0.10
                evidence.append(f"Moderate estimated value (€{m_eur:.1f}M).")
            else:
                score -= 0.10
                evidence.append(f"Lower estimated value (€{m_eur:.1f}M) — reduced financial risk.")

            # Age-value depreciation risk
            if age is not None and age >= 28.0 and m_eur >= 20.0:
                score += 0.15
                evidence.append(f"Age {age:.1f} with high value — resale depreciation risk.")
                factors["depreciation_risk"] = True

        else:
            return RiskDimension(
                dimension="FINANCIAL", risk_level="INSUFFICIENT_DATA", score=0.0,
                evidence=["No verified valuation — financial risk unknown."], factors=factors,
            )

        # Last transfer fee context
        last_fee = ctx.last_transfer_fee_eur if ctx else None
        if last_fee is not None and estimated_value_eur is not None:
            if estimated_value_eur > last_fee * 2.0:
                score += 0.10
                evidence.append("Estimated value significantly exceeds last known fee — potential overpayment risk.")
            factors["last_fee_eur"] = last_fee

        score = max(0.0, min(1.0, score))
        return RiskDimension(
            dimension="FINANCIAL",
            risk_level=self.classify_risk_level(score),
            score=round(score, 3),
            evidence=evidence,
            factors=factors,
        )

    def evaluate_availability_risk(
        self,
        season_stats: list[Any],
        ctx: Any,
    ) -> RiskDimension:
        """Assesses injury/availability risk based on historical minutes and appearance patterns."""
        evidence = []
        factors = {}
        score = 0.35  # Baseline

        if not season_stats:
            score = 0.0
            evidence.append("No season statistics available — availability risk unknown.")
            return RiskDimension(
                dimension="AVAILABILITY",
                risk_level="INSUFFICIENT_DATA",
                score=round(score, 3),
                evidence=evidence,
                factors=factors,
            )

        # Availability uses only seasons whose provider reported appearances;
        # an unreported season is not counted as zero appearances.
        reported = [s for s in season_stats if s.appearances is not None]
        factors["seasons_unreported"] = len(season_stats) - len(reported)
        if not reported:
            evidence.append("Season rows exist but no provider reported appearances — availability risk unknown.")
            return RiskDimension(
                dimension="AVAILABILITY",
                risk_level="INSUFFICIENT_DATA",
                score=round(score, 3),
                evidence=evidence,
                factors=factors,
            )
        total_apps = sum(s.appearances for s in reported)
        lineup_rows = [s.lineups for s in reported if s.lineups is not None]
        total_lineups = sum(lineup_rows) if lineup_rows else None
        minute_rows = [s.minutes for s in reported if s.minutes is not None]
        total_minutes = sum(minute_rows) if minute_rows else None
        seasons_count = len(reported)

        factors["total_appearances"] = total_apps
        factors["total_minutes"] = total_minutes
        factors["seasons_observed"] = seasons_count

        if seasons_count > 0:
            avg_apps = total_apps / seasons_count

            if avg_apps < 15:
                score += 0.25
                evidence.append(f"Low average appearances ({avg_apps:.0f}/season) — significant availability concern.")
            elif avg_apps < 25:
                score += 0.10
                evidence.append(f"Moderate appearances ({avg_apps:.0f}/season).")
            else:
                score -= 0.10
                evidence.append(f"Strong availability ({avg_apps:.0f} appearances/season).")

            # Starter consistency
            if total_apps > 0 and total_lineups is not None:
                lineup_rate = total_lineups / total_apps
                if lineup_rate < 0.50:
                    score += 0.10
                    evidence.append(f"Low lineup rate ({lineup_rate:.0%}) — rotation or fitness concerns.")
                factors["lineup_rate"] = round(lineup_rate, 3)

        score = max(0.0, min(1.0, score))
        return RiskDimension(
            dimension="AVAILABILITY",
            risk_level=self.classify_risk_level(score),
            score=round(score, 3),
            evidence=evidence,
            factors=factors,
        )

    async def assess_player_risk(
        self,
        session: AsyncSession,
        player_id: uuid.UUID,
    ) -> TransferRiskProfile:
        """Produces a complete multi-dimensional risk profile for a player."""
        eval_time = datetime.now(timezone.utc)

        # Fetch context
        player = (await session.execute(
            select(Player).where(Player.id == player_id)
        )).scalar_one_or_none()
        if not player:
            return TransferRiskProfile(
                player_id=player_id,
                player_name="Unknown",
                overall_risk_level="INSUFFICIENT_DATA",
                risk_summary="Player not found in canonical database.",
            )

        ctx = await build_player_market_context(session, player_id, as_of=eval_time)

        # Fetch season stats
        stats_stmt = (
            select(PlayerSeasonStats)
            .where(PlayerSeasonStats.player_id == player_id)
            .order_by(desc(PlayerSeasonStats.id))
        )
        season_stats = list((await session.execute(stats_stmt)).scalars().all())

        # Fetch transfers
        t_stmt = (
            select(Transfer)
            .where(Transfer.player_id == player_id)
            .order_by(desc(Transfer.transfer_date))
        )
        transfers = list((await session.execute(t_stmt)).scalars().all())

        # Estimated value: only a registry-servable valuation model may supply
        # one. While the valuation model is UNVERIFIED, financial risk is
        # INSUFFICIENT_DATA rather than computed from an unverified price.
        estimated_value = None

        # Evaluate each dimension
        dimensions = [
            self.evaluate_performance_risk(ctx, season_stats),
            self.evaluate_adaptation_risk(ctx, transfers),
            self.evaluate_financial_risk(ctx, estimated_value),
            self.evaluate_availability_risk(season_stats, ctx),
        ]

        # Overall score: weighted average of dimensions
        weights = {
            "PERFORMANCE": 0.30,
            "ADAPTATION": 0.20,
            "FINANCIAL": 0.25,
            "AVAILABILITY": 0.25,
        }
        total_score = sum(
            weights.get(d.dimension, 0.25) * d.score
            for d in dimensions
            if d.risk_level != "INSUFFICIENT_DATA"
        )
        scored_dims = [d for d in dimensions if d.risk_level != "INSUFFICIENT_DATA"]
        if len(scored_dims) >= MIN_SCORED_DIMENSIONS:
            weight_sum = sum(weights.get(d.dimension, 0.25) for d in scored_dims)
            overall_score = round(total_score / max(0.01, weight_sum), 3)
            overall_level = self.classify_risk_level(overall_score)
        else:
            # Phase 18 (R23): one scored dimension is not an overall profile.
            overall_score = 0.0
            overall_level = "INSUFFICIENT_DATA"

        # Data quality assessment
        data_quality = "HIGH" if len(season_stats) >= 3 and len(transfers) >= 1 else (
            "STANDARD" if len(season_stats) >= 1 else "LIMITED"
        )

        # Risk summary
        high_risk_dims = [d for d in dimensions if d.risk_level in ("HIGH", "CRITICAL")]
        if overall_level == "INSUFFICIENT_DATA":
            summary = (f"Insufficient evidence: {len(scored_dims)} of {len(dimensions)} risk dimensions have data "
                       f"(at least {MIN_SCORED_DIMENSIONS} required).")
        elif high_risk_dims:
            summary = f"Elevated risk in: {', '.join(d.dimension.lower() for d in high_risk_dims)}."
        elif overall_level == "LOW":
            summary = "Low overall transfer risk — strong evidence across all dimensions."
        else:
            summary = f"Overall {overall_level.lower()} risk profile with {len(scored_dims)} of {len(dimensions)} dimensions assessed."

        return TransferRiskProfile(
            player_id=player.id,
            player_name=player.name,
            age=ctx.age_at_as_of if ctx else None,
            position_group=ctx.position_group if ctx else None,
            current_club_name=ctx.current_club_name if ctx else None,
            overall_risk_level=overall_level,
            overall_risk_score=overall_score,
            dimensions=dimensions,
            risk_summary=summary,
            data_quality=data_quality,
        )

    async def assess_batch(
        self,
        session: AsyncSession,
        player_ids: list[uuid.UUID] | None = None,
        position_group: str | None = None,
        limit: int = 25,
    ) -> TransferRiskBatchResponse:
        """Batch risk assessment across the player universe."""
        eval_time = datetime.now(timezone.utc)

        if player_ids:
            stmt = select(Player).where(Player.id.in_(player_ids))
        else:
            stmt = select(Player)
            if position_group and position_group != "ALL":
                pg = position_group.upper()
                if pg == "GK":
                    stmt = stmt.where(Player.primary_position.ilike("%Goalkeeper%"))
                elif pg == "DEF":
                    stmt = stmt.where(Player.primary_position.ilike("%Defender%"))
                elif pg == "MID":
                    stmt = stmt.where(Player.primary_position.ilike("%Midfielder%"))
                elif pg in ("ATT", "FWD"):
                    stmt = stmt.where(
                        Player.primary_position.ilike("%Attacker%")
                        | Player.primary_position.ilike("%Forward%")
                    )

        players = list((await session.execute(stmt.limit(limit))).scalars().all())

        profiles = []
        for player in players:
            try:
                profile = await self.assess_player_risk(session, player.id)
                profiles.append(profile)
            except Exception:
                continue

        # Sort by overall risk score (highest risk first)
        profiles.sort(key=lambda p: p.overall_risk_score, reverse=True)

        return TransferRiskBatchResponse(
            as_of=eval_time,
            total_assessed=len(profiles),
            profiles=profiles,
        )
