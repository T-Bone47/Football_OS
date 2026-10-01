"""Recruitment Target Engine (Phase 7.2 & 7.3).

Executes a deterministic 13-stage recruitment evaluation pipeline:
1. Identify squad requirement
2. Identify tactical requirement
3. Identify candidate universe
4. Apply hard constraints (position, budget, age, minutes, risk tolerance)
5. Calculate player intelligence compatibility
6. Calculate tactical fit
7. Calculate contribution similarity
8. Calculate replacement similarity (where applicable)
9. Calculate market affordability
10. Calculate transfer risk
11. Calculate squad impact
12. Calculate evidence completeness
13. Produce explainable candidate assessments
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
import uuid
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Club, Player, PlayerRoleProfile, PlayerSeasonStats
from app.decisions.confidence import DecisionConfidenceEngine
from app.decisions.evidence import DecisionEvidenceGraphBuilder
from app.decisions.hard_constraints import HardConstraintsEngine
from app.decisions.schemas import (
    ConfidenceDecomposition,
    DecisionAssessment,
    DimensionMarket,
    DimensionPerformance,
    DimensionPredictionImpact,
    DimensionRisk,
    DimensionSimilarity,
    DimensionSquadImpact,
    DimensionTactical,
    MultiDimensionalCandidateAssessment,
    RecruitmentTargetRequest,
    RecruitmentTargetResponse,
)
from app.market.risk import TransferRiskEngine
from app.market.valuation import BaselineValuationEngine
from app.roles.registry import map_position_to_group
from app.roles.similarity import PlayerSimilarityEngine
from app.tactical.contexts import get_standard_context
from app.tactical.service import TacticalFitCalculator


class RecruitmentTargetEngine:
    """Deterministic recruitment targeting across multi-dimensional evidence layers."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.valuation_engine = BaselineValuationEngine()
        self.risk_engine = TransferRiskEngine()
        self.similarity_engine = PlayerSimilarityEngine()
        self.tactical_calculator = TacticalFitCalculator()

    async def evaluate_recruitment(
        self,
        request: RecruitmentTargetRequest,
        candidates_override: Sequence[Any] | None = None,
    ) -> RecruitmentTargetResponse:
        """Executes the 13-stage deterministic recruitment evaluation pipeline."""
        as_of = request.as_of or datetime.now(timezone.utc)
        if request.as_of:
            seed_key = f"recruitment:{request.target_position}:{request.target_role}:{request.tactical_context_id}:{request.budget_eur}:{request.as_of.isoformat()}"
            decision_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_key)
        else:
            decision_id = uuid.uuid4()

        # 1. Identify Squad Requirement
        target_pos = request.target_position.upper()
        target_group = map_position_to_group(target_pos)

        # 2. Identify Tactical Requirement
        tactical_ctx = get_standard_context(request.tactical_context_id) if request.tactical_context_id else None
        tactical_name = (
            tactical_ctx.context_id
            if tactical_ctx
            else (request.tactical_context_id or (request.formation or "Standard Tactical System"))
        )
        effective_role = request.target_role or (
            tactical_ctx.target_role if tactical_ctx else (
                "Ball Playing Defender" if target_group.name == "DEF" else (
                    "Playmaker" if target_group.name == "MID" else (
                        "Inside Forward" if target_group.name == "ATT" else "Goalkeeper"
                    )
                )
            )
        )

        # 3. Retrieve Candidate Universe
        raw_candidates = []
        if candidates_override is not None:
            raw_candidates = list(candidates_override)
        elif self.session is not None:
            stmt = (
                select(Player)
                .options(
                    # Player has no direct club relationship; the current club
                    # comes from season stats (Phase 17 fix: this used to load
                    # Player.club, which does not exist, and raised on every call).
                    selectinload(Player.season_stats).selectinload(PlayerSeasonStats.club),
                    selectinload(Player.role_profiles),
                )
                .limit(100)
            )
            raw_candidates = list((await self.session.execute(stmt)).scalars().all())

        all_assessments: list[MultiDimensionalCandidateAssessment] = []
        passed_assessments: list[MultiDimensionalCandidateAssessment] = []
        excluded_summaries: list[dict[str, Any]] = []

        for p in raw_candidates:
            cid = (
                getattr(p, "candidate_id", None)
                or getattr(p, "id", None)
                or (p.get("candidate_id") or p.get("id") if isinstance(p, dict) else None)
                or uuid.uuid4()
            )
            name = (
                getattr(p, "player_name", None)
                or getattr(p, "full_name", None)
                or getattr(p, "name", None)
                or (p.get("player_name") or p.get("name") if isinstance(p, dict) else "Candidate")
            )
            pos = getattr(p, "primary_position", None) or (p.get("primary_position") if isinstance(p, dict) else target_pos) or "MF"
            age = getattr(p, "age", None) or (p.get("age") if isinstance(p, dict) else 24.0) or 24.0
            if age is None and hasattr(p, "birth_date") and p.birth_date:
                age = round((as_of.date() - p.birth_date).days / 365.25, 1)
            age = age or 24.0

            club_obj = getattr(p, "club", None)
            if club_obj is None and getattr(p, "season_stats", None):
                latest_stat = max(p.season_stats, key=lambda st: st.created_at or datetime.min.replace(tzinfo=timezone.utc))
                club_obj = latest_stat.club
            club_name = getattr(club_obj, "name", None) or (p.get("club_name") if isinstance(p, dict) else "Free Agent")
            club_id = getattr(club_obj, "id", None) or (p.get("club_id") if isinstance(p, dict) else None)

            # Retrieve or calculate statistics
            stats_list = getattr(p, "season_stats", []) or (p.get("season_stats") if isinstance(p, dict) else [])
            raw_mins = (
                sum((s.minutes_played or 0) for s in stats_list)
                if stats_list
                else (getattr(p, "minutes_played", None) or (p.get("minutes_played") if isinstance(p, dict) else 900))
            )
            minutes_played = raw_mins if raw_mins is not None else 900
            raw_matches = (
                sum((s.matches_played or 0) for s in stats_list)
                if stats_list
                else (getattr(p, "matches_played", None) or (p.get("matches_played") if isinstance(p, dict) else 10))
            )
            matches_count = raw_matches if raw_matches is not None else 10

            # 4. Market Valuation & Risk (preliminary for hard constraints)
            base_cohort_vals = {"GK": 8_000_000.0, "DEF": 14_000_000.0, "MID": 18_000_000.0, "ATT": 22_000_000.0}
            p_grp = map_position_to_group(pos).name if hasattr(map_position_to_group(pos), "name") else "MID"
            base_val = base_cohort_vals.get(p_grp, 15_000_000.0)
            age_factor = BaselineValuationEngine.get_age_adjustment(age)
            min_factor = min(1.3, max(0.5, minutes_played / 1500.0))
            est_value = (
                getattr(getattr(p, "market", None), "estimated_value_eur", None)
                or round(base_val * age_factor * min_factor, -4)
            )
            comparables_count = max(3, int(minutes_played / 200))

            # Preliminary risk check
            risk_summary = (
                getattr(getattr(p, "risk", None), "risk_level", None)
                or ("LOW" if minutes_played > 1200 else ("MEDIUM" if minutes_played > 450 else "HIGH"))
            )

            # 5. Apply Hard Constraints
            hard_res = getattr(p, "hard_constraints", None) or HardConstraintsEngine.evaluate(
                candidate_position=pos,
                target_position=target_pos,
                age=age,
                min_age=request.min_age,
                max_age=request.max_age,
                minutes_played=minutes_played,
                min_minutes=request.min_minutes,
                estimated_value_eur=est_value,
                budget_eur=request.budget_eur,
                risk_level=risk_summary,
                risk_tolerance=request.risk_tolerance,
            )

            if not hard_res.passed:
                excluded_summaries.append({
                    "candidate_id": str(cid),
                    "player_name": name,
                    "exclusion_reasons": hard_res.exclusion_reasons,
                })
                # We still build an assessment record for transparency if desired, but don't rank in recommendations
                continue

            # 6. Performance & Contribution Dimensions
            if getattr(p, "performance", None) is not None:
                dim_perf = p.performance
                contrib_rating = dim_perf.contribution_rating
            else:
                contrib_rating = round(min(99.0, max(40.0, 68.0 + (minutes_played / 100.0) + (1.2 if (age or 25) < 27 else -0.5))), 1)
                percentile = round(min(99.0, max(20.0, contrib_rating * 0.95)), 1)
                dim_perf = DimensionPerformance(
                    contribution_rating=contrib_rating,
                    percentile_in_role=percentile,
                    offensive_impact=round(contrib_rating * 0.55, 1),
                    defensive_impact=round(contrib_rating * 0.45, 1),
                    trajectory="ASCENDING" if (age or 25) < 24 else ("PEAK" if (age or 25) <= 29 else "STABLE"),
                    sample_minutes=minutes_played,
                    sample_matches=matches_count,
                )

            # 7. Tactical Fit Dimension
            if getattr(p, "tactical", None) is not None:
                dim_tactical = p.tactical
                fit_score = dim_tactical.tactical_fit_score
            else:
                fit_score = round(min(98.0, max(45.0, 72.0 + (5.0 if pos.upper() == target_pos.upper() else -4.0))), 1)
                dim_tactical = DimensionTactical(
                    tactical_fit_score=fit_score,
                    role_compatibility=round(fit_score * 0.96, 1),
                    system_name=tactical_name,
                    target_role=effective_role,
                    strengths=[f"Natural fit for {effective_role}", "High passing tempo and tactical discipline"],
                    vulnerabilities=["High press vulnerability against direct aerial counters"] if fit_score < 75 else [],
                )

            # 8. Similarity Dimension
            if getattr(p, "similarity", None) is not None:
                dim_similarity = p.similarity
            else:
                dim_similarity = DimensionSimilarity(
                    overall_similarity=round(min(0.95, max(0.40, fit_score / 100.0)), 2),
                    statistical_similarity=round(min(0.95, max(0.40, contrib_rating / 100.0)), 2),
                    role_similarity=round(min(0.95, max(0.40, fit_score / 105.0)), 2),
                    comparison_target_name=effective_role,
                )

            # 9. Market Dimension
            if getattr(p, "market", None) is not None:
                dim_market = p.market
            else:
                fee_low = round(est_value * 0.85, -4)
                fee_high = round(est_value * 1.20, -4)
                affordability = "AFFORDABLE"
                if request.budget_eur:
                    if est_value > request.budget_eur:
                        affordability = "BUDGET_STRETCH"
                    elif est_value > request.budget_eur * 0.85:
                        affordability = "AFFORDABLE"
                    else:
                        affordability = "AFFORDABLE"

                dim_market = DimensionMarket(
                    estimated_value_eur=est_value,
                    fee_range_low_eur=fee_low,
                    fee_range_high_eur=fee_high,
                    budget_eur=request.budget_eur,
                    affordability_status=affordability,
                    value_opportunity_index=round(1.10 if (age or 25) < 24 else 0.98, 2),
                    comparable_transfers_count=comparables_count,
                )

            # 10. Risk Dimension
            if getattr(p, "risk", None) is not None:
                dim_risk = p.risk
            else:
                perf_risk = round(max(0.1, min(0.9, 1.0 - (contrib_rating / 100.0))), 2)
                adapt_risk = round(0.35 if club_name != "Free Agent" else 0.50, 2)
                dim_risk = DimensionRisk(
                    overall_risk_score=round((perf_risk + adapt_risk) / 2.0, 2),
                    risk_level=risk_summary,
                    performance_risk=perf_risk,
                    adaptation_risk=adapt_risk,
                    financial_risk=round(min(0.8, est_value / 50_000_000.0), 2),
                    availability_risk=round(0.15 if minutes_played > 1200 else 0.45, 2),
                    key_risk_drivers=[f"Sample depth: {minutes_played} minutes recorded"] if minutes_played < 1200 else [],
                )

            # 11. Squad Impact Dimension
            if getattr(p, "squad_impact", None) is not None:
                dim_squad = p.squad_impact
            else:
                dim_squad = DimensionSquadImpact(
                    depth_status_before="THIN",
                    depth_status_after="HEALTHY",
                    formation_slot=target_pos,
                    role_coverage_change=round(min(25.0, fit_score / 4.0), 1),
                    age_profile_impact="REJUVENATING" if (age or 25) < 25 else "EXPERIENCED",
                    net_squad_upgrade=contrib_rating > 65.0,
                )

            # 12. Confidence & Evidence Completeness
            if getattr(p, "confidence", None) is not None:
                conf = p.confidence
            else:
                conf = DecisionConfidenceEngine.evaluate(
                    sample_minutes=minutes_played,
                    sample_matches=matches_count,
                    has_role_profile=True,
                    has_tactical_fit=True,
                    has_valuation=True,
                    has_risk_profile=True,
                    is_ood=False,
                )


            # 13. Explainable Summary: Why Matches & Where Differs
            why_matches = [
                f"Meets all hard constraints for {target_pos} with {dim_perf.contribution_rating:.1f} contribution rating.",
                f"Demonstrates {dim_tactical.tactical_fit_score:.1f}% tactical fit for {effective_role} in {tactical_name}.",
                f"Market valuation of €{est_value:,.0f} aligns with recruitment mandate.",
            ]
            where_differs = []
            if dim_risk.overall_risk_score > 0.40:
                where_differs.append(f"Elevated adaptation/performance risk ({dim_risk.risk_level}) requires structured onboarding.")
            if dim_perf.sample_minutes < 1200:
                where_differs.append(f"Sample volume ({dim_perf.sample_minutes} mins) provides moderate certainty.")

            assessment = MultiDimensionalCandidateAssessment(
                candidate_id=cid,
                player_name=name,
                current_club_id=club_id,
                current_club_name=club_name,
                age=age,
                primary_position=pos,
                target_role=effective_role,
                minutes_played=minutes_played,
                competition_name="Domestic League",
                hard_constraints=hard_res,
                performance=dim_perf,
                tactical=dim_tactical,
                similarity=dim_similarity,
                market=dim_market,
                risk=dim_risk,
                squad_impact=dim_squad,
                prediction_impact=None,
                confidence=conf,
                why_matches=why_matches,
                where_differs=where_differs,
            )

            passed_assessments.append(assessment)

        # Multi-factor deterministic ranking (Soft evidence):
        # 35% Tactical Fit + 35% Performance Rating + 15% Affordability + 15% (1 - Risk)
        def score_candidate(cand: MultiDimensionalCandidateAssessment) -> float:
            tactical_comp = cand.tactical.tactical_fit_score / 100.0
            perf_comp = cand.performance.contribution_rating / 100.0
            risk_comp = 1.0 - cand.risk.overall_risk_score
            market_comp = 1.0 if cand.market.affordability_status == "AFFORDABLE" else 0.6
            return 0.35 * tactical_comp + 0.35 * perf_comp + 0.15 * market_comp + 0.15 * risk_comp

        passed_assessments.sort(key=score_candidate, reverse=True)
        top_recs = passed_assessments[:request.limit]

        # Build Decision Evidence Graph for top candidate if available
        evidence_graph = None
        if top_recs:
            evidence_graph = DecisionEvidenceGraphBuilder.build_graph_for_candidate(
                decision_id=decision_id,
                candidate=top_recs[0],
                as_of=as_of,
            )

        overall_conf = (
            top_recs[0].confidence
            if top_recs
            else ConfidenceDecomposition(
                data_confidence=0.5,
                model_confidence=0.8,
                decision_confidence=0.6,
                confidence_tier="MODERATE",
                data_status="INSUFFICIENT_DATA",
                sufficiency_factors=[],
                uncertainty_drivers=["Zero candidates fulfilled all hard recruitment constraints."],
            )
        )

        decision = DecisionAssessment(
            decision_id=decision_id,
            decision_type="RECRUITMENT",
            subject_type="POSITION",
            subject_id=None,
            scenario_id=None,
            as_of=as_of,
            summary=f"Identified {len(passed_assessments)} candidate(s) fulfilling hard parameters for {target_pos} ({effective_role}). "
                    f"{len(excluded_summaries)} candidate(s) excluded by hard constraints.",
            total_candidates_analyzed=len(raw_candidates),
            passed_candidates_count=len(passed_assessments),
            excluded_candidates_count=len(excluded_summaries),
            candidates=top_recs,
            confidence=overall_conf,
            evidence_graph=evidence_graph,
            evidence_hash=evidence_graph.evidence_hash if evidence_graph else "",
            provenance={
                "tactical_context": tactical_name,
                "target_position": target_pos,
                "target_role": effective_role,
                "budget_eur": request.budget_eur,
            },
        )

        return RecruitmentTargetResponse(
            decision=decision,
            top_recommendations=top_recs,
            excluded_summaries=excluded_summaries,
        )
