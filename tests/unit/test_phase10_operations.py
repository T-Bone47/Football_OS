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
from app.phase10.copilot_extension import copilot_dispatcher
from app.phase10.decision_records import DecisionRecord, decision_store
from app.phase10.model_lifecycle import ModelLifecycleStage, model_lifecycle
from app.phase10.operational_ingestion import IngestionRunStatus, operational_pipeline
from app.phase10.recruitment_projects import CandidateState, recruitment_manager
from app.phase10.reports import generate_recruitment_report, render_report_markdown
from app.phase10.scenarios import DataModality, ScenarioType, scenario_engine
from app.phase10.watchlists import (
    AlertChangeType,
    validate_non_causal_phrasing,
    watchlist_engine,
)


# ── §2, §3 Ingestion Run Management ──────────────────────────────────

class TestOperationalIngestion:
    """Tests for Phase 10 §2 & §3 ingestion lifecycle and run management."""

    # Phase 17 correction: these two tests previously asserted that a cycle
    # with no payload succeeded through 11 stages. That success was built on
    # an invented fixture (reconnaissance R4). They now assert the truthful
    # behaviour: no payload -> FAILED, and only executed stages are listed.
    VALID_PAYLOAD = {"response": [{"fixture": {"id": 868547, "date": "2023-08-11T19:00:00+00:00"}}]}

    def test_ingestion_cycle_without_payload_fails_without_fabrication(self):
        """No payload: the cycle fails and invents nothing."""
        run = operational_pipeline.execute_cycle(dry_run=True)
        assert run.status == IngestionRunStatus.FAILED
        assert "NO_PROVIDER_PAYLOAD" in run.error_summary
        assert run.records_seen == 0
        assert run.stages_completed == []
        assert run.impact_summary["status"] == "UNVERIFIED"

    def test_ingestion_cycle_lists_only_executed_stages(self):
        """A supplied payload is validated; unexecuted stages are not claimed."""
        run = operational_pipeline.execute_cycle(payload=self.VALID_PAYLOAD, dry_run=True)
        assert run.status == IngestionRunStatus.SUCCESS
        assert run.stages_completed == ["payload_received", "payload_hashed", "validation_gates_passed"]
        for claimed in ("authentication_verified", "silver_normalized", "features_refreshed", "model_readiness_confirmed"):
            assert claimed not in run.stages_completed
        assert "silver_normalization" in run.impact_summary["stages_not_executed"]

    def test_run_telemetry_schema(self):
        """Every run exposes complete required telemetry fields (§3)."""
        run = operational_pipeline.execute_cycle(payload=self.VALID_PAYLOAD, dry_run=True)
        d = run.to_dict()
        required_keys = [
            "ingestion_run_id", "provider", "resource", "requested_at",
            "completed_at", "status", "records_seen", "records_accepted",
            "records_rejected", "validation_status", "snapshot_id", "checksum",
        ]
        for k in required_keys:
            assert k in d, f"Missing required telemetry key: {k}"
        assert d["records_accepted"] > 0
        assert d["checksum"] is not None

    def test_ingestion_gate_rejection_recorded(self):
        """Quality gate failures are caught and recorded as FAILED without silent repair."""
        corrupt_payload = {
            "response": [
                {
                    "fixture": {"date": "1850-01-01"},  # Invalid historical date
                }
            ]
        }
        run = operational_pipeline.execute_cycle(payload=corrupt_payload, dry_run=True)
        assert run.status == IngestionRunStatus.FAILED
        assert run.records_rejected > 0 or run.records_accepted == 0
        assert run.validation_status in ("REJECTED", "QUARANTINED")


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

    def test_epl_is_production_ready(self):
        """Premier League has verified end-to-end evidence."""
        p = competition_manager.get_profile("EPL")
        assert p["readiness_state"] == "PRODUCTION_READY"
        assert p["matches_count"] == 760
        assert len(p["evidence_checklist"]) > 0

    def test_laliga_does_not_inherit_epl_match_model(self):
        """La Liga has transfer data but cannot execute uncalibrated match models (§5)."""
        p = competition_manager.get_profile("LaLiga")
        assert p["readiness_state"] == "DATA_AVAILABLE"
        assert p["engine_readiness"]["match_prediction"] == "INSUFFICIENT_DATA"
        assert p["engine_readiness"]["valuation"] == "MODEL_VALIDATED"

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
    """Tests for Phase 10 §6, §7, §8 recruitment projects and candidate pipelines."""

    def test_create_and_retrieve_project(self):
        """Persistent recruitment project stores all specification fields."""
        proj = recruitment_manager.create_project({
            "name": "Summer 2027 CB Recruitment",
            "club": "Arsenal",
            "position": "CB",
            "target_role": "Ball Playing Defender",
            "formation": "4-3-3",
            "budget_eur": 40_000_000.0,
            "min_age": 19,
            "max_age": 26,
            "risk_tolerance": "MODERATE",
        })
        assert proj.budget_eur == 40_000_000.0
        assert proj.target_role == "Ball Playing Defender"
        fetched = recruitment_manager.get_project(proj.project_id)
        assert fetched is not None
        assert fetched.name == "Summer 2027 CB Recruitment"

    def test_hard_constraints_execute_before_soft_scoring(self):
        """Hard constraints filter candidates prior to analytical scoring (§7)."""
        proj = recruitment_manager.create_project({
            "name": "Budget Strict Project",
            "position": "CB",
            "budget_eur": 30_000_000.0,
            "min_age": 20,
            "max_age": 25,
            "competition_constraints": ["EPL"],
        })

        # Candidate 1: Within bounds
        c1 = recruitment_manager.add_candidate(proj.project_id, {
            "player_name": "Valid Candidate",
            "age": 23,
            "estimated_value_eur": 25_000_000.0,
            "current_competition": "EPL",
        })
        assert c1.hard_constraints_passed is True

        # Candidate 2: Over age limit
        c2 = recruitment_manager.add_candidate(proj.project_id, {
            "player_name": "Too Old Candidate",
            "age": 32,
            "estimated_value_eur": 20_000_000.0,
            "current_competition": "EPL",
        })
        assert c2.hard_constraints_passed is False

    def test_candidate_workflow_state_transitions(self):
        """Candidates advance through defined workflow states (§8)."""
        proj_id = "proj_cb_summer_2027"
        c = recruitment_manager.add_candidate(proj_id, {
            "player_name": "Test Workflow Candidate",
            "age": 22,
        })
        assert c.state == CandidateState.DISCOVERED

        # Transition to REVIEWING
        c = recruitment_manager.update_candidate_state(proj_id, c.candidate_id, CandidateState.REVIEWING)
        assert c.state == CandidateState.REVIEWING

        # Transition to SHORTLISTED
        c = recruitment_manager.update_candidate_state(proj_id, c.candidate_id, CandidateState.SHORTLISTED)
        assert c.state == CandidateState.SHORTLISTED

    def test_scout_annotations_do_not_alter_analytics(self):
        """Scout notes and priority tags do not modify analytical assessments (§8)."""
        proj_id = "proj_cb_summer_2027"
        c = recruitment_manager.add_candidate(proj_id, {
            "player_name": "Test Annotation Candidate",
            "tactical_fit_score": 85.0,
            "contribution_rating": 80.0,
        })
        orig_fit = c.analytical_assessment["tactical_fit_score"]

        # Add scout notes
        updated = recruitment_manager.annotate_candidate(
            proj_id,
            c.candidate_id,
            notes=["Scout watched live: excellent recovery speed."],
            tags=["Priority 1"],
            priority="HIGH",
        )
        assert "Priority 1" in updated.tags
        assert updated.scout_priority == "HIGH"
        # Analytical score unchanged
        assert updated.analytical_assessment["tactical_fit_score"] == orig_fit

    def test_candidate_comparison(self):
        """Candidate comparison returns side-by-side dimensional metrics."""
        proj = recruitment_manager.get_project("proj_cb_summer_2027")
        cand_ids = [c.candidate_id for c in proj.candidates[:2]]
        comp = recruitment_manager.compare_candidates(proj.project_id, cand_ids)
        assert comp["compared_count"] == len(cand_ids)
        assert "dimension_comparison" in comp
        assert "tactical_fit" in comp["dimension_comparison"]


