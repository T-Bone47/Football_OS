"""Phase 10 — Evidence-Backed Recruitment Report (§14 sections).

Every figure in the report is read from the project/candidates/scenarios/decisions it is given, and a value nobody
supplied is None / "n/a" — never 0, never a passed check. The previous generator defaulted unknown values to 0.0
(so "within budget" and "risk tolerance met" came out True for unknown players) and asserted, unconditionally,
"zero_fabrication_policy: STRICTLY_ENFORCED", "provenance_traceability: 100.0%", a provider, three model names and
"depth_addition: True".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.phase10.recruitment_projects import RecruitmentProject

RISK_SCORE_TOLERANCE = 0.40  # existing policy threshold; applied only when a risk score was supplied


def _n(value: Any, fmt: str = "{}", prefix: str = "") -> str:
    return "n/a" if value is None else f"{prefix}{fmt.format(value)}"


def _window(low: Any, high: Any) -> str:
    return "not set" if low is None and high is None else f"{'-' if low is None else low} to {'-' if high is None else high}"


def generate_recruitment_report(
    project: RecruitmentProject, scenarios: list[dict[str, Any]] | None = None, decisions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Builds the 14-section report for a project the CALLER IS ALLOWED TO SEE (routes authorize first)."""
    scenarios = scenarios or []
    decisions = decisions or []
    candidates = project.candidates

    def a(c: Any, key: str) -> Any:
        return c.analytical_assessment.get(key)

    supplied = sum(1 for c in candidates if c.analytical_assessment.get("source") == "USER_SUPPLIED")
    unverified = sum(1 for c in candidates if c.hard_constraints_passed is None)

    exec_summary = (
        f"Recruitment evaluation for {project.club} targeting position {project.position} ({project.target_role})"
        + (f" under formation {project.formation}" if project.formation else "")
        + f". Candidates on the project: {len(candidates)}. Constraints: age {_window(project.min_age, project.max_age)}, "
        f"budget {_n(project.budget_eur, '{:,.0f}', '€')}, risk tolerance {project.risk_tolerance or 'not set'}."
    )
    requirement = {
        "club": project.club,
        "season": project.season,
        "position": project.position,
        "target_role": project.target_role,
        "formation": project.formation or None,
        "budget_eur": project.budget_eur,
        "age_window": _window(project.min_age, project.max_age),
        "risk_tolerance": project.risk_tolerance,
        "competition_constraints": project.competition_constraints,
    }
    candidate_universe = [
        {
            "candidate_id": c.candidate_id,
            "player_name": c.player_name,
            "current_club": c.current_club,
            "current_competition": c.current_competition,
            "hard_constraints_passed": c.hard_constraints_passed,
            "state": c.state,
        }
        for c in candidates
    ]
    comparison = [
        {
            "name": c.player_name,
            "tactical_fit": a(c, "tactical_fit_score"),
            "contribution_rating": a(c, "contribution_rating"),
            "estimated_value_eur": a(c, "estimated_value_eur"),
            "risk_score": a(c, "overall_risk_score"),
            "scout_priority": c.scout_priority,
        }
        for c in candidates
    ]
    player_intel = {
        c.player_name: {
            "contribution_rating": a(c, "contribution_rating"),
            "role_compatibility": a(c, "role_compatibility"),
            "confidence": c.overall_confidence,
            "data_status": c.data_status,
        }
        for c in candidates
    }
    tactical_fit = {
        c.player_name: {"system": project.formation or None, "target_role": project.target_role, "fit_score": a(c, "tactical_fit_score")}
        for c in candidates
    }

    def budget_view(c: Any) -> dict[str, Any]:
        value = a(c, "estimated_value_eur")
        known = value is not None and project.budget_eur is not None
        return {
            "estimated_value_eur": value,
            "within_budget": (value <= project.budget_eur) if known else None,
            "budget_delta": (project.budget_eur - value) if known else None,
        }

    market = {c.player_name: budget_view(c) for c in candidates}
    transfer_risk = {
        c.player_name: {
            "overall_risk_score": a(c, "overall_risk_score"),
            "tolerance_met": None if a(c, "overall_risk_score") is None else a(c, "overall_risk_score") <= RISK_SCORE_TOLERANCE,
        }
        for c in candidates
    }
    squad_impact = {
        "evaluated_against_squad": project.club,
        "impact_metric": None,
        "depth_addition": None,
        "note": "Squad impact is not computed: no squad data or validated model is connected.",
    }
    scenario_list = [
        {
            "scenario_id": s.get("scenario_id"),
            "name": s.get("name"),
            "net_spend_eur": s.get("results", {}).get("net_transfer_spend_eur"),
            "projected_points_delta": s.get("results", {}).get("projected_league_points_delta"),
        }
        for s in scenarios
    ]
    evidence = [
        f"{supplied} of {len(candidates)} candidate(s) carry assessment values entered by a user; the others carry none.",
        "No analytical model produced any figure in this report.",
        "Hard constraints are evaluated before scoring; a constraint that cannot be verified is reported as unknown.",
    ]
    data_quality = {
        "candidates_total": len(candidates),
        "candidates_with_user_supplied_assessment": supplied,
        "candidates_with_unverified_constraints": unverified,
        "primary_provider": None,
        "provenance_traceability": None,
        "note": "Values are user-entered and carry no provider provenance.",
    }
    limitations = [
        "Valuation, tactical-fit, contribution and risk figures are entered by users; they are not outputs of a validated model.",
        "Scenario figures are arithmetic on user-entered fees and wages; no match or squad impact is modelled.",
        "Unknown values are shown as n/a and are never treated as zero or as satisfying a constraint.",
    ]
    return {
        "report_id": f"rep_{project.project_id}",
        "project_id": project.project_id,
        "project_name": project.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": {
            "1_executive_summary": exec_summary,
            "2_requirement": requirement,
            "3_candidate_universe": candidate_universe,
            "4_candidate_comparison": comparison,
            "5_player_intelligence": player_intel,
            "6_tactical_fit": tactical_fit,
            "7_market": market,
            "8_transfer_risk": transfer_risk,
            "9_squad_impact": squad_impact,
            "10_scenarios": scenario_list,
            "11_evidence": evidence,
            "12_data_quality": data_quality,
            "13_limitations": limitations,
            "14_decision_record": decisions[0] if decisions else None,
        },
    }


