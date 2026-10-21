"""Phase 10 — Operational Intelligence Test Suite (§25).

Comprehensive unit and integration tests covering:
  - Controlled recurring ingestion & run telemetry (§2, §3)
  - Competition readiness & governance (§4, §5)
  - Persistent recruitment projects & candidate shortlist lifecycle (§6, §7, §8)
  - Persistent watchlists & governed non-causal alerts (§9, §10)
  - Multi-alternative scenarios & match simulation contract (§11, §12)
  - Immutable decision records & cryptographic verification (§13)
  - 14-section evidence-backed report generation (§14)
  - Project-aware Scout Copilot queries (§15)
  - Model lifecycle governance & data change impact analysis (§16, §17)
  - Security, zero-fabrication, and authorization guarantees (§22, §24)
"""
from __future__ import annotations

import pytest

from app.phase10 import RELEASE_STATES
from app.phase10.competition_readiness import CompetitionReadinessState, competition_manager
from app.phase10.copilot_extension import ProjectCopilotDispatcher
from app.phase10.decision_records import DecisionRecordStore
from app.phase10.model_lifecycle import ModelLifecycleStage, model_lifecycle
from app.phase10.recruitment_projects import CandidateState, RecruitmentProjectManager
from app.phase10.reports import generate_recruitment_report, render_report_markdown
from app.phase10.scenarios import DataModality, ScenarioEngine, ScenarioType
from app.phase10.watchlists import (
    AlertChangeType,
    WatchlistEngine,
    validate_non_causal_phrasing,
)
from app.security.tokens import Principal

OWNER = Principal(user_id="scout_a", roles=frozenset({"scout"}), org_id="org_a")
SPEC = {"name": "CB search", "club": "Club A", "season": "2026/27", "position": "CB", "target_role": "Ball Playing Defender"}


def _project(manager, **over):
    """Fresh, explicit project: nothing is seeded and nothing is defaulted."""
    return manager.create_project({**SPEC, **over}, owner_id=OWNER.user_id, organization_id=OWNER.org_id)


def _player(n: int, **over):
    return {"player_id": f"p{n}", "player_name": f"Player {n}", **over}


# ── §2, §3 Ingestion Run Management ──────────────────────────────────
# The previous TestOperationalIngestion asserted that execute_cycle(dry_run=True) "completed all 11
# stages" and produced records_accepted > 0 - i.e. it asserted the fabricated Arsenal-v-Chelsea
# cycle. That pipeline is gone (R4); the truthful behaviour is covered, with the same telemetry
# requirements, in tests/unit/test_phase10_ingestion_truth.py.


# ── §4, §5 Competition Readiness ────────────────────────────────────

class TestCompetitionReadiness:
    """Tests for Phase 10 §4 & §5 competition readiness and governance."""

    def test_explicit_readiness_states_exist(self):
        """System supports all 5 explicit readiness states."""
        assert CompetitionReadinessState.NOT_AVAILABLE == "NOT_AVAILABLE"
        assert CompetitionReadinessState.INSUFFICIENT_DATA == "INSUFFICIENT_DATA"
        assert CompetitionReadinessState.DATA_AVAILABLE == "DATA_AVAILABLE"
        assert CompetitionReadinessState.MODEL_VALIDATED == "MODEL_VALIDATED"
        assert CompetitionReadinessState.PRODUCTION_READY == "PRODUCTION_READY"

    def test_no_competition_is_ready_without_recorded_evidence(self):
        """Readiness used to be hand-typed (EPL PRODUCTION_READY with 760 matches / log loss 0.9418; La Liga valuation
        MODEL_VALIDATED while the valuation model is MODEL_RELEASE_BLOCKED). With no recorded evidence every
        competition is NOT_ASSESSED, counts are unmeasured (None, not 0), and no engine is authorized."""
        for p in competition_manager.list_all():
            assert p["readiness_state"] == "NOT_ASSESSED"
            assert p["matches_count"] is None and p["transfers_count"] is None and p["players_tracked"] is None
            assert set(p["engine_readiness"].values()) == {"NOT_ASSESSED"}
        for engine in ("match_prediction", "valuation"):
            assert competition_manager.is_engine_authorized("EPL", engine)[0] is False

    def test_laliga_does_not_inherit_epl_match_model(self):
        """No competition inherits another's readiness (§5)."""
        p = competition_manager.get_profile("LaLiga")
        assert p["readiness_state"] == "NOT_ASSESSED"
        assert p["engine_readiness"]["match_prediction"] == "NOT_ASSESSED"

        authorized, reason = competition_manager.is_engine_authorized("LaLiga", "match_prediction")
        assert authorized is False
        assert "Competition does not inherit EPL model validity" in reason

    def test_unknown_competition_is_out_of_distribution(self):
        """Unregistered competitions are strictly marked NOT_AVAILABLE and OOD."""
        p = competition_manager.get_profile("UNKNOWN_LEAGUE")
        assert p["readiness_state"] == "NOT_AVAILABLE"
        assert p["ood_status"] == "OUT_OF_DISTRIBUTION"


