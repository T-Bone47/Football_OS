"""Candidate evidence for recruitment, replacement and comparison (Phase 18, R22/R23).

The old engines filled every gap with an invented number: age 24, 900
minutes, contribution 68 + minutes/100, tactical fit 72, a cohort price,
squad depth "THIN -> HEALTHY". This module only reports what is stored:

- OBSERVED: provider facts (date of birth, position, reported minutes and
  appearances, lineup appearances, club).
- MODELLED: computed evidence already persisted with its own as_of
  (contribution snapshots, tactical fits, role profiles, risk assessment).
- SUPPLIED: a dimension the caller passed in (its provenance is the caller's).
- INSUFFICIENT_DATA / UNKNOWN / MODEL_UNVERIFIED / NOT_ASSESSED: anything else.

Nothing dated after `as_of` is read.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import (
    Club,
    Match,
    MatchLineup,
    Player,
    PlayerContributionSnapshot,
    PlayerRoleProfile,
    PlayerSeasonStats,
    PlayerTacticalFit,
)
from app.decisions.confidence import DecisionConfidenceEngine
from app.decisions.hard_constraints import HardConstraintsEngine
from app.decisions.schemas import (
    DimensionMarket,
    DimensionPerformance,
    DimensionRisk,
    DimensionSimilarity,
    DimensionSquadImpact,
    DimensionTactical,
    MultiDimensionalCandidateAssessment,
)
from app.roles.registry import DIMENSIONS as ROLE_DIMENSIONS

OBSERVED, MODELLED, SUPPLIED = "OBSERVED", "MODELLED", "SUPPLIED"
INSUFFICIENT, UNKNOWN, UNVERIFIED, NOT_ASSESSED = "INSUFFICIENT_DATA", "UNKNOWN", "MODEL_UNVERIFIED", "NOT_ASSESSED"
DIMENSION_MODELS = {
    "performance": DimensionPerformance, "tactical": DimensionTactical, "similarity": DimensionSimilarity,
    "market": DimensionMarket, "risk": DimensionRisk, "squad_impact": DimensionSquadImpact,
}
DIMENSIONS = tuple(DIMENSION_MODELS)
MIN_SHARED_FEATURES = 3


@dataclass
class CandidateEvidence:
    candidate_id: uuid.UUID
    name: str
    position: str | None = None
    age: float | None = None
    club_id: uuid.UUID | None = None
    club_name: str | None = None
    minutes: int | None = None            # sum of provider-reported minutes; None if none reported
    appearances: int | None = None        # reported appearances, else lineup rows
    appearances_basis: str | None = None
    contribution: PlayerContributionSnapshot | None = None
    tactical: PlayerTacticalFit | None = None
    role_profile: PlayerRoleProfile | None = None
    risk: Any | None = None               # TransferRiskProfile
    supplied: dict[str, Any] = field(default_factory=dict)  # dimensions passed in by the caller


def _get(obj: Any, *names: str) -> Any:
    for n in names:
        v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
        if v is not None:
            return v
    return None


def from_supplied(obj: Any) -> CandidateEvidence:
    """A caller-supplied candidate. Missing fields stay missing."""
    supplied = {d: (DIMENSION_MODELS[d].model_validate(v) if isinstance(v, dict) else v)
                for d in DIMENSIONS if (v := _get(obj, d)) is not None}
    cid = _get(obj, "candidate_id", "id")
    return CandidateEvidence(
        candidate_id=uuid.UUID(str(cid)) if cid is not None else uuid.uuid4(),
        name=_get(obj, "player_name", "full_name", "name") or "UNKNOWN",
        position=_get(obj, "primary_position"), age=_get(obj, "age"),
        club_id=_get(obj, "club_id"), club_name=_get(obj, "club_name"),
        minutes=_get(obj, "minutes_played"), appearances=_get(obj, "matches_played"),
        appearances_basis="SUPPLIED" if _get(obj, "matches_played") is not None else None,
        supplied=supplied,
    )


def _age(dob, as_of: datetime) -> float | None:
    return round((as_of.date() - dob).days / 365.25, 1) if dob else None


async def _latest_per_player(session: AsyncSession, model, ids: list[uuid.UUID], as_of: datetime, *where) -> dict:
    """The latest row per player with model.as_of <= as_of (one query)."""
    if not ids:
        return {}
    rows = (await session.execute(
        select(model).where(model.player_id.in_(ids), model.as_of <= as_of, *where)
        .order_by(model.player_id, model.as_of.desc()).distinct(model.player_id))).scalars().all()
    return {r.player_id: r for r in rows}


async def load_candidates(session: AsyncSession, as_of: datetime, tactical_context_id: str | None = None,
                          player_ids: Sequence[uuid.UUID] | None = None, limit: int = 5000,
                          assess_risk: bool = True) -> list[CandidateEvidence]:
    """Players with any stored evidence at as_of (season stats, lineup rows in
    matches at or before as_of, contribution snapshots, tactical fits), or
    exactly `player_ids`. Observed facts plus the latest modelled evidence
    dated at or before as_of. Batched: a fixed number of queries."""
    if player_ids is not None:
        players = (await session.execute(select(Player).where(Player.id.in_(list(player_ids))))).scalars().all()
    else:
        universe = select(PlayerSeasonStats.player_id).union(
            select(MatchLineup.player_id).join(Match, Match.id == MatchLineup.match_id).where(Match.date <= as_of),
            select(PlayerContributionSnapshot.player_id).where(PlayerContributionSnapshot.as_of <= as_of),
            select(PlayerTacticalFit.player_id).where(PlayerTacticalFit.as_of <= as_of),
        ).subquery()
        players = (await session.execute(select(Player).where(Player.id.in_(select(universe)))
                                         .order_by(Player.name, Player.id).limit(limit))).scalars().all()
    ids = [p.id for p in players]
    if not ids:
        return []

    stats: dict[uuid.UUID, list] = {}
    for st, club in (await session.execute(
            select(PlayerSeasonStats, Club).outerjoin(Club, Club.id == PlayerSeasonStats.club_id)
            .where(PlayerSeasonStats.player_id.in_(ids)).order_by(PlayerSeasonStats.created_at.desc()))).all():
        stats.setdefault(st.player_id, []).append((st, club))
    lineup_counts = dict((await session.execute(
        select(MatchLineup.player_id, func.count(MatchLineup.id)).join(Match, Match.id == MatchLineup.match_id)
        .where(MatchLineup.player_id.in_(ids), Match.date <= as_of).group_by(MatchLineup.player_id))).all())
    last_club = {pid: (cid, name) for pid, cid, name in (await session.execute(
        select(MatchLineup.player_id, Club.id, Club.name).join(Match, Match.id == MatchLineup.match_id)
        .join(Club, Club.id == MatchLineup.club_id)
        .where(MatchLineup.player_id.in_(ids), Match.date <= as_of)
        .order_by(MatchLineup.player_id, Match.date.desc()).distinct(MatchLineup.player_id))).all()}
    contributions = await _latest_per_player(session, PlayerContributionSnapshot, ids, as_of)
    fits = (await _latest_per_player(session, PlayerTacticalFit, ids, as_of,
                                     PlayerTacticalFit.tactical_context_id == tactical_context_id)
            if tactical_context_id else {})
    roles = await _latest_per_player(session, PlayerRoleProfile, ids, as_of)

    out: list[CandidateEvidence] = []
    for p in players:
        c = CandidateEvidence(candidate_id=p.id, name=p.name, position=p.primary_position, age=_age(p.date_of_birth, as_of))
        rows = stats.get(p.id, [])
        reported_min = [st.minutes for st, _ in rows if st.minutes is not None]
        reported_app = [st.appearances for st, _ in rows if st.appearances is not None]
        c.minutes = sum(reported_min) if reported_min else None
        if reported_app:
            c.appearances, c.appearances_basis = sum(reported_app), "PROVIDER_SEASON_STATS"
        elif lineup_counts.get(p.id):
            c.appearances, c.appearances_basis = int(lineup_counts[p.id]), "LINEUP_ROWS"
        if rows and rows[0][1] is not None:
            c.club_id, c.club_name = rows[0][1].id, rows[0][1].name
        elif p.id in last_club:
            c.club_id, c.club_name = last_club[p.id]
        c.contribution, c.tactical, c.role_profile = contributions.get(p.id), fits.get(p.id), roles.get(p.id)
        # Risk can only reach the two scored dimensions it needs with season
        # stats or a contribution sample; otherwise it is INSUFFICIENT_DATA
        # without running the engine.
        if assess_risk and (rows or c.contribution is not None):
            from app.market.risk import TransferRiskEngine

            try:
                c.risk = await TransferRiskEngine().assess_player_risk(session, p.id)
            except Exception:  # noqa: BLE001 - risk stays unknown, it is never invented
                c.risk = None
        out.append(c)
    return out


def _performance(c: CandidateEvidence) -> tuple[DimensionPerformance | None, str]:
    if "performance" in c.supplied:
        return c.supplied["performance"], SUPPLIED
    snap = c.contribution
    if snap is None:
        return None, INSUFFICIENT
    scored = {k: v.get("score") for k, v in (snap.dimension_scores or {}).items()
              if isinstance(v, dict) and v.get("score") is not None}
    if snap.contribution_status != "EVALUATED" or not scored:
        return None, INSUFFICIENT
    rating = round(sum(scored.values()) / len(scored), 1)
    pcts = [v.get("percentile") for v in snap.dimension_scores.values() if isinstance(v, dict) and v.get("percentile") is not None]
    return DimensionPerformance(
        contribution_rating=max(0.0, min(100.0, rating)),
        percentile_in_role=round(sum(pcts) / len(pcts), 1) if pcts else None,
        offensive_impact=None, defensive_impact=None, trajectory="UNKNOWN",
        sample_minutes=snap.sample_minutes, sample_matches=snap.sample_matches,
    ), MODELLED


def _tactical(c: CandidateEvidence, system_name: str, target_role: str) -> tuple[DimensionTactical | None, str]:
    if "tactical" in c.supplied:
        return c.supplied["tactical"], SUPPLIED
    fit = c.tactical
    if fit is None or fit.fit_status == "INSUFFICIENT_DATA":
        return None, INSUFFICIENT
    return DimensionTactical(
        tactical_fit_score=round(fit.fit_score * 100.0 if fit.fit_score <= 1.0 else fit.fit_score, 1),
        role_compatibility=round(fit.role_fit * 100.0 if fit.role_fit <= 1.0 else fit.role_fit, 1),
        system_name=fit.tactical_context_id or system_name, target_role=fit.target_role or target_role,
        strengths=list(fit.why_fit or []), vulnerabilities=list(fit.why_not_fit or []),
    ), MODELLED


def _risk(c: CandidateEvidence) -> tuple[DimensionRisk | None, str]:
    if "risk" in c.supplied:
        return c.supplied["risk"], SUPPLIED
    prof = c.risk
    if prof is None or prof.overall_risk_level == "INSUFFICIENT_DATA":
        return None, INSUFFICIENT
    dims = {d.dimension: d for d in prof.dimensions if d.risk_level != "INSUFFICIENT_DATA"}

    def score(name: str) -> float | None:
        return dims[name].score if name in dims else None

    return DimensionRisk(
        overall_risk_score=prof.overall_risk_score, risk_level=prof.overall_risk_level,
        performance_risk=score("PERFORMANCE"), adaptation_risk=score("ADAPTATION"),
        financial_risk=score("FINANCIAL"), availability_risk=score("AVAILABILITY"),
        key_risk_drivers=[e for d in dims.values() for e in d.evidence][:5],
    ), MODELLED


def assess(c: CandidateEvidence, *, target_position: str, target_role: str, system_name: str,
           min_age: float | None, max_age: float | None, min_minutes: int | None, budget_eur: float | None,
           risk_tolerance: str, competition_name: str | None = None,
           similarity: DimensionSimilarity | None = None) -> MultiDimensionalCandidateAssessment:
    perf, perf_s = _performance(c)
    tac, tac_s = _tactical(c, system_name, target_role)
    risk, risk_s = _risk(c)
    market = c.supplied.get("market")
    similarity = c.supplied.get("similarity") or similarity
    squad = c.supplied.get("squad_impact")
    status = {
        "age": OBSERVED if c.age is not None else UNKNOWN,
        "minutes": OBSERVED if c.minutes is not None else UNKNOWN,
        "performance": perf_s, "tactical": tac_s, "risk": risk_s,
        # The valuation model is UNVERIFIED in the registry: no value is served.
        "market": SUPPLIED if market is not None else UNVERIFIED,
        "similarity": (SUPPLIED if "similarity" in c.supplied else MODELLED) if similarity is not None else NOT_ASSESSED,
        "squad_impact": SUPPLIED if squad is not None else NOT_ASSESSED,
    }
    hard = HardConstraintsEngine.evaluate(
        candidate_position=c.position, target_position=target_position, age=c.age, min_age=min_age, max_age=max_age,
        minutes_played=c.minutes, min_minutes=min_minutes,
        estimated_value_eur=market.estimated_value_eur if market is not None else None, budget_eur=budget_eur,
        risk_level=risk.risk_level if risk is not None else None, risk_tolerance=risk_tolerance,
    )
    conf = DecisionConfidenceEngine.evaluate(
        sample_minutes=c.minutes or 0, sample_matches=c.appearances or 0,
        has_role_profile=c.role_profile is not None, has_tactical_fit=tac is not None,
        has_valuation=market is not None, has_risk_profile=risk is not None, is_ood=False,
    )
    ranked = hard.passed and perf is not None and tac is not None
    parts = [x for x in (tac.tactical_fit_score / 100.0 if tac else None,
                         perf.contribution_rating / 100.0 if perf else None,
                         (1.0 - risk.overall_risk_score) if risk else None) if x is not None]
    why = []
    if tac:
        why.append(f"Tactical fit {tac.tactical_fit_score:.1f} for {tac.target_role} in {tac.system_name} ({tac_s}).")
    if perf:
        why.append(f"Contribution rating {perf.contribution_rating:.1f} over {perf.sample_matches} matches ({perf_s}).")
    if similarity is not None:
        why.append(f"Similarity {similarity.overall_similarity:.2f} to {similarity.comparison_target_name} ({status['similarity']}).")
    if c.appearances is not None:
        why.append(f"{c.appearances} appearances observed ({c.appearances_basis}).")
    missing = [f"{d}: {s}" for d, s in status.items() if s not in (OBSERVED, MODELLED, SUPPLIED)]
    return MultiDimensionalCandidateAssessment(
        candidate_id=c.candidate_id, player_name=c.name, current_club_id=c.club_id, current_club_name=c.club_name,
        age=c.age, primary_position=c.position, target_role=target_role, minutes_played=c.minutes,
        competition_name=competition_name, hard_constraints=hard, performance=perf, tactical=tac,
        similarity=similarity, market=market, risk=risk, squad_impact=squad, prediction_impact=None, confidence=conf,
        dimension_status=status, ranking_status="RANKED" if ranked else "INSUFFICIENT_EVIDENCE",
        ranking_score=round(sum(parts) / len(parts), 4) if ranked and parts else None,
        why_matches=why, where_differs=[f"Not established — {m}" for m in missing],
    )


def role_similarity(target: CandidateEvidence, cand: CandidateEvidence) -> DimensionSimilarity | None:
    """Similarity from two stored, QUALIFIED role profiles; None when either is
    missing or incomplete (a missing dimension is never filled with 0.5)."""
    a, b = target.role_profile, cand.role_profile
    if a is None or b is None or a.role_status != "QUALIFIED" or b.role_status != "QUALIFIED":
        return None
    sa, sb = a.profile_scores or {}, b.profile_scores or {}
    if any(sa.get(d) is None or sb.get(d) is None for d in ROLE_DIMENSIONS):
        return None
    shared = sorted(set(a.feature_vector or {}) & set(b.feature_vector or {}))
    if len(shared) < MIN_SHARED_FEATURES:
        return None
    from app.roles.similarity import PlayerSimilarityEngine

    eng = PlayerSimilarityEngine()
    stat = eng.compute_statistical_similarity({k: a.feature_vector[k] for k in shared},
                                              {k: b.feature_vector[k] for k in shared})
    role = eng.compute_role_similarity(sa, sb)
    overall = eng.compute_overall_similarity(stat, role, 0.0, mode="tactical")
    return DimensionSimilarity(overall_similarity=overall, statistical_similarity=stat, role_similarity=role,
                               replacement_similarity=overall, comparison_target_name=target.name)


def no_evidence_confidence(reason: str):
    from app.decisions.schemas import ConfidenceDecomposition

    return ConfidenceDecomposition(data_confidence=0.0, model_confidence=0.0, decision_confidence=0.0,
                                   confidence_tier="VERY_LOW", data_status="INSUFFICIENT_DATA",
                                   uncertainty_drivers=[reason])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