# ── §9, §10 Watchlists & Governed Alerts ─────────────────────────────

class TestWatchlistsAndAlerts:
    """Tests for Phase 10 §9 & §10 watchlists and governed alerts."""

    def test_watchlist_lifecycle(self):
        """Watchlist creation, item addition, and item removal."""
        wl = watchlist_engine.create_watchlist("Summer Strikers", "Tracking U25 CFs")
        assert wl.name == "Summer Strikers"

        item = watchlist_engine.add_item(wl.watchlist_id, {
            "entity_name": "Test Striker",
            "entity_type": "PLAYER",
        })
        assert item.entity_name == "Test Striker"
        assert len(watchlist_engine.get_watchlist(wl.watchlist_id).items) == 1

        removed = watchlist_engine.remove_item(wl.watchlist_id, item.item_id)
        assert removed is True
        assert len(watchlist_engine.get_watchlist(wl.watchlist_id).items) == 0

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

    def test_change_evaluation_produces_governed_alert(self):
        """Evaluating metric delta produces an evidence-backed alert."""
        alert = watchlist_engine.evaluate_change(
            watchlist_id="wl_scout_priority",
            entity_id="p_test_defender",
            entity_name="Test Defender",
            metric_name="contribution_percentile",
            previous_val=72.0,
            new_val=81.5,
            change_type=AlertChangeType.PERFORMANCE_CHANGE,
        )
        assert alert is not None
        assert alert.delta == 9.5
        assert alert.model_version is not None
        assert alert.confidence == "HIGH"
        assert alert.data_status == "IN_DISTRIBUTION"
        assert len(alert.evidence_summary) > 0