# ── §6, §7, §8 Recruitment Projects & Pipelines ─────────────────────

class TestRecruitmentProjects:
    """Tests for Phase 10 §6, §7, §8 recruitment projects and candidate pipelines (fresh manager per test, no seeds)."""

    def test_create_and_retrieve_project(self):
        """Persistent recruitment project stores all specification fields."""
        mgr = RecruitmentProjectManager()
        proj = _project(mgr, name="Summer 2027 CB Recruitment", formation="4-3-3", budget_eur=40_000_000.0,
                        min_age=19, max_age=26, risk_tolerance="MODERATE")
        assert proj.budget_eur == 40_000_000.0
        assert proj.target_role == "Ball Playing Defender"
        fetched = mgr.get_project(proj.project_id)
        assert fetched is not None
        assert fetched.name == "Summer 2027 CB Recruitment"

    def test_hard_constraints_execute_before_soft_scoring(self):
        """Hard constraints filter candidates prior to analytical scoring (§7)."""
        mgr = RecruitmentProjectManager()
        proj = _project(mgr, name="Budget Strict Project", budget_eur=30_000_000.0, min_age=20, max_age=25,
                        competition_constraints=["EPL"])

        c1 = mgr.add_candidate(proj.project_id, _player(1, age=23, estimated_value_eur=25_000_000.0, current_competition="EPL"))
        assert c1.hard_constraints_passed is True

        c2 = mgr.add_candidate(proj.project_id, _player(2, age=32, estimated_value_eur=20_000_000.0, current_competition="EPL"))
        assert c2.hard_constraints_passed is False

        # A candidate whose facts are unknown cannot be certified as meeting the constraints.
        c3 = mgr.add_candidate(proj.project_id, _player(3))
        assert c3.hard_constraints_passed is None

    def test_candidate_workflow_state_transitions(self):
        """Candidates advance through defined workflow states (§8)."""
        mgr = RecruitmentProjectManager()
        proj_id = _project(mgr).project_id
        c = mgr.add_candidate(proj_id, _player(1, age=22))
        assert c.state == CandidateState.DISCOVERED

        c = mgr.update_candidate_state(proj_id, c.candidate_id, CandidateState.REVIEWING)
        assert c.state == CandidateState.REVIEWING

        c = mgr.update_candidate_state(proj_id, c.candidate_id, CandidateState.SHORTLISTED)
        assert c.state == CandidateState.SHORTLISTED

    def test_scout_annotations_do_not_alter_analytics(self):
        """Scout notes and priority tags do not modify analytical assessments (§8)."""
        mgr = RecruitmentProjectManager()
        proj_id = _project(mgr).project_id
        c = mgr.add_candidate(proj_id, _player(1, tactical_fit_score=85.0, contribution_rating=80.0))
        orig_fit = c.analytical_assessment["tactical_fit_score"]

        updated = mgr.annotate_candidate(
            proj_id, c.candidate_id,
            notes=["Scout watched live: excellent recovery speed."], tags=["Priority 1"], priority="HIGH",
        )
        assert "Priority 1" in updated.tags
        assert updated.scout_priority == "HIGH"
        assert updated.analytical_assessment["tactical_fit_score"] == orig_fit

    def test_candidate_comparison(self):
        """Candidate comparison returns side-by-side dimensional metrics."""
        mgr = RecruitmentProjectManager()
        proj = _project(mgr)
        for n in (1, 2):
            mgr.add_candidate(proj.project_id, _player(n, tactical_fit_score=70.0 + n))
        cand_ids = [c.candidate_id for c in proj.candidates[:2]]
        comp = mgr.compare_candidates(proj.project_id, cand_ids)
        assert comp["compared_count"] == len(cand_ids)
        assert "dimension_comparison" in comp
        assert "tactical_fit" in comp["dimension_comparison"]