def render_report_markdown(report: dict[str, Any]) -> str:
    """Formats the report dictionary as markdown; unknown values render as n/a."""
    s = report.get("sections", {})
    md = [f"# Recruitment Intelligence Report: {report.get('project_name')}\n"]
    md.append(f"**Project ID**: `{report.get('project_id')}` | **Generated**: {report.get('generated_at')}\n")
    md.append("---\n")
    md.append("## 1. Executive Summary")
    md.append(f"{s.get('1_executive_summary')}\n")

    md.append("## 2. Recruitment Requirement")
    for k, v in s.get("2_requirement", {}).items():
        md.append(f"- **{k.replace('_', ' ').title()}**: {'not set' if v in (None, '', []) else v}")
    md.append("")

    md.append("## 3. Candidate Universe")
    md.append("| Candidate | Club | Competition | Hard Constraints | State |")
    md.append("|---|---|---|---|---|")
    labels = {True: "PASS", False: "FAIL", None: "UNVERIFIED"}
    for c in s.get("3_candidate_universe", []):
        md.append(f"| {c['player_name']} | {c['current_club'] or 'n/a'} | {c['current_competition'] or 'n/a'} | {labels[c['hard_constraints_passed']]} | {c['state']} |")
    md.append("")

    md.append("## 4. Candidate Comparison")
    md.append("| Candidate | Tactical Fit | Contribution | Valuation | Risk Score | Priority |")
    md.append("|---|---|---|---|---|---|")
    for c in s.get("4_candidate_comparison", []):
        md.append(
            f"| {c['name']} | {_n(c['tactical_fit'], '{:.1f}')} | {_n(c['contribution_rating'], '{:.1f}')} | "
            f"{_n(c['estimated_value_eur'], '{:,.0f}', '€')} | {_n(c['risk_score'], '{:.2f}')} | {c['scout_priority']} |"
        )
    md.append("")

    md.append("## 10. Planning Scenarios")
    for sc in s.get("10_scenarios", []):
        md.append(f"- **{sc.get('name')}**: Net Spend {_n(sc.get('net_spend_eur'), '{:,.0f}', '€')} | Projected Points: {_n(sc.get('projected_points_delta'), '{:+.1f}')}")
    md.append("")

    md.append("## 13. Limitations & Material Disclosures")
    for lim in s.get("13_limitations", []):
        md.append(f"- {lim}")
    md.append("")

    md.append("## 14. Decision Record")
    dec = s.get("14_decision_record")
    if dec:
        md.append(f"- **Decision ID**: `{dec.get('decision_id')}`")
        md.append(f"- **Chosen Target**: **{dec.get('chosen_candidate_name')}** ({dec.get('decision_type')})")
        md.append(f"- **Signed By**: {dec.get('signed_by')} at {dec.get('decision_timestamp')}")
        md.append(f"- **Audit Hash**: `{dec.get('audit_hash')}`")
    else:
        md.append("No finalized decision recorded yet for this project.")
    return "\n".join(md)
