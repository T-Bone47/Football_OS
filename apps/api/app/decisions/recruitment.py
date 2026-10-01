"""Recruitment Target Engine (Phase 7.2, rebuilt in Phase 18 for R22/R23).

Pipeline:
1. Resolve the requested slot, role and tactical context.
2. Load the candidate universe: players with stored evidence (or the
   caller-supplied candidates), read at `as_of`.
3. Apply hard constraints to observed values; an unknown value never passes
   a constraint the request sets.
4. Assess each dimension from stored evidence only (candidate_evidence).
5. Rank only candidates with enough evidence (hard constraints passed,
   performance and tactical fit present). The rest are listed as
   INSUFFICIENT_EVIDENCE and never recommended.

Nothing is invented: no default age, minutes, ratings, prices or squad depth.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.decisions.candidate_evidence import assess, from_supplied, load_candidates, no_evidence_confidence
from app.decisions.evidence import DecisionEvidenceGraphBuilder
from app.decisions.schemas import (
    DecisionAssessment,
    MultiDimensionalCandidateAssessment,
    RecruitmentTargetRequest,
    RecruitmentTargetResponse,
)
from app.tactical.contexts import get_standard_context


def rank(assessments: list[MultiDimensionalCandidateAssessment]) -> list[MultiDimensionalCandidateAssessment]:
    """Deterministic: score descending, then name and id."""
    return sorted(assessments, key=lambda a: (-(a.ranking_score or 0.0), a.player_name, str(a.candidate_id)))


class RecruitmentTargetEngine:
    """Recruitment targeting over stored, point-in-time evidence."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def evaluate_recruitment(
        self,
        request: RecruitmentTargetRequest,
        candidates_override: Sequence[Any] | None = None,
    ) -> RecruitmentTargetResponse:
        as_of = request.as_of or datetime.now(timezone.utc)
        if request.as_of:
            seed_key = (f"recruitment:{request.target_position}:{request.target_role}:{request.tactical_context_id}:"
                        f"{request.budget_eur}:{request.as_of.isoformat()}")
            decision_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_key)
        else:
            decision_id = uuid.uuid4()

        target_pos = request.target_position.upper()
        ctx = get_standard_context(request.tactical_context_id) if request.tactical_context_id else None
        system_name = ctx.context_id if ctx else (request.tactical_context_id or request.formation)
        role = request.target_role or (ctx.target_role if ctx else None) or "UNSPECIFIED"

        if candidates_override is not None:
            universe = [from_supplied(o) for o in candidates_override]
            source = "CALLER_SUPPLIED"
        elif self.session is not None:
            universe = await load_candidates(self.session, as_of, request.tactical_context_id)
            source = "CANONICAL_DATABASE"
        else:
            universe, source = [], "NONE"

        ranked: list[MultiDimensionalCandidateAssessment] = []
        insufficient: list[MultiDimensionalCandidateAssessment] = []
        excluded: list[dict[str, Any]] = []
        for c in universe:
            a = assess(c, target_position=target_pos, target_role=role, system_name=system_name,
                       min_age=request.min_age, max_age=request.max_age, min_minutes=request.min_minutes,
                       budget_eur=request.budget_eur, risk_tolerance=request.risk_tolerance)
            if not a.hard_constraints.passed:
                excluded.append({"candidate_id": str(a.candidate_id), "player_name": a.player_name,
                                 "exclusion_reasons": a.hard_constraints.exclusion_reasons})
            elif a.ranking_status == "RANKED":
                ranked.append(a)
            else:
                insufficient.append(a)

        top = rank(ranked)[:request.limit]
        insufficient = sorted(insufficient, key=lambda a: (a.player_name, str(a.candidate_id)))[:request.limit]
        graph = (DecisionEvidenceGraphBuilder.build_graph_for_candidate(decision_id=decision_id, candidate=top[0],
                                                                         as_of=as_of) if top else None)
        if top:
            status = "RANKED"
        elif insufficient:
            status = "INSUFFICIENT_EVIDENCE"
        else:
            status = "NO_ELIGIBLE_CANDIDATES"
        reason = {
            "INSUFFICIENT_EVIDENCE": "Candidates passed the hard constraints but none has stored performance and "
                                     "tactical-fit evidence; none is ranked.",
            "NO_ELIGIBLE_CANDIDATES": "No candidate in the evaluated universe passed the hard constraints.",
        }.get(status)

        decision = DecisionAssessment(
            decision_id=decision_id, decision_type="RECRUITMENT", subject_type="POSITION", as_of=as_of,
            summary=(f"{len(universe)} candidate(s) evaluated for {target_pos} ({role}); {len(ranked)} ranked, "
                     f"{len(universe) - len(ranked) - len(excluded)} with insufficient evidence, "
                     f"{len(excluded)} excluded by hard constraints."),
            total_candidates_analyzed=len(universe),
            passed_candidates_count=len(ranked),
            excluded_candidates_count=len(excluded),
            candidates=top,
            confidence=top[0].confidence if top else no_evidence_confidence(reason),
            evidence_graph=graph,
            evidence_hash=graph.evidence_hash if graph else "",
            provenance={"tactical_context": system_name, "target_position": target_pos, "target_role": role,
                        "budget_eur": request.budget_eur, "candidate_source": source, "status": status},
        )
        return RecruitmentTargetResponse(decision=decision, status=status, top_recommendations=top,
                                         insufficient_evidence=insufficient, excluded_summaries=excluded)
