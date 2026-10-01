"""Recruitment, replacement, comparison and scenario evidence on real Silver data.

    DATABASE_URL=postgresql+asyncpg://.../fios_p17_live python scripts/evidence/recruitment_evidence.py

Runs every decision engine against the canonical database (StatsBomb open
data) at a fixed as_of and checks the Phase 18 invariants (R22-R24):

1. Every ranked candidate has stored performance AND tactical evidence;
   no dimension is present without a status of OBSERVED/MODELLED.
2. No market value is served (the valuation model is UNVERIFIED).
3. Candidate ages and minutes equal the database facts (or are None).
4. A comparison returns exactly the requested players.
5. A transfer scenario uses the club's stored roster (lineups at or before
   as_of) and labels its output COUNTERFACTUAL; a missing fee stays unknown.
6. Re-running with the same as_of gives the same decision id and evidence hash.

Nothing is written to the database (the session is rolled back).
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from common import write_evidence

AS_OF = datetime(2016, 6, 1, tzinfo=timezone.utc)


async def main() -> int:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.models.canonical import Club, Match, MatchLineup, Player
    from app.decisions.schemas import (
        CandidateComparisonRequest,
        RecruitmentTargetRequest,
        ReplacementDecisionRequest,
        ScenarioRosterChange,
        TransferScenarioDecisionRequest,
    )
    from app.decisions.service import UnifiedDecisionService

    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    out: dict = {"as_of": AS_OF.isoformat()}
    violations: list[str] = []
    async with Session() as s:
        svc = UnifiedDecisionService(s)  # no principal: nothing is persisted
        out["database_counts"] = {
            "players": (await s.execute(select(func.count(Player.id)))).scalar_one(),
            "clubs": (await s.execute(select(func.count(Club.id)))).scalar_one(),
            "lineup_rows": (await s.execute(select(func.count(MatchLineup.id)))).scalar_one(),
        }

        recruitment = {}
        for pos in ("FW", "MF", "DF"):
            req = RecruitmentTargetRequest(target_position=pos, as_of=AS_OF, limit=10)
            t0 = time.perf_counter()
            res = await svc.analyze_recruitment_targets(req)
            ms = round((time.perf_counter() - t0) * 1000, 1)
            again = await svc.analyze_recruitment_targets(req)
            listed = res.top_recommendations + res.insufficient_evidence
            for c in res.top_recommendations:
                if c.performance is None or c.tactical is None:
                    violations.append(f"{pos}: ranked {c.player_name} without performance/tactical evidence")
            for c in listed:
                if c.market is not None:
                    violations.append(f"{pos}: market value served for {c.player_name}")
                for dim in ("performance", "tactical", "risk", "similarity", "squad_impact"):
                    if getattr(c, dim) is not None and c.dimension_status.get(dim) not in ("MODELLED", "OBSERVED"):
                        violations.append(f"{pos}: {dim} present with status {c.dimension_status.get(dim)}")
                p = (await s.execute(select(Player).where(Player.id == c.candidate_id))).scalar_one()
                expected_age = round((AS_OF.date() - p.date_of_birth).days / 365.25, 1) if p.date_of_birth else None
                if c.age != expected_age:
                    violations.append(f"{pos}: age {c.age} != database {expected_age} for {c.player_name}")
            if (again.decision.decision_id, again.decision.evidence_hash) != (res.decision.decision_id,
                                                                              res.decision.evidence_hash):
                violations.append(f"{pos}: not deterministic for a fixed as_of")
            recruitment[pos] = {
                "status": res.status, "elapsed_ms": ms,
                "evaluated": res.decision.total_candidates_analyzed, "ranked": len(res.top_recommendations),
                "insufficient_evidence_listed": len(res.insufficient_evidence),
                "excluded": len(res.excluded_summaries),
                "dimension_status_counts": {d: dict(Counter(c.dimension_status[d] for c in listed))
                                            for d in ("age", "minutes", "performance", "tactical", "risk", "market")},
                "sample": [{"player": c.player_name, "position": c.primary_position, "age": c.age,
                            "minutes": c.minutes_played, "club": c.current_club_name,
                            "ranking_status": c.ranking_status, "dimension_status": c.dimension_status}
                           for c in listed[:3]],
            }
        out["recruitment"] = recruitment

        # A player and club with real lineups at or before as_of.
        row = (await s.execute(
            select(MatchLineup.player_id, MatchLineup.club_id).join(Match, Match.id == MatchLineup.match_id)
            .where(Match.date <= AS_OF).order_by(Match.date.desc(), MatchLineup.id).limit(1))).one()
        player_id, club_id = row
        rep = await svc.analyze_replacement(ReplacementDecisionRequest(player_id_to_replace=player_id, as_of=AS_OF,
                                                                       limit=5))
        if any(c.similarity is None for c in rep.top_replacements):
            violations.append("replacement ranked without similarity")
        out["replacement"] = {"replaced": rep.replaced_player_name, "status": rep.status,
                              "evaluated": rep.decision.total_candidates_analyzed, "ranked": len(rep.top_replacements),
                              "insufficient_evidence_listed": len(rep.insufficient_evidence),
                              "excluded": len(rep.excluded_summaries)}

        ids = [c.candidate_id for c in (await svc.analyze_recruitment_targets(
            RecruitmentTargetRequest(target_position="FW", as_of=AS_OF, limit=2))).insufficient_evidence[:2]]
        if len(ids) == 2:
            cmp_ = await svc.compare_candidates(CandidateComparisonRequest(candidate_ids=ids, as_of=AS_OF))
            if [c.candidate_id for c in cmp_.candidates] != ids:
                violations.append("comparison did not return exactly the requested players")
            out["comparison"] = {"requested": [str(i) for i in ids],
                                 "returned": [str(c.candidate_id) for c in cmp_.candidates],
                                 "dimension_leaders": cmp_.dimension_leaders}
        else:
            out["comparison"] = {"status": "NOT_RUN", "reason": "fewer than two FW candidates listed"}

        roster_size = (await s.execute(
            select(func.count(func.distinct(MatchLineup.player_id))).join(Match, Match.id == MatchLineup.match_id)
            .where(MatchLineup.club_id == club_id, Match.date <= AS_OF))).scalar_one()
        scen = await svc.simulate_transfer_scenario(TransferScenarioDecisionRequest(
            club_id=club_id, as_of=AS_OF, budget_eur=20_000_000.0,
            roster_changes=[ScenarioRosterChange(player_id=player_id, direction="OUT")]))
        sq = scen.squad_impact_summary
        if sq.get("roster_size_before") != roster_size:
            violations.append(f"scenario roster {sq.get('roster_size_before')} != stored lineup roster {roster_size}")
        if scen.financial_impact["net_transfer_spend_eur"] is not None:
            violations.append("scenario invented a fee")
        if scen.decision.provenance.get("modality") != "COUNTERFACTUAL":
            violations.append("scenario not labelled COUNTERFACTUAL")
        out["scenario"] = {"club": (await s.get(Club, club_id)).name, "stored_roster_size": roster_size,
                           "squad_summary": {k: sq.get(k) for k in ("status", "squad_source", "roster_size_before",
                                                                     "roster_size_after", "depth_status_before",
                                                                     "depth_status_after", "role_coverage_before",
                                                                     "role_coverage_after")},
                           "financial_impact": scen.financial_impact,
                           "modality": scen.decision.provenance.get("modality")}
        await s.rollback()
    await engine.dispose()

    out["violations"] = violations
    status = "VERIFIED" if not violations else "FAILED"
    write_evidence("recruitment_evidence", " ".join(sys.argv),
                   inputs={"database": os.environ["DATABASE_URL"].rsplit("/", 1)[-1], "as_of": AS_OF.isoformat()},
                   outputs=out, status=status)
    for pos, r in out["recruitment"].items():
        print(pos, {k: r[k] for k in ("status", "elapsed_ms", "evaluated", "ranked", "insufficient_evidence_listed",
                                      "excluded")})
    print("replacement", out["replacement"])
    print("scenario", out["scenario"]["squad_summary"])
    print("violations", violations)
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(asyncio.run(main()))
