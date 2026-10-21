"""Phase 10 truth: nothing is invented, unknown stays unknown, every object has an owner, evidence is hashed in full.

Replaces reliance on seeded demo data (an Arsenal CB project with made-up fit/value scores for real players,
a "verified" decision record whose evidence digest was the SHA-256 of the EMPTY string, sign-based "simulation"
constants labelled as model output).
"""
from __future__ import annotations

import hashlib
import inspect

import pytest

from app.phase10.copilot_extension import ProjectCopilotDispatcher
from app.phase10.decision_records import DecisionRecordStore
from app.phase10.recruitment_projects import RecruitmentProjectManager
from app.phase10.reports import generate_recruitment_report, render_report_markdown
from app.phase10.scenarios import ScenarioEngine
from app.phase10.watchlists import WatchlistEngine
from app.security.tokens import Principal

ALICE = Principal(user_id="alice", roles=frozenset({"scout"}), org_id="org_a")
AMY = Principal(user_id="amy", roles=frozenset({"analyst"}), org_id="org_a")
BOB = Principal(user_id="bob", roles=frozenset({"scout"}), org_id="org_b")
SOLO = Principal(user_id="solo", roles=frozenset({"scout"}), org_id=None)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
REQ = {"name": "Winger search", "club": "Club A", "season": "2026/27", "position": "FW", "target_role": "Inside Forward"}


def _project(mgr=None, **over):
    mgr = mgr or RecruitmentProjectManager()
    return mgr, mgr.create_project({**REQ, **over}, owner_id="alice", organization_id="org_a")


# ------------------------------------------------------------------ recruitment
def test_fresh_stores_hold_no_seeded_data():
    assert RecruitmentProjectManager().list_projects() == []
    assert WatchlistEngine().list_watchlists() == []
    assert ScenarioEngine().list_scenarios() == []
    assert DecisionRecordStore().list_decisions() == []


@pytest.mark.parametrize("missing", ["name", "club", "season", "position", "target_role"])
def test_project_requires_its_defining_fields_instead_of_an_arsenal_cb_default(missing):
    data = {k: v for k, v in REQ.items() if k != missing}
    with pytest.raises(ValueError):
        RecruitmentProjectManager().create_project(data, owner_id="alice", organization_id="org_a")


def test_unstated_project_constraints_stay_unset_not_invented():
    _, p = _project()
    assert (p.budget_eur, p.min_age, p.max_age, p.risk_tolerance, p.min_minutes_played) == (None, None, None, None, None)
    assert p.competition_constraints == [] and p.formation == ""


@pytest.mark.parametrize("missing", ["player_id", "player_name"])
def test_candidate_requires_an_identity(missing):
    mgr, p = _project()
    data = {k: v for k, v in {"player_id": "p1", "player_name": "A Player"}.items() if k != missing}
    with pytest.raises(ValueError):
        mgr.add_candidate(p.project_id, data)


def test_candidate_added_by_name_invents_nothing():
    mgr, p = _project(budget_eur=40e6, min_age=20, max_age=26, competition_constraints=["EPL"])
    c = mgr.add_candidate(p.project_id, {"player_id": "p1", "player_name": "A Player"})
    assert (c.age, c.current_club, c.current_competition, c.position) == (None, "", "", "")
    a = c.analytical_assessment
    assert [a[k] for k in ("tactical_fit_score", "contribution_rating", "estimated_value_eur", "overall_risk_score")] == [None] * 4
    assert a["source"] == "NONE"
    assert (c.overall_confidence, c.data_status) == ("UNASSESSED", "UNASSESSED")
    assert c.hard_constraints_passed is None and set(a["hard_constraints_breakdown"].values()) == {None}


def test_a_project_without_constraints_has_nothing_to_violate():
    mgr, p = _project()
    c = mgr.add_candidate(p.project_id, {"player_id": "p1", "player_name": "A"})
    assert c.hard_constraints_passed is True and set(c.analytical_assessment["hard_constraints_breakdown"].values()) == {True}


def test_unknown_constraints_are_never_reported_as_met():
    mgr, p = _project(budget_eur=40e6, min_age=20, max_age=26, competition_constraints=["EPL"])
    unknown = mgr.add_candidate(p.project_id, {"player_id": "p1", "player_name": "A"})
    assert unknown.hard_constraints_passed is None
    too_old = mgr.add_candidate(p.project_id, {"player_id": "p2", "player_name": "B", "age": 31})
    assert too_old.hard_constraints_passed is False  # one violated constraint decides, even with others unknown
    ok = mgr.add_candidate(p.project_id, {"player_id": "p3", "player_name": "C", "age": 23, "estimated_value_eur": 30e6, "current_competition": "EPL"})
    assert ok.hard_constraints_passed is True
    pricey = mgr.add_candidate(p.project_id, {"player_id": "p4", "player_name": "D", "age": 23, "estimated_value_eur": 90e6, "current_competition": "EPL"})
    assert pricey.hard_constraints_passed is False and pricey.analytical_assessment["hard_constraints_breakdown"]["budget_valid"] is False


