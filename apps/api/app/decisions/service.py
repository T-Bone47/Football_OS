"""Unified Decision Intelligence Service (Phase 7).

Orchestrates all decision-intelligence pipelines:
- Recruitment Target Analysis
- Replacement Intelligence
- Multi-Player Transfer Scenarios
- Candidate Comparison
- Decision Evidence Graph retrieval
- Point-in-time decision persistence & auditing
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.decisions.evidence import DecisionEvidenceGraphBuilder
from app.decisions.recruitment import RecruitmentTargetEngine
from app.decisions.replacement import ReplacementDecisionEngine
from app.decisions.scenario import DecisionTransferScenarioEngine
from app.decisions.schemas import (
    CandidateComparisonRequest,
    CandidateComparisonResponse,
    DecisionAssessment,
    EvidenceGraphResponse,
    MultiDimensionalCandidateAssessment,
    RecruitmentTargetRequest,
    RecruitmentTargetResponse,
    ReplacementDecisionRequest,
    ReplacementDecisionResponse,
    TransferScenarioDecisionRequest,
    TransferScenarioDecisionResponse,
)


class UnifiedDecisionService:
    """Unified service layer for football decision intelligence and recruitment."""

    # In-memory store for quick decision auditing across the session
    _decision_cache: dict[uuid.UUID, DecisionAssessment] = {}

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.recruitment_engine = RecruitmentTargetEngine(session)
        self.replacement_engine = ReplacementDecisionEngine(session)
        self.scenario_engine = DecisionTransferScenarioEngine(session)

    async def analyze_recruitment_targets(
        self,
        request: RecruitmentTargetRequest,
        candidates_override: list[Any] | None = None,
    ) -> RecruitmentTargetResponse:
        """Executes recruitment targeting and caches the decision snapshot."""
        resp = await self.recruitment_engine.evaluate_recruitment(
            request, candidates_override=candidates_override
        )
        self._decision_cache[resp.decision.decision_id] = resp.decision
        return resp

    async def analyze_replacement(
        self,
        request: ReplacementDecisionRequest,
        target_player_override: Any | None = None,
        candidates_override: list[Any] | None = None,
    ) -> ReplacementDecisionResponse:
        """Executes player replacement analysis and caches the decision snapshot."""
        resp = await self.replacement_engine.evaluate_replacement(
            request,
            target_player_override=target_player_override,
            candidates_override=candidates_override,
        )
        self._decision_cache[resp.decision.decision_id] = resp.decision
        return resp

    async def simulate_transfer_scenario(
        self,
        request: TransferScenarioDecisionRequest,
    ) -> TransferScenarioDecisionResponse:
        """Executes transfer scenario simulation and caches the decision snapshot."""
        resp = await self.scenario_engine.evaluate_scenario(request)
        self._decision_cache[resp.decision.decision_id] = resp.decision
        return resp

    # Service aliases
    evaluate_recruitment = analyze_recruitment_targets
    evaluate_replacement = analyze_replacement
    evaluate_transfer_scenario = simulate_transfer_scenario

    async def compare_candidates(
        self,
        request: CandidateComparisonRequest,
        candidates_override: list[Any] | None = None,
    ) -> CandidateComparisonResponse:
        """Performs side-by-side comparison across all 6 analytical dimensions."""
        # Use recruitment engine to evaluate candidate universe
        rec_req = RecruitmentTargetRequest(
            target_position="MF",
            target_role=request.target_role or "Playmaker",
            tactical_context_id=request.tactical_context_id,
            limit=20,
        )
        rec_res = await self.recruitment_engine.evaluate_recruitment(
            rec_req, candidates_override=candidates_override
        )

        # Filter by candidate_ids if available, or take top N
        selected_candidates: list[MultiDimensionalCandidateAssessment] = []
        target_id_set = {str(cid) for cid in request.candidate_ids}

        for c in rec_res.top_recommendations:
            if str(c.candidate_id) in target_id_set or len(selected_candidates) < len(request.candidate_ids):
                selected_candidates.append(c)
                if len(selected_candidates) >= len(request.candidate_ids):
                    break

        # Compute dimension leaders
        leaders: dict[str, str] = {}
        if selected_candidates:
            leaders["tactical"] = max(selected_candidates, key=lambda x: x.tactical.tactical_fit_score).player_name
            leaders["performance"] = max(selected_candidates, key=lambda x: x.performance.contribution_rating).player_name
            leaders["value_opportunity"] = max(selected_candidates, key=lambda x: x.market.value_opportunity_index).player_name
            leaders["lowest_risk"] = min(selected_candidates, key=lambda x: x.risk.overall_risk_score).player_name

        # Trade-off analysis
        trade_offs = []
        for c in selected_candidates:
            trade_offs.append({
                "candidate_id": str(c.candidate_id),
                "player_name": c.player_name,
                "primary_strength": c.tactical.strengths[0] if c.tactical.strengths else "Consistent profile",
                "trade_off": c.risk.key_risk_drivers[0] if c.risk.key_risk_drivers else "Standard transfer exposure",
                "overall_fit_tier": c.confidence.confidence_tier,
            })

        return CandidateComparisonResponse(
            candidates=selected_candidates,
            trade_off_analysis=trade_offs,
            dimension_leaders=leaders,
        )

    def get_decision(self, decision_id: uuid.UUID) -> DecisionAssessment:
        """Retrieves a previously evaluated decision assessment from cache."""
        if decision_id not in self._decision_cache:
            raise ValueError(f"Decision with ID {decision_id} not found.")
        return self._decision_cache[decision_id]

    def get_decision_evidence(self, decision_id: uuid.UUID) -> EvidenceGraphResponse:
        """Retrieves the traceable evidence graph for a specific decision."""
        dec = self.get_decision(decision_id)
        if dec.evidence_graph is not None:
            return dec.evidence_graph

        if dec.candidates:
            return DecisionEvidenceGraphBuilder.build_graph_for_candidate(
                decision_id=decision_id,
                candidate=dec.candidates[0],
            )

        return EvidenceGraphResponse(decision_id=decision_id, nodes=[], edges=[])
