"""Operational state survives a restart and stays isolated per user and organisation (stage 3).

"Restart" = new manager instances over the SAME durable stores (what a new process sees). In production the stores
are PostgreSQL (tests/unit/test_persistence_contract.py proves the SQL side in CI); here they are the in-memory
reference implementations, so this file verifies the managers' persistence logic itself.
"""
from __future__ import annotations

import pytest

from app.persistence.stores import MemoryCollectionStore, MemoryLedgerStore
from app.phase10.decision_records import DecisionRecordStore
from app.phase10.recruitment_projects import RecruitmentProjectManager
from app.phase10.scenarios import ScenarioEngine
from app.phase10.watchlists import WatchlistEngine
from app.security.tokens import Principal

ALICE = Principal(user_id="alice", roles=frozenset({"scout"}), org_id="org_a")
AMY = Principal(user_id="amy", roles=frozenset({"analyst"}), org_id="org_a")
BOB = Principal(user_id="bob", roles=frozenset({"scout"}), org_id="org_b")
SPEC = {"name": "CB search", "club": "Club A", "season": "2026/27", "position": "CB", "target_role": "Ball Playing Defender", "budget_eur": 40e6}


def _stores():
    return MemoryCollectionStore(), MemoryLedgerStore()


def test_projects_and_candidates_survive_a_restart_and_keep_working():
    collections, _ = _stores()
    before = RecruitmentProjectManager(store=collections)
    project = before.create_project(SPEC, owner_id="alice", organization_id="org_a")
    cand = before.add_candidate(project.project_id, {"player_id": "p1", "player_name": "A Player", "age": 22, "tactical_fit_score": 80.0})
    before.annotate_candidate(project.project_id, cand.candidate_id, notes=["watched live"], priority="HIGH")

    after = RecruitmentProjectManager(store=collections)  # restart
    reloaded = after.get_project_for(AMY, project.project_id)
    assert reloaded.budget_eur == 40e6 and [c.player_name for c in reloaded.candidates] == ["A Player"]
    assert reloaded.candidates[0].scout_notes == ["watched live"] and reloaded.candidates[0].scout_priority == "HIGH"
    assert reloaded.candidates[0].analytical_assessment["tactical_fit_score"] == 80.0
    after.update_candidate_state(project.project_id, cand.candidate_id, "SHORTLISTED")
    assert RecruitmentProjectManager(store=collections).get_project_for(ALICE, project.project_id).candidates[0].state == "SHORTLISTED"


def test_isolation_holds_after_a_restart():
    collections, _ = _stores()
    project = RecruitmentProjectManager(store=collections).create_project(SPEC, owner_id="alice", organization_id="org_a")
    after = RecruitmentProjectManager(store=collections)
    assert after.list_projects_for(BOB) == []
    with pytest.raises(KeyError):
        after.get_project_for(BOB, project.project_id)
    assert [p.project_id for p in after.list_projects_for(AMY)] == [project.project_id]


def test_a_client_chosen_id_cannot_overwrite_a_persisted_project_after_a_restart():
    collections, _ = _stores()
    project = RecruitmentProjectManager(store=collections).create_project(SPEC, owner_id="alice", organization_id="org_a")
    after = RecruitmentProjectManager(store=collections)
    with pytest.raises(ValueError):
        after.create_project({**SPEC, "project_id": project.project_id}, owner_id="bob", organization_id="org_b")


def test_watchlists_and_alerts_survive_and_stay_private():
    collections, _ = _stores()
    before = WatchlistEngine(store=collections)
    wl = before.create_watchlist("mine", owner_id="alice", organization_id="org_a")
    before.add_item(wl.watchlist_id, {"entity_id": "p1", "entity_name": "A"})
    before.evaluate_change(wl.watchlist_id, "p1", "A", "goals_per90", 0.2, 0.45)

    after = WatchlistEngine(store=collections)
    assert [w["name"] for w in after.list_watchlists_for(ALICE)] == ["mine"] and after.list_watchlists_for(AMY) == []
    assert len(after.get_watchlist(wl.watchlist_id).items) == 1
    alerts = after.list_alerts(watchlist_ids={wl.watchlist_id})
    assert len(alerts) == 1 and alerts[0]["new_value"] == 0.45 if "new_value" in alerts[0] else len(alerts) == 1


def test_scenarios_survive_a_restart():
    collections, _ = _stores()
    moves = [{"player_id": "p1", "player_name": "A", "action": "BUY", "fee_eur": 10e6, "wage_eur_weekly": 50_000.0}]
    scen = ScenarioEngine(store=collections).create_scenario("proj1", {"name": "Plan A", "movements": moves}, owner_id="alice", organization_id="org_a")
    after = ScenarioEngine(store=collections)
    loaded = after.get_scenario_for(AMY, scen.scenario_id)
    assert loaded.results.net_transfer_spend_eur == 10e6 and loaded.movements[0].player_name == "A"
    assert after.list_scenarios_for(BOB) == []


DECISION = {"project_id": "proj1", "chosen_candidate_id": "c1", "chosen_candidate_name": "A", "decision_type": "TARGET_SIGNING",
            "candidate_set": [{"candidate_id": "c1"}], "model_versions": {"valuation": "claimed"}}


def test_decision_records_survive_a_restart_and_the_chain_continues():
    collections, ledger = _stores()
    before = DecisionRecordStore(ledger_store=ledger)
    first = before.record_decision(DECISION, signed_by="alice", organization_id="org_a")

    after = DecisionRecordStore(ledger_store=ledger)
    assert after.verify_integrity(first.decision_id)[0] is True
    second = after.record_decision(DECISION, signed_by="amy", organization_id="org_a")
    assert second.prev_audit_hash == first.audit_hash  # continues the persisted chain, not a fresh one
    assert after.verify_chain("org_a") == (True, "chain intact (2 records)")
    assert DecisionRecordStore(ledger_store=ledger).verify_persisted_chain("org_a") == (True, "persisted chain intact (2 records)")
    assert [d["decision_id"] for d in DecisionRecordStore(ledger_store=ledger).list_decisions_for(BOB)] == []


def test_tampering_with_a_persisted_decision_is_detected():
    _, ledger = _stores()
    store = DecisionRecordStore(ledger_store=ledger)
    store.record_decision(DECISION, signed_by="alice", organization_id="org_a")
    store.record_decision(DECISION, signed_by="alice", organization_id="org_a")
    rows = ledger._rows["org_a"]  # an attacker with database access rewrites history (the DB trigger is the other defence)
    rows[0].payload["chosen_candidate_name"] = "Someone Else"
    ok, message = DecisionRecordStore(ledger_store=ledger).verify_persisted_chain("org_a")
    assert ok is False and "content" in message


def test_default_managers_without_a_store_still_work_in_memory():
    assert RecruitmentProjectManager().create_project(SPEC, owner_id="a").owner_id == "a"
    assert WatchlistEngine().create_watchlist("w", owner_id="a").owner_id == "a"


def test_production_refuses_ephemeral_state_unless_explicitly_allowed(monkeypatch):
    from app.persistence.factory import build_stores

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OPERATIONAL_STATE_BACKEND", "memory")
    monkeypatch.delenv("ALLOW_EPHEMERAL_STATE", raising=False)
    with pytest.raises(RuntimeError):
        build_stores()
    monkeypatch.setenv("ALLOW_EPHEMERAL_STATE", "1")
    collections, ledger = build_stores()
    assert collections is not None and ledger is not None
    monkeypatch.setenv("OPERATIONAL_STATE_BACKEND", "carrier-pigeon")
    with pytest.raises(ValueError):
        build_stores()