def test_a_caller_cannot_assert_confidence_status_or_a_precomputed_assessment():
    mgr, p = _project()
    c = mgr.add_candidate(p.project_id, {"player_id": "p1", "player_name": "A", "overall_confidence": "HIGH", "data_status": "IN_DISTRIBUTION",
                                         "analytical_assessment": {"tactical_fit_score": 99.0}, "tactical_fit_score": 70.0})
    assert (c.overall_confidence, c.data_status) == ("UNASSESSED", "UNASSESSED")
    assert c.analytical_assessment["tactical_fit_score"] == 70.0 and c.analytical_assessment["source"] == "USER_SUPPLIED"


def test_comparison_keeps_unknown_values_as_none_not_zero():
    mgr, p = _project()
    a = mgr.add_candidate(p.project_id, {"player_id": "p1", "player_name": "A", "tactical_fit_score": 80.0})
    b = mgr.add_candidate(p.project_id, {"player_id": "p2", "player_name": "B"})
    dims = mgr.compare_candidates(p.project_id, [a.candidate_id, b.candidate_id])["dimension_comparison"]
    assert dims["tactical_fit"] == {"A": 80.0, "B": None}
    assert dims["estimated_value_eur"] == {"A": None, "B": None} and dims["risk_score"] == {"A": None, "B": None}


def test_projects_are_visible_to_their_organisation_and_owner_only():
    mgr, p = _project()
    assert [x.project_id for x in mgr.list_projects_for(AMY)] == [p.project_id]
    assert mgr.list_projects_for(BOB) == []
    with pytest.raises(KeyError):
        mgr.get_project_for(BOB, p.project_id)
    solo_mgr = RecruitmentProjectManager()
    own = solo_mgr.create_project(REQ, owner_id="solo", organization_id=None)
    assert solo_mgr.get_project_for(SOLO, own.project_id).project_id == own.project_id
    with pytest.raises(KeyError):
        solo_mgr.get_project_for(AMY, own.project_id)


def test_client_chosen_project_ids_never_overwrite_another_tenants_project():
    mgr, p = _project()
    with pytest.raises(ValueError):
        mgr.create_project({**REQ, "project_id": p.project_id}, owner_id="bob", organization_id="org_b")


# ------------------------------------------------------------------ watchlists
def test_watchlists_are_owner_private_and_require_real_entities():
    eng = WatchlistEngine()
    wl = eng.create_watchlist("Alice's list", owner_id="alice", organization_id="org_a")
    assert [w["watchlist_id"] for w in eng.list_watchlists_for(ALICE)] == [wl.watchlist_id]
    assert eng.list_watchlists_for(AMY) == [] and eng.list_watchlists_for(BOB) == []
    with pytest.raises(KeyError):
        eng.get_watchlist_for(AMY, wl.watchlist_id)
    with pytest.raises(ValueError):
        eng.add_item(wl.watchlist_id, {"notes": "no entity"})  # no "p_unknown" / "Unknown Entity" placeholders
    with pytest.raises(ValueError):
        eng.create_watchlist("", owner_id="alice")  # no "Priority Scouting Targets" default


def test_alerts_do_not_claim_verification_or_a_provider_for_user_supplied_numbers():
    eng = WatchlistEngine()
    wl = eng.create_watchlist("L", owner_id="alice", organization_id="org_a")
    alert = eng.evaluate_change(wl.watchlist_id, "p1", "A", "goals_per90", 0.20, 0.45)
    d = alert.to_dict()
    assert d["source_provider"] == "USER_SUPPLIED" and d["model_version"] is None
    assert (d["confidence"], d["data_status"]) == ("UNASSESSED", "UNVERIFIED_INPUT")
    text = " ".join(d["evidence_summary"]).lower()
    assert "verified" not in text and "zero causal" not in text and "api-football" not in text
    assert "0.2" in text and "0.45" in text  # it still states what was supplied


