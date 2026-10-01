"""Scout Copilot decision tools and orchestrator (Phase 7, Phase 18 grounding).

Every statement the orchestrator streams is rendered from an engine output;
a missing dimension is rendered as its status (INSUFFICIENT_DATA,
MODEL_UNVERIFIED, NOT_ASSESSED...), never as a number. No constraint the
user did not state is added to a request (no default budget, role or
similarity floor beyond the request schema's documented default).

Tools are read-only and deterministic:
- get_player_intelligence: stored evidence statuses for one player
- get_valuation: the registry's decision for the valuation model
- get_match_prediction: a registry-gated inference (logged)
- simulate_transfer, compare_candidates, retrieve_evidence
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.decisions.candidate_evidence import assess, load_candidates
from app.decisions.schemas import (
    CandidateComparisonRequest,
    MultiDimensionalCandidateAssessment,
    RecruitmentTargetRequest,
    ReplacementDecisionRequest,
    TransferScenarioDecisionRequest,
)
from app.decisions.service import DecisionNotFound, UnifiedDecisionService

logger = logging.getLogger(__name__)

NO_DATABASE = {"status": "NOT_AVAILABLE", "reason": "no database session"}


class ScoutDecisionTools:
    """Deterministic, read-only tool registry for decision intelligence queries."""

    def __init__(self, session: AsyncSession | None = None, principal: Any | None = None) -> None:
        self.session = session
        self.decision_service = UnifiedDecisionService(session=session, principal=principal)

    async def get_player_intelligence(self, player_id: uuid.UUID | str) -> dict[str, Any]:
        """Which evidence is stored for the player at now (and which is not)."""
        if self.session is None:
            return NO_DATABASE
        found = await load_candidates(self.session, datetime.now(timezone.utc), player_ids=[uuid.UUID(str(player_id))])
        if not found:
            return {"status": "NOT_FOUND", "player_id": str(player_id)}
        c = found[0]
        a = assess(c, target_position=c.position or "UNKNOWN", target_role="UNSPECIFIED", system_name="UNSPECIFIED",
                   min_age=None, max_age=None, min_minutes=None, budget_eur=None, risk_tolerance="ALL")
        return {"status": "OK", "player_id": str(c.candidate_id), "name": c.name, "position": c.position,
                "age": c.age, "minutes": c.minutes, "appearances": c.appearances,
                "appearances_basis": c.appearances_basis, "dimension_status": a.dimension_status}

    async def get_valuation(self, player_id: uuid.UUID | str) -> dict[str, Any]:
        """The valuation model is served only if the registry allows it."""
        if self.session is None:
            return NO_DATABASE
        from app.ml.valuation_registry import ModelNotServable, register_valuation_model, valuation_gate

        entry = await register_valuation_model(self.session)
        try:
            await valuation_gate(self.session, entry.model_id if entry else None)
        except ModelNotServable as exc:
            return {"player_id": str(player_id), **exc.body()}
        return {"player_id": str(player_id), "status": "SERVABLE",
                "detail": "use GET /api/v1/players/{id}/valuation"}

    async def get_match_prediction(self, match_id: uuid.UUID | str) -> dict[str, Any]:
        """A registry-gated inference; a refusal is returned (and logged) as is."""
        if self.session is None:
            return NO_DATABASE
        from app.phase17.model_ops import infer_match
        from app.api.routes_phase17 import inference_dict

        log = await infer_match(self.session, uuid.UUID(str(match_id)))
        await self.session.commit()
        return inference_dict(log)

    async def simulate_transfer(self, request: TransferScenarioDecisionRequest) -> dict[str, Any]:
        """COUNTERFACTUAL roster change on the club's stored roster."""
        return (await self.decision_service.evaluate_transfer_scenario(request)).model_dump(mode="json")

    async def compare_candidates(self, candidate_ids: list[uuid.UUID | str]) -> dict[str, Any]:
        req = CandidateComparisonRequest(candidate_ids=[uuid.UUID(str(cid)) for cid in candidate_ids])
        return (await self.decision_service.compare_candidates(req)).model_dump(mode="json")

    async def retrieve_evidence(self, decision_id: uuid.UUID | str) -> dict[str, Any]:
        try:
            ev = await self.decision_service.get_decision_evidence(uuid.UUID(str(decision_id)))
            return ev.model_dump(mode="json")
        except (DecisionNotFound, ValueError) as e:
            return {"status": "NOT_FOUND", "error": str(e)}


def _cell(c: MultiDimensionalCandidateAssessment, dim: str, render) -> str:
    value = getattr(c, dim)
    return render(value) if value is not None else c.dimension_status.get(dim, "NOT_ASSESSED")


