"""Phase 10 — Scout Copilot Project Query Extension (§15).

Routes natural-language scout queries to deterministic lookups over the data the CALLER IS ALLOWED TO SEE.
Answers state recorded values and say "not supplied" for anything missing. There is no default project, no
canned player and no canned evidence: the previous dispatcher defaulted to a seeded project, answered "why was X
flagged" with Saliba or Inácio regardless of the query, and returned four hardcoded "evidence" strings ("100%
SHA-256 provenance linkage...") for any project.
"""
from __future__ import annotations

from typing import Any

from app.phase10.recruitment_projects import RecruitmentProject, recruitment_manager
from app.phase10.scenarios import scenario_engine
from app.phase10.watchlists import watchlist_engine
from app.security.tokens import Principal

_CONSTRAINT_LABEL = {True: "all verified", False: "at least one violated", None: "not fully verifiable"}


def _show(value: Any, suffix: str = "") -> str:
    return "not supplied" if value is None else f"{value}{suffix}"


class ProjectCopilotDispatcher:
    """Dispatches natural-language scout queries to deterministic, access-scoped lookups."""

    def __init__(self, projects: Any = None, scenarios: Any = None, watchlists: Any = None) -> None:
        self._projects = projects or recruitment_manager
        self._scenarios = scenarios or scenario_engine
        self._watchlists = watchlists or watchlist_engine

    def dispatch_query(self, query: str, project_id: str, principal: Principal) -> dict[str, Any]:
        try:
            project = self._projects.get_project_for(principal, project_id)
        except KeyError:
            return {"error": f"Project '{project_id}' not found"}
        q = query.lower()
        if "shortlist" in q or "candidates" in q:
            return self.get_project_shortlist(project)
        if "changed" in q or "alerts" in q or "movement" in q:
            return self.inspect_recent_changes(principal)
        if "flagged" in q or "why was" in q:
            return self.explain_candidate_flagging(project, query)
        if "simulate" in q or "sell" in q or "buy" in q:
            return self.simulate_transfer_scenario(project, principal)
        if "evidence" in q or "support" in q:
            return self.retrieve_candidate_evidence(project)
        return self.get_project_shortlist(project)

    def get_project_shortlist(self, p: RecruitmentProject) -> dict[str, Any]:
        return {
            "intent": "PROJECT_SHORTLIST",
            "project_name": p.name,
            "club": p.club,
            "target_role": p.target_role,
            "budget_eur": p.budget_eur,
            "shortlist_count": len(p.candidates),
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "player_name": c.player_name,
                    "club": c.current_club,
                    "state": c.state,
                    "tactical_fit": c.analytical_assessment.get("tactical_fit_score"),
                    "estimated_value_eur": c.analytical_assessment.get("estimated_value_eur"),
                    "scout_priority": c.scout_priority,
                }
                for c in p.candidates
            ],
            "text_summary": f"Project '{p.name}' currently has {len(p.candidates)} candidate(s) in review (unranked).",
        }

    def inspect_recent_changes(self, principal: Principal) -> dict[str, Any]:
        """Alerts from the caller's own watchlists only."""
        visible = {w["watchlist_id"] for w in self._watchlists.list_watchlists_for(principal)}
        alerts = self._watchlists.list_alerts(limit=5, watchlist_ids=visible)
        return {
            "intent": "WATCHLIST_CHANGES",
            "alerts_count": len(alerts),
            "alerts": alerts,
            "text_summary": (
                f"Found {len(alerts)} recorded metric shift(s) on your watchlists. "
                f"Most recent: {alerts[0].get('what_changed') if alerts else 'none.'}"
            ),
        }

    def explain_candidate_flagging(self, p: RecruitmentProject, query: str) -> dict[str, Any]:
        """States the recorded values for the candidate named in the query; never guesses a player."""
        q = query.lower()
        cand = next((c for c in p.candidates if c.player_name.lower() in q), None)
        if cand is None:
            names = ", ".join(c.player_name for c in p.candidates) or "none yet"
            return {
                "intent": "EXPLAIN_FLAGGING",
                "found": False,
                "text_summary": f"Name a candidate on this project in your question (candidates: {names}).",
            }
        a = cand.analytical_assessment
        return {
            "intent": "EXPLAIN_FLAGGING",
            "player_name": cand.player_name,
            "found": True,
            "tactical_fit_score": a.get("tactical_fit_score"),
            "contribution_rating": a.get("contribution_rating"),
            "hard_constraints_passed": cand.hard_constraints_passed,
            "scout_notes": cand.scout_notes,
            "text_summary": (
                f"Recorded values for {cand.player_name}: tactical fit {_show(a.get('tactical_fit_score'))}, "
                f"contribution {_show(a.get('contribution_rating'))} (source: {a.get('source', 'NONE')}); "
                f"hard constraints {_CONSTRAINT_LABEL[cand.hard_constraints_passed]}. "
                f"Scout notes: {', '.join(cand.scout_notes) or 'none'}."
            ),
        }

    def simulate_transfer_scenario(self, p: RecruitmentProject, principal: Principal) -> dict[str, Any]:
        scenarios = self._scenarios.list_scenarios_for(principal, p.project_id)
        if not scenarios:
            return {"error": "No scenarios available for this project"}
        sc = scenarios[0]
        res = sc.get("results", {})
        spend = res.get("net_transfer_spend_eur")
        return {
            "intent": "SIMULATE_SCENARIO",
            "scenario_name": sc.get("name"),
            "net_transfer_spend_eur": spend,
            "projected_points_delta": res.get("projected_league_points_delta"),
            "match_prediction_impact": res.get("match_prediction_impact"),
            "text_summary": (
                f"Scenario '{sc.get('name')}': net outlay {'unknown' if spend is None else f'€{spend:,.0f}'} "
                "(sum of user-entered fees). League points and match impact are not modelled."
            ),
        }

    def retrieve_candidate_evidence(self, p: RecruitmentProject) -> dict[str, Any]:
        """What is actually recorded for each candidate; no canned evidence."""
        nodes = [
            {
                "candidate_id": c.candidate_id,
                "player_name": c.player_name,
                "assessment_source": c.analytical_assessment.get("source", "NONE"),
                "hard_constraints": c.analytical_assessment.get("hard_constraints_breakdown", {}),
            }
            for c in p.candidates
        ]
        supplied = sum(1 for n in nodes if n["assessment_source"] == "USER_SUPPLIED")
        return {
            "intent": "RETRIEVE_EVIDENCE",
            "project_id": p.project_id,
            "evidence_nodes": nodes,
            "text_summary": (
                f"{len(nodes)} candidate(s); {supplied} carry user-supplied assessment values. "
                "No analytical-model evidence is attached to any candidate."
            ),
        }


copilot_dispatcher = ProjectCopilotDispatcher()