# ── §9, §10 Watchlists & Governed Alerts ─────────────────────────────

class TestWatchlistsAndAlerts:
    """Tests for Phase 10 §9 & §10 watchlists and governed alerts."""

    def test_watchlist_lifecycle(self):
        """Watchlist creation, item addition, and item removal."""
        eng = WatchlistEngine()
        wl = eng.create_watchlist("Summer Strikers", "Tracking U25 CFs", owner_id=OWNER.user_id, organization_id=OWNER.org_id)
        assert wl.name == "Summer Strikers"

        item = eng.add_item(wl.watchlist_id, {"entity_id": "p1", "entity_name": "Test Striker", "entity_type": "PLAYER"})
        assert item.entity_name == "Test Striker"
        assert len(eng.get_watchlist(wl.watchlist_id).items) == 1

        assert eng.remove_item(wl.watchlist_id, item.item_id) is True
        assert len(eng.get_watchlist(wl.watchlist_id).items) == 0

    def test_alert_governance_rejects_causal_speculation(self):
        """Alert governance validator rejects subjective causal claims (§10)."""
        valid_phrase = "Player contribution percentile increased from 61 to 74."
        is_valid, msg = validate_non_causal_phrasing(valid_phrase)
        assert is_valid is True

        invalid_phrase_1 = "Player has become a better player."
        is_valid, msg = validate_non_causal_phrasing(invalid_phrase_1)
        assert is_valid is False
        assert "better player" in msg

        invalid_phrase_2 = "Player improved because tactical coaching causes higher pass completion."
        is_valid, msg = validate_non_causal_phrasing(invalid_phrase_2)
        assert is_valid is False

    def test_change_evaluation_produces_a_truthful_alert(self):
        """A metric delta produces an alert that reports the supplied values and claims nothing more."""
        eng = WatchlistEngine()
        wl = eng.create_watchlist("L", owner_id=OWNER.user_id, organization_id=OWNER.org_id)
        alert = eng.evaluate_change(
            watchlist_id=wl.watchlist_id,
            entity_id="p_test_defender",
            entity_name="Test Defender",
            metric_name="contribution_percentile",
            previous_val=72.0,
            new_val=81.5,
            change_type=AlertChangeType.PERFORMANCE_CHANGE,
        )
        assert alert is not None
        assert alert.delta == 9.5
        # Previously HIGH / IN_DISTRIBUTION / a model version / "verified operational window" were hard-coded.
        assert alert.model_version is None
        assert (alert.confidence, alert.data_status, alert.source_provider) == ("UNASSESSED", "UNVERIFIED_INPUT", "USER_SUPPLIED")
        assert len(alert.evidence_summary) > 0


# ── §11, §12 Scenarios & Match Contract ──────────────────────────────