def _budget_from_query(q: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*m\b", q)
    return float(m.group(1)) * 1_000_000 if m else None


async def orchestrate_copilot_decision(
    query: str,
    context_players: list[dict[str, Any]],
    session: AsyncSession | None = None,
    principal: Any | None = None,
) -> AsyncGenerator[str, None]:
    """Routes the question to a decision engine and streams markdown rendered
    only from that engine's output."""
    tools = ScoutDecisionTools(session=session, principal=principal)
    service = tools.decision_service
    q_lower = query.lower()
    budget = _budget_from_query(q_lower)

    yield "### 🎯 Decision Intelligence Analysis\n\n"

    if "replace" in q_lower or "replacement" in q_lower:
        target_player = context_players[0] if context_players else None
        target_id = (target_player or {}).get("candidate_id") or (target_player or {}).get("id")
        if not target_id:
            yield "**Status**: NO_TARGET — select the player to replace (context with a player id).\n"
            yield "No candidate met both the minimum similarity threshold and all hard criteria: nothing was evaluated.\n"
            return
        req = ReplacementDecisionRequest(player_id_to_replace=uuid.UUID(str(target_id)), budget_eur=budget, limit=3)
        supplied = context_players[1:] if len(context_players) > 1 else None
        use_context = supplied is not None or session is None  # else both come from the database
        try:
            res = await service.evaluate_replacement(
                req, target_player_override=target_player if use_context else None,
                candidates_override=(supplied or []) if use_context else None)
        except ValueError as exc:
            yield f"**Status**: NOT_FOUND — {exc}\n"
            return
        yield f"**Objective**: replacement candidates for **{res.replaced_player_name}**.\n\n"
        yield f"**Status**: {res.status}. {res.decision.summary}\n\n"
        if res.top_replacements:
            yield "| Candidate | Similarity | Tactical Fit | Valuation | Risk |\n|---|---|---|---|---|\n"
            for c in res.top_replacements:
                yield (f"| **{c.player_name}** | {_cell(c, 'similarity', lambda v: f'{v.overall_similarity:.2f}')} | "
                       f"{_cell(c, 'tactical', lambda v: f'{v.tactical_fit_score:.1f}%')} | "
                       f"{_cell(c, 'market', lambda v: f'€{v.estimated_value_eur:,.0f}')} | "
                       f"{_cell(c, 'risk', lambda v: v.risk_level)} |\n")
            yield "\n**Evidence**:\n"
            for c in res.top_replacements[:2]:
                yield f"- **{c.player_name}**: {'; '.join(c.why_matches) or 'none recorded'}\n"
                if c.where_differs:
                    yield f"  *Not established*: {'; '.join(c.where_differs)}\n"
        else:
            yield ("No candidate met both the minimum similarity threshold "
                   f"({req.min_similarity:.2f}) and all hard criteria with stored evidence.\n")
        yield f"\n*Decision Confidence*: **{res.decision.confidence.confidence_tier}**. Evidence graph ID: `{res.decision.decision_id}`.\n"
        return

    if "compare" in q_lower or " vs" in q_lower:
        cids = [p.get("candidate_id") or p.get("id") for p in context_players[:5]]
        cids = [c for c in cids if c]
        if len(cids) < 2:
            yield "**Status**: NEEDS_TWO_PLAYERS — a comparison needs at least two player ids in context.\n"
            return
        req = CandidateComparisonRequest(candidate_ids=[uuid.UUID(str(c)) for c in cids])
        res = await service.compare_candidates(req, candidates_override=context_players if session is None else None)
        yield f"**Objective**: side-by-side comparison of {len(res.candidates)} candidate(s).\n\n"
        if res.not_found_candidate_ids:
            yield f"*Not found*: {', '.join(str(i) for i in res.not_found_candidate_ids)}\n\n"
        if res.candidates:
            yield "| Dimension | " + " | ".join(c.player_name for c in res.candidates) + " |\n"
            yield "|---|" + "|".join("---" for _ in res.candidates) + "|\n"
            rows = [("Tactical Fit", "tactical", lambda v: f"{v.tactical_fit_score:.1f}%"),
                    ("Contribution Rating", "performance", lambda v: f"{v.contribution_rating:.1f}"),
                    ("Estimated Valuation", "market", lambda v: f"€{v.estimated_value_eur:,.0f}"),
                    ("Transfer Risk", "risk", lambda v: v.risk_level)]
            for label, dim, render in rows:
                yield f"| **{label}** | " + " | ".join(_cell(c, dim, render) for c in res.candidates) + " |\n"
        if res.dimension_leaders:
            yield "\n*Dimension leaders (among candidates with that evidence)*: " + ", ".join(
                f"{k.replace('_', ' ')}: {v}" for k, v in res.dimension_leaders.items()) + "\n"
        yield "\n*Note*: trade-offs are shown per dimension; no single winner is declared.\n"
        return

    pos = "CM" if "midfield" in q_lower else ("CB" if "centre-back" in q_lower or "defender" in q_lower else "FW")
    yield "**Objective**: recruitment targeting search.\n\n"
    yield f"Constraints applied: position `{pos}`" + (f", budget ceiling `€{budget:,.0f}`" if budget else "") + ".\n\n"
    req = RecruitmentTargetRequest(target_position=pos, budget_eur=budget, limit=5)
    res = await service.evaluate_recruitment(req, candidates_override=context_players if context_players or session is None else None)
    yield f"**Status**: {res.status}. {res.decision.summary}\n\n"
    if res.top_recommendations:
        yield "| Player | Tactical Fit | Contribution | Valuation | Risk |\n|---|---|---|---|---|\n"
        for c in res.top_recommendations:
            yield (f"| **{c.player_name}** | {_cell(c, 'tactical', lambda v: f'{v.tactical_fit_score:.1f}%')} | "
                   f"{_cell(c, 'performance', lambda v: f'{v.contribution_rating:.1f}')} | "
                   f"{_cell(c, 'market', lambda v: f'€{v.estimated_value_eur:,.0f}')} | "
                   f"{_cell(c, 'risk', lambda v: v.risk_level)} |\n")
        yield "\n**Evidence**:\n"
        for c in res.top_recommendations[:2]:
            yield f"- **{c.player_name}**: {'; '.join(c.why_matches)}\n"
    elif res.insufficient_evidence:
        yield (f"{len(res.insufficient_evidence)} candidate(s) passed the hard constraints but lack stored performance "
               "and tactical-fit evidence; none is ranked.\n")
    else:
        yield "No candidates satisfied all hard constraints.\n"
    if res.excluded_summaries:
        yield f"\n*Excluded*: {len(res.excluded_summaries)} candidate(s) by hard constraints (reasons are in the analysis).\n"
    yield f"\nEvidence graph ID: `{res.decision.decision_id}`.\n"