def test_alert_visibility_follows_watchlist_ownership():
    eng = WatchlistEngine()
    mine = eng.create_watchlist("mine", owner_id="alice", organization_id="org_a")
    theirs = eng.create_watchlist("theirs", owner_id="bob", organization_id="org_b")
    eng.evaluate_change(mine.watchlist_id, "p1", "A", "m", 1.0, 2.0)
    eng.evaluate_change(theirs.watchlist_id, "p9", "Z", "m", 1.0, 3.0)
    visible = {w["watchlist_id"] for w in eng.list_watchlists_for(ALICE)}
    assert [a["entity_id"] for a in eng.list_alerts(watchlist_ids=visible)] == ["p1"]
    assert eng.list_alerts(watchlist_ids=set()) == []


# ------------------------------------------------------------------ scenarios
MOVES = [{"player_id": "p1", "player_name": "A", "action": "BUY", "fee_eur": 10e6, "wage_eur_weekly": 50_000.0},
         {"player_id": "p2", "player_name": "B", "action": "SELL", "fee_eur": 4e6, "wage_eur_weekly": 30_000.0}]


def test_scenarios_compute_arithmetic_only_and_do_not_pretend_to_model_impact():
    eng = ScenarioEngine()
    s = eng.create_scenario("proj1", {"name": "Plan A", "movements": MOVES}, owner_id="alice", organization_id="org_a")
    r = s.results
    assert (r.net_transfer_spend_eur, r.wage_bill_delta_weekly) == (6e6, 20_000.0)
    assert r.squad_overall_rating_delta is None and r.tactical_balance_delta is None and r.projected_league_points_delta is None
    assert r.match_prediction_impact["status"] == "NOT_MODELLED"
    assert (r.confidence, r.data_status) == ("UNASSESSED", "ARITHMETIC_ONLY")
    assert s.model_versions == {}  # no model was used
    assert not [n for n in r.evidence_nodes if n.startswith(("OBSERVED:", "MODELLED:"))]  # the old canned claims
    assert "calibrated_multinomial_logit" not in str(r.match_prediction_impact)


def test_results_do_not_flip_with_the_sign_of_spend():
    eng = ScenarioEngine()
    buy = eng.create_scenario("p", {"name": "buy", "movements": [MOVES[0]]}, owner_id="alice")
    sell = eng.create_scenario("p", {"name": "sell", "movements": [MOVES[1]]}, owner_id="alice")
    assert buy.results.projected_league_points_delta is None and sell.results.projected_league_points_delta is None


def test_unknown_fees_make_the_total_unknown_not_zero():
    eng = ScenarioEngine()
    s = eng.create_scenario("p", {"name": "x", "movements": [{"player_id": "p1", "player_name": "A", "action": "BUY"}]}, owner_id="alice")
    assert s.results.net_transfer_spend_eur is None and s.results.wage_bill_delta_weekly is None


def test_scenarios_need_a_name_and_valid_movements_and_respect_ownership():
    eng = ScenarioEngine()
    with pytest.raises(ValueError):
        eng.create_scenario("p", {"movements": MOVES}, owner_id="alice")  # no "New Planning Scenario" default
    with pytest.raises(ValueError):
        eng.create_scenario("p", {"name": "x", "movements": [{"player_id": "p1", "player_name": "A", "action": "TELEPORT"}]}, owner_id="alice")
    s = eng.create_scenario("p", {"name": "x", "movements": MOVES}, owner_id="alice", organization_id="org_a")
    assert [x["scenario_id"] for x in eng.list_scenarios_for(AMY)] == [s.scenario_id] and eng.list_scenarios_for(BOB) == []
    with pytest.raises(KeyError):
        eng.get_scenario_for(BOB, s.scenario_id)


# ------------------------------------------------------------------ decisions (immutable evidence records)
DECISION = {"project_id": "proj1", "project_name": "P", "chosen_candidate_id": "c1", "chosen_candidate_name": "A", "decision_type": "TARGET_SIGNING",
            "candidate_set": [{"candidate_id": "c1", "name": "A"}], "project_constraints": {"budget_eur": 40e6},
            "scenario_assumptions": ["fee as stated"], "model_versions": {"valuation": "claimed_v1"}}


def _record(store, **over):
    return store.record_decision({**DECISION, **over}, signed_by="alice", organization_id="org_a")


