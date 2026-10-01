"""Unified Decision Intelligence Service (Phase 7, Phase 18 R12/R22).

Orchestrates recruitment, replacement, transfer scenarios and candidate
comparison. Analyses are persisted per organization (ops_decision_analyses)
when the caller is an authenticated principal; nothing lives in a
process-wide cache.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.decisions.candidate_evidence import assess, from_supplied, load_candidates
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
from app.tactical.contexts import get_standard_context


class DecisionNotFound(LookupError):
    pass


def _leader(cands: list[MultiDimensionalCandidateAssessment], value, lowest: bool = False) -> str | None:
    have = [(value(c), c.player_name) for c in cands if value(c) is not None]
    if not have:
        return None
    return (min if lowest else max)(have, key=lambda t: (t[0], t[1]))[1]


class UnifiedDecisionService:
    """Service layer for football decision intelligence and recruitment."""

    def __init__(self, session: AsyncSession | None = None, principal: Any | None = None) -> None:
        self.session = session
        self.principal = principal
        self.recruitment_engine = RecruitmentTargetEngine(session)
        self.replacement_engine = ReplacementDecisionEngine(session)
        self.scenario_engine = DecisionTransferScenarioEngine(session)

    async def _persist(self, decision: DecisionAssessment, response: BaseModel) -> None:
        if self.session is None or self.principal is None:
            return
        from app.db.models.operations import DecisionAnalysis

        payload = response.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        org = self.principal.organization_id
        exists = (await self.session.execute(select(DecisionAnalysis.id).where(
            DecisionAnalysis.organization_id == org, DecisionAnalysis.decision_id == decision.decision_id,
            DecisionAnalysis.content_sha256 == digest))).first()
        if exists is None:
            self.session.add(DecisionAnalysis(organization_id=org, user_id=self.principal.id,
                                              decision_id=decision.decision_id, decision_type=decision.decision_type,
                                              as_of=decision.as_of, payload=payload, content_sha256=digest))
            await self.session.commit()

    async def analyze_recruitment_targets(
        self,
        request: RecruitmentTargetRequest,
        candidates_override: list[Any] | None = None,
    ) -> RecruitmentTargetResponse:
        resp = await self.recruitment_engine.evaluate_recruitment(request, candidates_override=candidates_override)
        await self._persist(resp.decision, resp)
        return resp

    async def analyze_replacement(
        self,
        request: ReplacementDecisionRequest,
        target_player_override: Any | None = None,
        candidates_override: list[Any] | None = None,
    ) -> ReplacementDecisionResponse:
        resp = await self.replacement_engine.evaluate_replacement(
            request, target_player_override=target_player_override, candidates_override=candidates_override)
        await self._persist(resp.decision, resp)
        return resp

    async def simulate_transfer_scenario(
        self,
        request: TransferScenarioDecisionRequest,
    ) -> TransferScenarioDecisionResponse:
        resp = await self.scenario_engine.evaluate_scenario(request)
        await self._persist(resp.decision, resp)
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
        """Exactly the requested candidates, side by side. A requested id with
        no record is reported in not_found_candidate_ids, never substituted."""
        as_of = request.as_of or datetime.now(timezone.utc)
        wanted = list(dict.fromkeys(request.candidate_ids))
        if candidates_override is not None:
            pool = {c.candidate_id: c for c in map(from_supplied, candidates_override)}
        elif self.session is not None:
            pool = {c.candidate_id: c for c in await load_candidates(
                self.session, as_of, request.tactical_context_id, player_ids=wanted)}
        else:
            pool = {}
        ctx = get_standard_context(request.tactical_context_id) if request.tactical_context_id else None
        system_name = ctx.context_id if ctx else (request.tactical_context_id or "UNSPECIFIED")
        role = request.target_role or (ctx.target_role if ctx else None) or "UNSPECIFIED"

        selected = [
            assess(pool[cid], target_position=pool[cid].position or "UNKNOWN", target_role=role, system_name=system_name,
                   min_age=None, max_age=None, min_minutes=None, budget_eur=None, risk_tolerance="ALL")
            for cid in wanted if cid in pool
        ]
        leaders = {k: v for k, v in {
            "tactical": _leader(selected, lambda c: c.tactical.tactical_fit_score if c.tactical else None),
            "performance": _leader(selected, lambda c: c.performance.contribution_rating if c.performance else None),
            "value_opportunity": _leader(selected, lambda c: c.market.value_opportunity_index if c.market else None),
            "lowest_risk": _leader(selected, lambda c: c.risk.overall_risk_score if c.risk else None, lowest=True),
        }.items() if v is not None}
        trade_offs = [{
            "candidate_id": str(c.candidate_id),
            "player_name": c.player_name,
            "primary_strength": c.tactical.strengths[0] if c.tactical and c.tactical.strengths else None,
            "trade_off": c.risk.key_risk_drivers[0] if c.risk and c.risk.key_risk_drivers else None,
            "dimension_status": c.dimension_status,
            "overall_fit_tier": c.confidence.confidence_tier,
        } for c in selected]
        return CandidateComparisonResponse(
            candidates=selected,
            not_found_candidate_ids=[cid for cid in wanted if cid not in pool],
            trade_off_analysis=trade_offs,
            dimension_leaders=leaders,
        )

    async def get_decision(self, decision_id: uuid.UUID) -> dict[str, Any]:
        """The analysis exactly as served, for the caller's organization only."""
        if self.session is None or self.principal is None:
            raise DecisionNotFound(f"Decision {decision_id} not found.")
        from app.db.models.operations import DecisionAnalysis

        row = (await self.session.execute(
            select(DecisionAnalysis).where(DecisionAnalysis.decision_id == decision_id,
                                           DecisionAnalysis.organization_id == self.principal.organization_id)
            .order_by(DecisionAnalysis.created_at.desc()).limit(1))).scalar_one_or_none()
        if row is None:
            raise DecisionNotFound(f"Decision {decision_id} not found.")
        return {"decision_id": str(row.decision_id), "decision_type": row.decision_type,
                "as_of": row.as_of.isoformat(), "stored_at": row.created_at.isoformat(),
                "content_sha256": row.content_sha256, "analysis": row.payload}

    async def get_decision_evidence(self, decision_id: uuid.UUID) -> EvidenceGraphResponse:
        stored = await self.get_decision(decision_id)
        graph = stored["analysis"].get("decision", {}).get("evidence_graph")
        if graph is None:
            return EvidenceGraphResponse(decision_id=decision_id, nodes=[], edges=[])
        return EvidenceGraphResponse.model_validate(graph)