class TestScenarios:
    """Tests for Phase 10 §11 & §12 persistent scenarios (arithmetic only; no match forecast exists)."""

    def test_scenario_creation_and_modalities(self):
        """Scenario computes only from supplied figures and labels everything it did not compute (§11)."""
        scen = ScenarioEngine().create_scenario("proj1", {
            "name": "Scenario B: Retain X / Buy Y",
            "scenario_type": ScenarioType.RETAIN_BUY,
            "assumptions": ["Keep existing starter", "Acquire rotational CB"],
            "movements": [
                {"player_id": "p1", "player_name": "Starter", "action": "RETAIN", "fee_eur": 0.0},
                {"player_id": "p2", "player_name": "Prospect", "action": "BUY", "fee_eur": 15_000_000.0, "wage_eur_weekly": 50_000.0},
            ],
        }, owner_id=OWNER.user_id, organization_id=OWNER.org_id)
        assert scen.results.net_transfer_spend_eur == 15_000_000.0
        assert all(m.modality == DataModality.SCENARIO for m in scen.movements)
        evidence = " ".join(scen.results.evidence_nodes)
        assert "SUPPLIED" in evidence and "COMPUTED" in evidence and "NOT_MODELLED" in evidence

    def test_match_impact_is_never_forecast_even_for_extreme_inputs(self):
        """No validated match-prediction model exists, so no scenario ever receives a match forecast (§12)."""
        extreme_movements = [
            {"player_id": f"in{i}", "player_name": f"Incoming_{i}", "action": "BUY", "fee_eur": 5_000_000.0}
            for i in range(8)
        ]
        scen = ScenarioEngine().create_scenario("proj1", {"name": "Extreme Turnover Scenario", "movements": extreme_movements},
                                                owner_id=OWNER.user_id)
        assert scen.results.match_prediction_impact["status"] == "NOT_MODELLED"
        assert scen.results.projected_league_points_delta is None


# ── §13, §14 Decision Records & Reports ──────────────────────────────

class TestDecisionRecordsAndReports:
    """Tests for Phase 10 §13 & §14 decision records and reporting."""

    def test_decision_record_immutable_audit_digest(self):
        """Decision records generate SHA-256 audit digests over their full content (§13)."""
        store = DecisionRecordStore()
        rec = store.record_decision({
            "project_id": "proj1",
            "project_name": "Summer 2027 CB Recruitment",
            "chosen_candidate_id": "cand_1",
            "chosen_candidate_name": "Player One",
            "decision_type": "TARGET_SIGNING",
            "model_versions": {"valuation": "claimed_by_caller"},
        }, signed_by=OWNER.user_id, organization_id=OWNER.org_id)
        assert len(rec.audit_hash) == 64
        valid, msg = store.verify_integrity(rec.decision_id)
        assert valid is True

    def _report(self):
        mgr = RecruitmentProjectManager()
        proj = _project(mgr, name="Report project", budget_eur=40_000_000.0)
        mgr.add_candidate(proj.project_id, _player(1, age=22, estimated_value_eur=20_000_000.0, tactical_fit_score=80.0, overall_risk_score=0.2))
        return generate_recruitment_report(proj, scenarios=[], decisions=[])

    def test_recruitment_report_has_all_fourteen_sections(self):
        """Generated report compiles all 14 required sections (§14)."""
        rep = self._report()
        assert "sections" in rep
        sections = rep["sections"]
        expected_sections = [
            "1_executive_summary", "2_requirement", "3_candidate_universe",
            "4_candidate_comparison", "5_player_intelligence", "6_tactical_fit",
            "7_market", "8_transfer_risk", "9_squad_impact", "10_scenarios",
            "11_evidence", "12_data_quality", "13_limitations", "14_decision_record",
        ]
        for es in expected_sections:
            assert es in sections, f"Missing report section: {es}"

    def test_report_markdown_rendering(self):
        """Report renders clean markdown without hallucinated text."""
        md = render_report_markdown(self._report())
        assert "# Recruitment Intelligence Report" in md
        assert "## 1. Executive Summary" in md
        assert "## 14. Decision Record" in md


# ── §15 Scout Copilot Tools ──────────────────────────────────────────