def test_decision_records_do_not_accept_asserted_confidence_signer_or_evidence_digest():
    rec = _record(DecisionRecordStore(), confidence="HIGH", data_status="DECISION_VALIDATED", evidence_dag_digest="e3b0c442" + "0" * 56, evidence_nodes_count=14)
    assert rec.signed_by == "alice"  # the authenticated user, never caller text like "Technical Director"
    assert (rec.confidence, rec.data_status) == ("UNASSESSED", "RECORDED_UNVERIFIED")
    assert rec.lineage_status == "CLAIMED_NOT_VERIFIED"
    assert rec.evidence_dag_digest not in ("", EMPTY_SHA256) and len(rec.evidence_dag_digest) == 64
    assert rec.evidence_nodes_count == len(DECISION["candidate_set"])


def test_evidence_digest_is_computed_from_the_evidence():
    store = DecisionRecordStore()
    a, b = _record(store), _record(store)
    assert a.evidence_dag_digest == b.evidence_dag_digest
    assert _record(store, candidate_set=[{"candidate_id": "c2", "name": "B"}]).evidence_dag_digest != a.evidence_dag_digest


@pytest.mark.parametrize("field,value", [("candidate_set", []), ("project_constraints", {"budget_eur": 1}), ("scenario_assumptions", ["x"]),
                                         ("confidence", "HIGH"), ("signed_by", "mallory"), ("organization_id", "org_b"), ("decision_type", "REJECT_TARGET")])
def test_changing_any_field_of_a_record_is_detected(field, value):
    store = DecisionRecordStore()
    rec = _record(store)
    assert store.verify_integrity(rec.decision_id)[0] is True
    setattr(rec, field, value)
    assert store.verify_integrity(rec.decision_id)[0] is False, f"tampering with {field} went undetected"


def test_records_form_a_hash_chain_per_organisation():
    store = DecisionRecordStore()
    first, second, third = _record(store), _record(store), _record(store)
    assert first.prev_audit_hash == "" and second.prev_audit_hash == first.audit_hash and third.prev_audit_hash == second.audit_hash
    assert store.verify_chain("org_a") == (True, "chain intact (3 records)")
    first.candidate_set = []  # rewrite history
    assert store.verify_chain("org_a")[0] is False
    other = store.record_decision(DECISION, signed_by="bob", organization_id="org_b")
    assert other.prev_audit_hash == ""  # a different tenant has its own chain


def test_decisions_are_visible_to_the_organisation_only():
    store = DecisionRecordStore()
    mine = _record(store)
    store.record_decision(DECISION, signed_by="bob", organization_id="org_b")
    assert [d["decision_id"] for d in store.list_decisions_for(AMY)] == [mine.decision_id]
    assert [d["signed_by"] for d in store.list_decisions_for(BOB)] == ["bob"]
    with pytest.raises(KeyError):
        store.get_decision_for(BOB, mine.decision_id)


# ------------------------------------------------------------------ reports and copilot
def test_report_never_turns_unknown_into_zero_or_a_passed_check():
    mgr, p = _project(budget_eur=40e6)
    mgr.add_candidate(p.project_id, {"player_id": "p1", "player_name": "A"})
    report = generate_recruitment_report(p, scenarios=[], decisions=[])
    s = report["sections"]
    assert s["4_candidate_comparison"][0]["tactical_fit"] is None and s["4_candidate_comparison"][0]["estimated_value_eur"] is None
    assert s["7_market"]["A"]["within_budget"] is None and s["7_market"]["A"]["budget_delta"] is None
    assert s["8_transfer_risk"]["A"]["tolerance_met"] is None
    md = render_report_markdown(report)  # must not crash on unknown values
    assert "n/a" in md and "0.0" not in md.split("## 4.")[1].split("## 10.")[0]


def test_report_makes_no_unsupported_claims():
    mgr, p = _project()
    s = generate_recruitment_report(p, scenarios=[], decisions=[])["sections"]
    blob = str(s)
    for claim in ("zero_fabrication_policy", "STRICTLY_ENFORCED", "100.0%", "val_lightgbm", "calibrated_multinomial_logit", "TacticalFitCalculator", "api-football"):
        assert claim not in blob, f"report asserts {claim!r} without evidence"
    assert s["9_squad_impact"]["depth_addition"] is None
    assert s["12_data_quality"]["provenance_traceability"] is None


def test_copilot_has_no_default_project_and_no_canned_evidence():
    sig = inspect.signature(ProjectCopilotDispatcher.dispatch_query)
    assert sig.parameters["project_id"].default is inspect.Parameter.empty
    source = inspect.getsource(ProjectCopilotDispatcher)
    for canned in ("Saliba", "Inácio", "EVIDENCE_4", "100% SHA-256", "proj_cb_summer_2027"):
        assert canned not in source, f"copilot still hardcodes {canned!r}"