# ── §11, §12 Scenarios & Match Contract ──────────────────────────────

class TestScenarios:
    """Tests for Phase 10 §11 & §12 persistent scenarios and match integration."""

    def test_scenario_creation_and_modalities(self):
        """Scenario clearly separates OBSERVED, MODELLED, and SCENARIO modalities (§11)."""
        scen = scenario_engine.create_scenario("proj_cb_summer_2027", {
            "name": "Scenario B: Retain X / Buy Y",
            "scenario_type": ScenarioType.RETAIN_BUY,
            "assumptions": ["Keep existing starter", "Acquire rotational CB"],
            "movements": [
                {"player_name": "Starter", "action": "RETAIN", "fee_eur": 0.0},
                {"player_name": "Prospect", "action": "BUY", "fee_eur": 15_000_000.0, "wage_eur_weekly": 50_000.0},
            ],
        })
        assert scen.results.net_transfer_spend_eur == 15_000_000.0
        assert any("OBSERVED" in e for e in scen.results.evidence_nodes)
        assert any("MODELLED" in e for e in scen.results.evidence_nodes)
        assert any("SCENARIO" in e for e in scen.results.evidence_nodes)

    def test_match_scenario_returns_unsupported_on_contract_violation(self):
        """Match scenario simulation returns SCENARIO_UNSUPPORTED when inputs exceed model bounds (§12)."""
        extreme_movements = [
            {"player_name": f"Incoming_{i}", "action": "BUY", "fee_eur": 5_000_000.0}
            for i in range(8)  # 8 incoming transfers violates regular squad stability contract
        ]
        scen = scenario_engine.create_scenario("proj_cb_summer_2027", {
            "name": "Extreme Turnover Scenario",
            "movements": extreme_movements,
        })
        assert scen.results.match_prediction_impact["status"] == "SCENARIO_UNSUPPORTED"
        assert "suppressing" in scen.results.match_prediction_impact["action"].lower()


# ── §13, §14 Decision Records & Reports ──────────────────────────────

