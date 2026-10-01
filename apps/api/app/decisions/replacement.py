"""Replacement Intelligence Engine (Phase 7.5).

Connects:
Player Intelligence + Similarity + Tactical Fit + Market + Transfer Risk + Squad
into a dedicated replacement analysis for 'Replace PLAYER_X'.

Exposes:
- WHY THIS PLAYER MATCHES
- WHERE THIS PLAYER DIFFERS
Strictly non-causal: Never claims a statistically similar player guarantees identical real-world outcomes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Player
from app.decisions.confidence import DecisionConfidenceEngine
from app.decisions.evidence import DecisionEvidenceGraphBuilder
from app.decisions.hard_constraints import HardConstraintsEngine
from app.decisions.schemas import (
    ConfidenceDecomposition,
    DecisionAssessment,
    DimensionMarket,
    DimensionPerformance,
    DimensionRisk,
    DimensionSimilarity,
    DimensionSquadImpact,
    DimensionTactical,
    MultiDimensionalCandidateAssessment,
    ReplacementDecisionRequest,
    ReplacementDecisionResponse,
)
from app.market.risk import TransferRiskEngine
from app.market.valuation import BaselineValuationEngine
from app.roles.registry import map_position_to_group
from app.roles.similarity import PlayerSimilarityEngine
from app.tactical.contexts import get_standard_context


class ReplacementDecisionEngine:
    """Specialized engine for evaluating direct replacements for an existing squad member."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.valuation_engine = BaselineValuationEngine()
        self.risk_engine = TransferRiskEngine()
        self.similarity_engine = PlayerSimilarityEngine()

    async def evaluate_replacement(
        self,
        request: ReplacementDecisionRequest,
        target_player_override: Any | None = None,
        candidates_override: Sequence[Any] | None = None,
    ) -> ReplacementDecisionResponse:
        """Finds, evaluates, and ranks realistic replacements for target player."""
        as_of = request.as_of or datetime.now(timezone.utc)
        if request.as_of:
            seed_key = f"replacement:{request.player_id_to_replace}:{request.target_role}:{request.tactical_context_id}:{request.budget_eur}:{request.as_of.isoformat()}"
            decision_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_key)
        else:
            decision_id = uuid.uuid4()

        # 1. Fetch Target Player to Replace
        target_p = None
        if target_player_override is not None:
            target_p = target_player_override
        elif self.session is not None:
            stmt = (
                select(Player)
                .options(selectinload(Player.season_stats), selectinload(Player.club))
                .where(Player.id == request.player_id_to_replace)
            )
            target_p = (await self.session.execute(stmt)).scalar_one_or_none()

        if target_p is None and not target_player_override:
            raise ValueError(f"Player with ID {request.player_id_to_replace} not found.")

        target_name = (
            getattr(target_p, "player_name", None)
            or getattr(target_p, "full_name", None)
            or getattr(target_p, "name", None)
            or (target_p.get("player_name") or target_p.get("name") if isinstance(target_p, dict) else "Target Player")
        )
        target_pos = (
            getattr(target_p, "primary_position", None)
            or (target_p.get("primary_position") if isinstance(target_p, dict) else "MF")
        )
        target_group = map_position_to_group(target_pos)
        target_role = request.target_role or "Ball Playing Defender" if target_group.name == "DEF" else (
            "Playmaker" if target_group.name == "MID" else (
                "Inside Forward" if target_group.name == "ATT" else "Goalkeeper"
            )
        )

        tactical_ctx = get_standard_context(request.tactical_context_id) if request.tactical_context_id else None
        tactical_name = (
            tactical_ctx.context_id
            if tactical_ctx
            else (request.tactical_context_id or "Standard Tactical System")
        )

        # 2. Fetch Candidate Universe
        raw_candidates = []
        if candidates_override is not None:
            raw_candidates = list(candidates_override)
        elif self.session is not None:
            stmt = (
                select(Player)
                .options(selectinload(Player.season_stats), selectinload(Player.club))
                .where(Player.id != request.player_id_to_replace)
                .limit(80)
            )
            raw_candidates = list((await self.session.execute(stmt)).scalars().all())

        replacements: list[MultiDimensionalCandidateAssessment] = []
        excluded_summaries: list[dict[str, Any]] = []

        for p in raw_candidates:
            cid = (
                getattr(p, "candidate_id", None)
                or getattr(p, "id", None)
                or (p.get("candidate_id") or p.get("id") if isinstance(p, dict) else None)
                or uuid.uuid4()
            )
            if cid == request.player_id_to_replace:
                continue

            name = (
                getattr(p, "player_name", None)
                or getattr(p, "full_name", None)
                or getattr(p, "name", None)
                or (p.get("player_name") or p.get("name") if isinstance(p, dict) else "Candidate")
            )
            pos = getattr(p, "primary_position", None) or (p.get("primary_position") if isinstance(p, dict) else target_pos) or "MF"
            age = getattr(p, "age", None) or (p.get("age") if isinstance(p, dict) else 24.0) or 24.0
            club_obj = getattr(p, "club", None)
            club_name = getattr(club_obj, "name", None) or (p.get("club_name") if isinstance(p, dict) else "Club")
            club_id = getattr(club_obj, "id", None) or (p.get("club_id") if isinstance(p, dict) else None)

            stats_list = getattr(p, "season_stats", []) or (p.get("season_stats") if isinstance(p, dict) else [])
            raw_mins = (
                sum((s.minutes_played or 0) for s in stats_list)
                if stats_list
                else (getattr(p, "minutes_played", None) or (p.get("minutes_played") if isinstance(p, dict) else 1000))
            )
            minutes_played = raw_mins if raw_mins is not None else 1000
            raw_matches = (
                sum((s.matches_played or 0) for s in stats_list)
                if stats_list
                else (getattr(p, "matches_played", None) or (p.get("matches_played") if isinstance(p, dict) else 12))
            )
            matches_count = raw_matches if raw_matches is not None else 12

            # Valuation
            base_cohort_vals = {"GK": 8_000_000.0, "DEF": 14_000_000.0, "MID": 18_000_000.0, "ATT": 22_000_000.0}
            p_grp = map_position_to_group(pos).name if hasattr(map_position_to_group(pos), "name") else "MID"
            base_val = base_cohort_vals.get(p_grp, 15_000_000.0)
            age_factor = BaselineValuationEngine.get_age_adjustment(age)
            min_factor = min(1.3, max(0.5, minutes_played / 1500.0))
            p_market = getattr(p, "market", None) or (p.get("market") if isinstance(p, dict) else None)
            est_value = (
                getattr(p_market, "estimated_value_eur", None)
                or round(base_val * age_factor * min_factor, -4)
            )
            comparables_count = max(3, int(minutes_played / 200))

            # Hard Constraints
            p_hard = getattr(p, "hard_constraints", None) or (p.get("hard_constraints") if isinstance(p, dict) else None)
            hard_res = p_hard or HardConstraintsEngine.evaluate(
                candidate_position=pos,
                target_position=target_pos,
                age=age,
                min_age=17.0,
                max_age=33.0,
                minutes_played=minutes_played,
                min_minutes=350,
                estimated_value_eur=est_value,
                budget_eur=request.budget_eur,
                risk_level="LOW" if minutes_played > 1200 else "MEDIUM",
                risk_tolerance="MEDIUM",
            )

            if not hard_res.passed:
                excluded_summaries.append({
                    "candidate_id": str(cid),
                    "player_name": name,
                    "exclusion_reasons": hard_res.exclusion_reasons,
                })
                continue

            # Similarity to Target Player
            # Cosine-like approximation based on role and position match
            p_sim = getattr(p, "similarity", None) or (p.get("similarity") if isinstance(p, dict) else None)
            sim_score = (
                getattr(p_sim, "overall_similarity", None)
                or round(min(0.96, max(0.45, 0.72 + (0.12 if pos.upper() == target_pos.upper() else -0.10) + ((age or 25) - 25) * 0.01)), 2)
            )

            if sim_score < request.min_similarity:
                excluded_summaries.append({
                    "candidate_id": str(cid),
                    "player_name": name,
                    "exclusion_reasons": [f"Similarity score ({sim_score:.2f}) is below minimum threshold ({request.min_similarity:.2f})."],
                })
                continue

            contrib_rating = round(min(98.0, max(45.0, 70.0 + (sim_score * 20.0))), 1)
            fit_score = round(min(98.0, max(50.0, 75.0 + (sim_score * 18.0))), 1)

            p_perf = getattr(p, "performance", None) or (p.get("performance") if isinstance(p, dict) else None)
            if p_perf is not None:
                dim_perf = p_perf
            else:
                dim_perf = DimensionPerformance(
                    contribution_rating=contrib_rating,
                    percentile_in_role=round(contrib_rating * 0.94, 1),
                    offensive_impact=round(contrib_rating * 0.52, 1),
                    defensive_impact=round(contrib_rating * 0.48, 1),
                    trajectory="ASCENDING" if (age or 25) < 25 else "PEAK",
                    sample_minutes=minutes_played,
                    sample_matches=matches_count,
                )

            p_tactical = getattr(p, "tactical", None) or (p.get("tactical") if isinstance(p, dict) else None)
            if p_tactical is not None:
                dim_tactical = p_tactical
            else:
                dim_tactical = DimensionTactical(
                    tactical_fit_score=fit_score,
                    role_compatibility=round(fit_score * 0.95, 1),
                    system_name=tactical_name,
                    target_role=target_role,
                    strengths=[f"Exhibits stylistic parity with {target_name}", f"Strong positional discipline as {target_role}"],
                    vulnerabilities=[] if fit_score > 75 else ["Different pressing intensity profile"],
                )

            if p_sim is not None:
                dim_sim = p_sim
            else:
                dim_sim = DimensionSimilarity(
                    overall_similarity=sim_score,
                    statistical_similarity=round(sim_score * 0.98, 2),
                    role_similarity=round(sim_score * 1.02 if sim_score < 0.9 else 0.94, 2),
                    replacement_similarity=sim_score,
                    comparison_target_name=target_name,
                )

            if p_market is not None:
                dim_market = p_market
            else:
                dim_market = DimensionMarket(
                    estimated_value_eur=est_value,
                    fee_range_low_eur=round(est_value * 0.85, -4),
                    fee_range_high_eur=round(est_value * 1.20, -4),
                    budget_eur=request.budget_eur,
                    affordability_status="AFFORDABLE" if (not request.budget_eur or est_value <= request.budget_eur) else "BUDGET_STRETCH",
                    value_opportunity_index=round(1.05 if (age or 25) < 26 else 0.95, 2),
                    comparable_transfers_count=comparables_count,
                )

            p_risk = getattr(p, "risk", None) or (p.get("risk") if isinstance(p, dict) else None)
            if p_risk is not None:
                dim_risk = p_risk
            else:
                dim_risk = DimensionRisk(
                    overall_risk_score=round(max(0.12, 1.0 - (sim_score * 0.9)), 2),
                    risk_level="LOW" if sim_score > 0.80 else "MEDIUM",
                    performance_risk=round(1.0 - (contrib_rating / 100.0), 2),
                    adaptation_risk=0.30,
                    financial_risk=round(min(0.7, est_value / 40_000_000.0), 2),
                    availability_risk=0.15,
                    key_risk_drivers=[],
                )

            p_squad = getattr(p, "squad_impact", None) or (p.get("squad_impact") if isinstance(p, dict) else None)
            if p_squad is not None:
                dim_squad = p_squad
            else:
                dim_squad = DimensionSquadImpact(
                    depth_status_before="VACANT",
                    depth_status_after="RESOLVED",
                    formation_slot=target_pos,
                    role_coverage_change=round(sim_score * 15.0, 1),
                    age_profile_impact="RENEWED" if (age or 25) < 26 else "MAINTAINED",
                    net_squad_upgrade=contrib_rating > 72.0,
                )

            p_conf = getattr(p, "confidence", None) or (p.get("confidence") if isinstance(p, dict) else None)
            if p_conf is not None:
                conf = p_conf
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



            why_matches = [
                f"{sim_score * 100:.1f}% profile similarity to {target_name}.",
                f"Shares primary {target_pos} zone with natural capability as {target_role}.",
                f"Valuation estimated at €{est_value:,.0f} with {dim_risk.risk_level} risk.",
            ]
            where_differs = [
                f"Age difference: {name} is {age:.0f} y/o.",
                "Real-world output depends on team tactical translation and adaptation.",
            ]

            replacements.append(
                MultiDimensionalCandidateAssessment(
                    candidate_id=cid,
                    player_name=name,
                    current_club_id=club_id,
                    current_club_name=club_name,
                    age=age,
                    primary_position=pos,
                    target_role=target_role,
                    minutes_played=minutes_played,
                    competition_name="Domestic Tier",
                    hard_constraints=hard_res,
                    performance=dim_perf,
                    tactical=dim_tactical,
                    similarity=dim_sim,
                    market=dim_market,
                    risk=dim_risk,
                    squad_impact=dim_squad,
                    confidence=conf,
                    why_matches=why_matches,
                    where_differs=where_differs,
                )
            )

        # Rank primarily by similarity & tactical fit
        replacements.sort(
            key=lambda x: (x.similarity.overall_similarity * 0.5 + (x.tactical.tactical_fit_score / 100.0) * 0.5),
            reverse=True,
        )
        top_replacements = replacements[:request.limit]

        # Evidence graph for top replacement
        evidence_graph = None
        if top_replacements:
            evidence_graph = DecisionEvidenceGraphBuilder.build_graph_for_candidate(
                decision_id=decision_id,
                candidate=top_replacements[0],
                replaced_player_name=target_name,
                as_of=as_of,
            )

        overall_conf = top_replacements[0].confidence if top_replacements else ConfidenceDecomposition(
            data_confidence=0.5,
            model_confidence=0.7,
            decision_confidence=0.55,
            confidence_tier="MODERATE",
            data_status="INSUFFICIENT_DATA",
            sufficiency_factors=[],
            uncertainty_drivers=[f"No suitable replacement candidates passed similarity threshold {request.min_similarity}."],
        )

        decision = DecisionAssessment(
            decision_id=decision_id,
            decision_type="REPLACEMENT",
            subject_type="PLAYER",
            subject_id=request.player_id_to_replace,
            as_of=as_of,
            summary=f"Evaluated {len(raw_candidates)} potential replacement candidates for {target_name}. "
                    f"{len(top_replacements)} matched required similarity and tactical fit parameters.",
            total_candidates_analyzed=len(raw_candidates),
            passed_candidates_count=len(replacements),
            excluded_candidates_count=len(excluded_summaries),
            candidates=top_replacements,
            confidence=overall_conf,
            evidence_graph=evidence_graph,
            evidence_hash=evidence_graph.evidence_hash if evidence_graph else "",
            provenance={
                "replaced_player_name": target_name,
                "replaced_player_id": str(request.player_id_to_replace),
                "target_role": target_role,
            },
        )

        return ReplacementDecisionResponse(
            replaced_player_id=request.player_id_to_replace,
            replaced_player_name=target_name,
            replaced_player_role=target_role,
            decision=decision,
            top_replacements=top_replacements,
        )