class TestScoutCopilotExtension:
    """Tests for Phase 10 §15 project-integrated Scout Copilot (stores injected; nothing seeded)."""

    def _setup(self):
        projects, scenarios, watchlists = RecruitmentProjectManager(), ScenarioEngine(), WatchlistEngine()
        proj = _project(projects)
        projects.add_candidate(proj.project_id, {"player_id": "p1", "player_name": "Alvaro Prado", "tactical_fit_score": 88.0})
        scenarios.create_scenario(proj.project_id, {"name": "Plan A", "movements": [
            {"player_id": "p1", "player_name": "Alvaro Prado", "action": "BUY", "fee_eur": 12_000_000.0, "wage_eur_weekly": 40_000.0}]},
            owner_id=OWNER.user_id, organization_id=OWNER.org_id)
        wl = watchlists.create_watchlist("mine", owner_id=OWNER.user_id, organization_id=OWNER.org_id)
        watchlists.evaluate_change(wl.watchlist_id, "p1", "Alvaro Prado", "contribution_percentile", 60.0, 75.0)
        return ProjectCopilotDispatcher(projects, scenarios, watchlists), proj.project_id

    def test_copilot_shortlist_query(self):
        """Copilot returns the project's shortlist."""
        copilot, pid = self._setup()
        res = copilot.dispatch_query("Show me the current shortlist for CB project", pid, OWNER)
        assert res["intent"] == "PROJECT_SHORTLIST"
        assert res["shortlist_count"] == 1
        assert "Alvaro Prado" in [c["player_name"] for c in res["candidates"]]

    def test_copilot_recent_changes_query(self):
        """Copilot returns the caller's recorded alerts."""
        copilot, pid = self._setup()
        res = copilot.dispatch_query("What changed about these players?", pid, OWNER)
        assert res["intent"] == "WATCHLIST_CHANGES"
        assert res["alerts_count"] == 1

    def test_copilot_flagging_explanation(self):
        """Copilot states the recorded values for the candidate named in the question."""
        copilot, pid = self._setup()
        res = copilot.dispatch_query("Why was Alvaro Prado flagged?", pid, OWNER)
        assert res["intent"] == "EXPLAIN_FLAGGING"
        assert res["found"] is True
        assert res["tactical_fit_score"] == 88.0

    def test_copilot_scenario_simulation(self):
        """Copilot returns the scenario's computed net outlay."""
        copilot, pid = self._setup()
        res = copilot.dispatch_query("Simulate selling Partey and buying Prado", pid, OWNER)
        assert res["intent"] == "SIMULATE_SCENARIO"
        assert res["net_transfer_spend_eur"] == 12_000_000.0


# ── §16, §17 Model Lifecycle & Change Impact ─────────────────────────

class TestModelLifecycle:
    """Tests for Phase 10 §16 & §17 model lifecycle and impact analysis."""

    def test_lifecycle_stages_defined(self):
        """All 7 lifecycle stages are defined (§16)."""
        stages = [s.value for s in ModelLifecycleStage]
        assert "TRAINING" in stages
        assert "VALIDATION" in stages
        assert "CANDIDATE" in stages
        assert "SHADOW" in stages
        assert "PRODUCTION" in stages
        assert "MONITORING" in stages
        assert "RETRAIN" in stages
        assert "RETIRE" in stages

    def test_no_silent_promotion_to_production(self):
        """Models cannot be promoted to PRODUCTION from unverified stages (§16)."""
        # Promotion from TRAINING to PRODUCTION directly should fail
        m = model_lifecycle.get_model("calibrated_multinomial_logit_v1")
        m.stage = ModelLifecycleStage.TRAINING
        ok, msg = model_lifecycle.promote_model("calibrated_multinomial_logit_v1", ModelLifecycleStage.PRODUCTION)
        assert ok is False
        assert "Cannot promote" in msg

        # Reset back to PRODUCTION
        m.stage = ModelLifecycleStage.PRODUCTION

    def test_data_impact_analysis_preserves_historical_decisions(self):
        """New incoming data does not automatically rewrite historical decision records (§17)."""
        impact = model_lifecycle.analyze_data_impact(new_records_count=10)
        assert impact.decisions_stale_count == 0
        assert impact.immutable_preservation_verified is True


# ── Release State Certification ──────────────────────────────────────

class TestPhase10ReleaseState:
    """Tests for Phase 10 release state compliance (§26)."""

    def test_release_states_taxonomy(self):
        """Phase 10 supports exactly the designated release states."""
        assert "PHASE_10_IN_PROGRESS" in RELEASE_STATES
        assert "PHASE_10_BLOCKED" in RELEASE_STATES
        assert "OPERATIONAL_INTELLIGENCE_VALIDATED" in RELEASE_STATES
        assert "PHASE_10_RELEASE_BLOCKED" in RELEASE_STATES


# ── REST API Route Tests ─────────────────────────────────────────────
# Functional route tests run as the conftest's authenticated org admin (test_admin / org_test).