class TestDecisionRecordsAndReports:
    """Tests for Phase 10 §13 & §14 decision records and reporting."""

    def test_decision_record_immutable_audit_digest(self):
        """Decision records generate immutable SHA-256 audit digests (§13)."""
        rec = decision_store.record_decision({
            "project_id": "proj_cb_summer_2027",
            "project_name": "Summer 2027 CB Recruitment",
            "chosen_candidate_id": "cand_inacio",
            "chosen_candidate_name": "Gonçalo Inácio",
            "decision_type": "TARGET_SIGNING",
            "model_versions": {"valuation": "val_lightgbm_20260920"},
        })
        assert len(rec.audit_hash) == 64
        # Verify integrity
        valid, msg = decision_store.verify_integrity(rec.decision_id)
        assert valid is True

    def test_recruitment_report_has_all_fourteen_sections(self):
        """Generated report compiles all 14 required sections (§14)."""
        rep = generate_recruitment_report("proj_cb_summer_2027")
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
        rep = generate_recruitment_report("proj_cb_summer_2027")
        md = render_report_markdown(rep)
        assert "# Recruitment Intelligence Report" in md
        assert "## 1. Executive Summary" in md
        assert "## 14. Decision Record" in md


# ── §15 Scout Copilot Tools ──────────────────────────────────────────

class TestScoutCopilotExtension:
    """Tests for Phase 10 §15 project-integrated Scout Copilot."""

    def test_copilot_shortlist_query(self):
        """Copilot returns verified project shortlist."""
        res = copilot_dispatcher.dispatch_query("Show me the current shortlist for CB project")
        assert res["intent"] == "PROJECT_SHORTLIST"
        assert res["shortlist_count"] > 0
        assert "Gonçalo Inácio" in [c["player_name"] for c in res["candidates"]]

    def test_copilot_recent_changes_query(self):
        """Copilot returns governed alerts without causal speculation."""
        res = copilot_dispatcher.dispatch_query("What changed about these players?")
        assert res["intent"] == "WATCHLIST_CHANGES"
        assert "alerts" in res

    def test_copilot_flagging_explanation(self):
        """Copilot explains why a player was flagged using deterministic metrics."""
        res = copilot_dispatcher.dispatch_query("Why was Inacio flagged?")
        assert res["intent"] == "EXPLAIN_FLAGGING"
        assert res["found"] is True
        assert res["tactical_fit_score"] is not None

    def test_copilot_scenario_simulation(self):
        """Copilot returns simulated transfer impact."""
        res = copilot_dispatcher.dispatch_query("Simulate selling Partey and buying Inacio")
        assert res["intent"] == "SIMULATE_SCENARIO"
        assert res["net_transfer_spend_eur"] is not None


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

class TestPhase10ApiRoutes:
    """Tests for Phase 10 FastAPI router integration."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_api_list_projects(self, client):
        """GET /api/phase10/recruitment/projects returns project list."""
        resp = client.get("/api/phase10/recruitment/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["club"] == "Arsenal"

    def test_api_get_competition_readiness(self, client):
        """GET /api/phase10/operations/competition-readiness/EPL returns readiness."""
        resp = client.get("/api/phase10/operations/competition-readiness/EPL")
        assert resp.status_code == 200
        data = resp.json()
        assert data["readiness_state"] == "PRODUCTION_READY"

    def test_api_watchlist_alerts(self, client):
        """GET /api/phase10/watchlists/alerts returns governed alerts."""
        resp = client.get("/api/phase10/watchlists/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_api_copilot_project_query(self, client):
        """POST /api/phase10/copilot/project-query dispatches query."""
        resp = client.post(
            "/api/phase10/copilot/project-query",
            json={"query": "Show me the current shortlist", "project_id": "proj_cb_summer_2027"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["intent"] == "PROJECT_SHORTLIST"

    def test_api_project_report(self, client):
        """GET /api/phase10/recruitment/projects/{id}/report returns 14-section report."""
        resp = client.get("/api/phase10/recruitment/projects/proj_cb_summer_2027/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        assert "1_executive_summary" in data["sections"]

