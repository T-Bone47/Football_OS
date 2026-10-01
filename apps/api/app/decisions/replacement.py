"""Replacement Intelligence Engine (Phase 7.5, rebuilt in Phase 18 for R22/R23).

'Replace PLAYER_X': candidates in the same position group are compared with
the replaced player through their stored, QUALIFIED role profiles. A
candidate without a comparable profile has no similarity and is never
recommended. No hidden constraints are applied: only those the request sets.

Strictly non-causal: a similar profile does not guarantee similar outcomes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.decisions.candidate_evidence import (
    assess,
    from_supplied,
    load_candidates,
    no_evidence_confidence,
    role_similarity,
)
from app.decisions.evidence import DecisionEvidenceGraphBuilder
from app.decisions.recruitment import rank
from app.decisions.schemas import (
    DecisionAssessment,
    MultiDimensionalCandidateAssessment,
    ReplacementDecisionRequest,
    ReplacementDecisionResponse,
)
from app.tactical.contexts import get_standard_context


class ReplacementDecisionEngine:
    """Replacement analysis over stored, point-in-time evidence."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def evaluate_replacement(
        self,
        request: ReplacementDecisionRequest,
        target_player_override: Any | None = None,
        candidates_override: Sequence[Any] | None = None,
    ) -> ReplacementDecisionResponse:
        as_of = request.as_of or datetime.now(timezone.utc)
        if request.as_of:
            seed_key = (f"replacement:{request.player_id_to_replace}:{request.target_role}:"
                        f"{request.tactical_context_id}:{request.budget_eur}:{request.as_of.isoformat()}")
            decision_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_key)
        else:
            decision_id = uuid.uuid4()

        if target_player_override is not None:
            target = from_supplied(target_player_override)
        elif self.session is not None:
            found = await load_candidates(self.session, as_of, request.tactical_context_id,
                                          player_ids=[request.player_id_to_replace], assess_risk=False)
            target = found[0] if found else None
        else:
            target = None
        if target is None:
            raise ValueError(f"Player with ID {request.player_id_to_replace} not found.")

        ctx = get_standard_context(request.tactical_context_id) if request.tactical_context_id else None
        system_name = ctx.context_id if ctx else (request.tactical_context_id or request.formation)
        role = request.target_role or (ctx.target_role if ctx else None) or "UNSPECIFIED"

        if candidates_override is not None:
            universe = [from_supplied(o) for o in candidates_override]
        elif self.session is not None:
            universe = await load_candidates(self.session, as_of, request.tactical_context_id)
        else:
            universe = []
        universe = [c for c in universe if c.candidate_id != target.candidate_id]

        ranked: list[MultiDimensionalCandidateAssessment] = []
        insufficient: list[MultiDimensionalCandidateAssessment] = []
        excluded: list[dict[str, Any]] = []
        for c in universe:
            if target.position is None:
                excluded.append({"candidate_id": str(c.candidate_id), "player_name": c.name,
                                 "exclusion_reasons": [f"Position of {target.name} UNKNOWN: the slot cannot be matched."]})
                continue
            sim = role_similarity(target, c)
            a = assess(c, target_position=target.position, target_role=role, system_name=system_name,
                       min_age=None, max_age=None, min_minutes=None, budget_eur=request.budget_eur,
                       risk_tolerance="ALL", similarity=sim)
            if not a.hard_constraints.passed:
                excluded.append({"candidate_id": str(a.candidate_id), "player_name": a.player_name,
                                 "exclusion_reasons": a.hard_constraints.exclusion_reasons})
                continue
            if a.similarity is None:
                insufficient.append(a.model_copy(update={"ranking_status": "INSUFFICIENT_EVIDENCE", "ranking_score": None}))
                continue
            if a.similarity.overall_similarity < request.min_similarity:
                excluded.append({"candidate_id": str(a.candidate_id), "player_name": a.player_name,
                                 "exclusion_reasons": [f"Similarity {a.similarity.overall_similarity:.2f} is below the "
                                                       f"minimum {request.min_similarity:.2f}."]})
                continue
            ranked.append(a.model_copy(update={"ranking_status": "RANKED",
                                               "ranking_score": a.similarity.overall_similarity}))

        top = rank(ranked)[:request.limit]
        insufficient = sorted(insufficient, key=lambda a: (a.player_name, str(a.candidate_id)))[:request.limit]
        graph = (DecisionEvidenceGraphBuilder.build_graph_for_candidate(
            decision_id=decision_id, candidate=top[0], replaced_player_name=target.name, as_of=as_of) if top else None)
        status = "RANKED" if top else ("INSUFFICIENT_EVIDENCE" if insufficient else "NO_ELIGIBLE_CANDIDATES")
        reason = (f"No candidate has a QUALIFIED role profile comparable with {target.name}'s."
                  if status == "INSUFFICIENT_EVIDENCE" else "No candidate passed the hard constraints and similarity floor.")

        decision = DecisionAssessment(
            decision_id=decision_id, decision_type="REPLACEMENT", subject_type="PLAYER",
            subject_id=request.player_id_to_replace, as_of=as_of,
            summary=(f"{len(universe)} candidate(s) evaluated as replacements for {target.name}; {len(ranked)} ranked "
                     f"by stored role-profile similarity, {len(insufficient)} without comparable profiles, "
                     f"{len(excluded)} excluded."),
            total_candidates_analyzed=len(universe),
            passed_candidates_count=len(ranked),
            excluded_candidates_count=len(excluded),
            candidates=top,
            confidence=top[0].confidence if top else no_evidence_confidence(reason),
            evidence_graph=graph,
            evidence_hash=graph.evidence_hash if graph else "",
            provenance={"replaced_player_name": target.name, "replaced_player_id": str(request.player_id_to_replace),
                        "replaced_player_position": target.position, "target_role": role, "status": status,
                        "similarity_basis": "stored QUALIFIED role profiles (feature vector + profile scores)"},
        )
        return ReplacementDecisionResponse(
            replaced_player_id=request.player_id_to_replace, replaced_player_name=target.name,
            replaced_player_role=role, status=status, decision=decision, top_replacements=top,
            insufficient_evidence=insufficient, excluded_summaries=excluded,
        )