class TestPhase10ApiRoutes:
    """Tests for Phase 10 FastAPI router integration."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def _create_project(self, client, name="API project"):
        resp = client.post("/api/phase10/recruitment/projects", json={**SPEC, "name": name, "budget_eur": 40_000_000.0})
        assert resp.status_code == 200, resp.text
        return resp.json()["project_id"]

    def test_api_project_lifecycle_and_report(self, client):
        """Create project -> add candidate -> list -> 14-section report -> copilot, with nothing seeded."""
        pid = self._create_project(client)
        cand = client.post(f"/api/phase10/recruitment/projects/{pid}/candidates",
                           json={"player_id": "p1", "player_name": "API Player", "age": 22, "estimated_value_eur": 20_000_000.0})
        assert cand.status_code == 200 and cand.json()["analytical_assessment"]["source"] == "USER_SUPPLIED"
        assert pid in [p["project_id"] for p in client.get("/api/phase10/recruitment/projects").json()]
        report = client.get(f"/api/phase10/recruitment/projects/{pid}/report")
        assert report.status_code == 200 and "1_executive_summary" in report.json()["sections"]
        copilot = client.post("/api/phase10/copilot/project-query", json={"query": "Show me the current shortlist", "project_id": pid})
        assert copilot.status_code == 200 and copilot.json()["intent"] == "PROJECT_SHORTLIST"

    def test_api_rejects_projects_and_candidates_without_their_defining_fields(self, client):
        assert client.post("/api/phase10/recruitment/projects", json={"name": "only a name"}).status_code == 422
        pid = self._create_project(client, "validation project")
        assert client.post(f"/api/phase10/recruitment/projects/{pid}/candidates", json={"player_name": "No id"}).status_code == 422

    def test_api_get_competition_readiness(self, client):
        """GET /api/phase10/operations/competition-readiness/EPL: not assessed without evidence."""
        resp = client.get("/api/phase10/operations/competition-readiness/EPL")
        assert resp.status_code == 200
        assert resp.json()["readiness_state"] == "NOT_ASSESSED"

    def test_api_watchlist_alerts(self, client):
        """GET /api/phase10/watchlists/alerts returns the caller's alerts."""
        resp = client.get("/api/phase10/watchlists/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_api_unknown_project_is_404_not_a_default_project(self, client):
        assert client.get("/api/phase10/recruitment/projects/proj_cb_summer_2027/report").status_code == 404
        resp = client.post("/api/phase10/copilot/project-query", json={"query": "shortlist", "project_id": "proj_cb_summer_2027"})
        assert resp.status_code == 404

    @pytest.mark.real_auth
    def test_api_objects_are_invisible_across_organisations(self, client):
        """Per-object authorization: another organisation gets 404 for every project-scoped route (no existence leak)."""
        from auth_helpers import auth_headers

        org_a = auth_headers(user_id="u_a", roles=("analyst",), org="org_a")
        org_b = auth_headers(user_id="u_b", roles=("analyst",), org="org_b")
        pid = client.post("/api/phase10/recruitment/projects", json=SPEC, headers=org_a).json()["project_id"]
        base = f"/api/phase10/recruitment/projects/{pid}"
        assert client.get(base, headers=org_a).status_code == 200
        assert client.get(base, headers=org_b).status_code == 404
        assert client.get(base + "/report", headers=org_b).status_code == 404
        assert client.post(base + "/candidates", json={"player_id": "p", "player_name": "X"}, headers=org_b).status_code == 404
        assert client.post(base + "/compare", json={"candidate_ids": []}, headers=org_b).status_code == 404
        assert client.post("/api/phase10/scenarios", json={"project_id": pid, "name": "x"}, headers=org_b).status_code == 404
        assert client.post("/api/phase10/decisions/records", json={"project_id": pid, "chosen_candidate_id": "c", "decision_type": "TARGET_SIGNING"}, headers=org_b).status_code == 404
        assert client.post("/api/phase10/copilot/project-query", json={"query": "shortlist", "project_id": pid}, headers=org_b).status_code == 404
        assert pid not in [p["project_id"] for p in client.get("/api/phase10/recruitment/projects", headers=org_b).json()]
        assert client.get("/api/phase10/recruitment/projects").status_code == 401  # no token at all
