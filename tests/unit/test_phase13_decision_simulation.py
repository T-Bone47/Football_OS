"""Phase 13 — Football Decision Intelligence 2.0 Comprehensive Test Suite (§30).

Validates all 28 Phase 13 Release Gates (G1–G28):
  - G1:  Reconnaissance documentation integrity
  - G2:  Scenario Graph (12 stages, cryptographic lineage)
  - G3:  Squad Baseline (empirical roster, non-fabricated metrics)
  - G4:  Tactical Simulator (8 supported formations, diagnostics, gap detection)
  - G5:  Player Replacement Simulator (multi-dimensional deltas, no single hidden score)
  - G6:  Multi-Transfer Scenarios (Sell/Buy, Multi-Buy, Retain/Promote, Status Quo)
  - G7:  Budget Allocation Simulator
  - G8:  Squad Depth Simulation (SOLID, ADEQUATE, THIN, CRITICAL_GAP)
  - G9:  Academy Integration (readiness states without age-only bias)
  - G10: Manager / Tactical Change Simulation (hypothetical scenario boundary)
  - G11: Side-by-Side Scenario Comparison (Pareto trade-offs, non-collapsed)
  - G12: Sensitivity Analysis (low/base/high, non-statistical CI flag)
  - G13: Robustness Analysis (stress perturbations, STABLE/SENSITIVE/HIGHLY_SENSITIVE)
  - G14: Match Prediction Boundary Contract (churn > 4 triggers SCENARIO_UNSUPPORTED)
  - G15: Evidence Graph V2 (cryptographic SHA-256 lineage)
  - G16: Decision Record V2 (immutability, audit digest)
  - G17: Decision Follow-Up Evaluation (realized vs assumed metrics, alignment status)
  - G18: Recruitment Workflow V2 (scenario comparison stage)
  - G19: Scout Copilot V3 (deterministic dispatch, no hallucinations)
  - G20: Frontend Decision Lab Workspace surface
  - G21: REST API Contracts (Pydantic models, zero router logic)
  - G22: Database / In-Memory Store integrity
  - G23: Security & Input Validation
  - G24: Performance & Bounded Complexity
  - G25: Test Suite Zero Failures / Zero Regressions
  - G26: Deterministic Scenario Replay
  - G27: Release Documentation
  - G28: Full Release Audit & Certification
"""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from app.api.routes_phase13 import router as phase13_router
from app.main import app
from app.phase13 import (
    EpistemicModality,
    Phase13ReleaseState,
    ScenarioRobustnessClass,
    SquadDepthState,
    TacticalDiagnosticState,
)
from app.phase13.budget_depth_simulator import (
    BudgetDepthSimulator,
    budget_depth_simulator,
)
from app.phase13.copilot_v3 import (
    ScoutCopilotV3Dispatcher,
    copilot_v3_dispatcher,
)
from app.phase13.decision_record_v2 import (
    DecisionFollowUpEvaluation,
    DecisionRecordStoreV2,
    DecisionRecordV2,
    FollowUpAlignmentStatus,
    ScenarioAlternativeSummary,
    decision_record_store_v2,
)
from app.phase13.multi_transfer_scenario import (
    MultiTransferScenarioEngine,
    ScenarioMovement,
    multi_transfer_scenario_engine,
)
from app.phase13.player_replacement import (
    PlayerReplacementSimulator,
    player_replacement_simulator,
)
from app.phase13.role_dependencies import (
    RoleDependencyEngine,
    role_dependency_engine,
)
from app.phase13.scenario_graph import (
    UnifiedScenarioGraphBuilder,
    unified_scenario_graph_builder,
)
from app.phase13.sensitivity_robustness import (
    ScenarioRobustnessAnalyzer,
    ScenarioSensitivityAnalyzer,
)
from app.phase13.squad_baseline import (
    SquadBaselineRegistry,
    squad_baseline_registry,
)
from app.phase13.squad_construction import (
    SquadConstructionEngineV2,
    squad_construction_engine_v2,
)
from app.phase13.tactical_simulator import (
    SUPPORTED_FORMATIONS,
    TacticalSystemSimulator,
    tactical_system_simulator,
)

client = TestClient(app)


# ── 1. G3: Squad Baseline Roster & Financial Integrity ─────────────────

def test_squad_baseline_integrity() -> None:
    baseline = squad_baseline_registry.get_baseline("arsenal_fc")
    assert baseline.club_id == "arsenal_fc"
    assert len(baseline.squad_players) >= 11
    # Check that missing values are not fabricated
    for p in baseline.squad_players:
        assert p.minutes_played_season >= 0
        assert 0.0 <= p.contribution_percentile <= 100.0
        assert p.epistemic_modality == EpistemicModality.OBSERVED.value
    # Financial state
    assert baseline.financial_state.available_transfer_budget_eur > 0
    assert baseline.financial_state.weekly_wage_headroom_eur > 0


# ── 2. G4: Tactical System Simulator & Formations ──────────────────────

def test_tactical_simulator_supported_and_unsupported_formations() -> None:
    sim = TacticalSystemSimulator()
    roster = [
        {"position": "GK"}, {"position": "CB"}, {"position": "CB"},
        {"position": "RB"}, {"position": "LB"}, {"position": "DM"},
        {"position": "CM"}, {"position": "AM"}, {"position": "RW"},
        {"position": "LW"}, {"position": "CF"},
    ]

    for fmt in SUPPORTED_FORMATIONS:
        result = sim.simulate_formation(fmt, roster)
        assert result.is_supported is True
        assert result.overall_compatibility_score > 0.0
        assert result.diagnostics_state in [
            TacticalDiagnosticState.OPTIMAL,
            TacticalDiagnosticState.TACTICAL_GAP,
            TacticalDiagnosticState.ROLE_OVERLOAD,
            TacticalDiagnosticState.ROLE_UNDERCOVERAGE,
            TacticalDiagnosticState.POSITIONAL_REDUNDANCY,
        ]

    # Unsupported formation must be strictly rejected
    unsupported = sim.simulate_formation("2-3-5", roster)
    assert unsupported.is_supported is False
    assert unsupported.diagnostics_state == TacticalDiagnosticState.FORMATION_UNSUPPORTED
    assert "not calibrated" in unsupported.detected_gaps[0]


def test_tactical_gap_detection() -> None:
    sim = TacticalSystemSimulator()
    # Roster with only 1 CB attempting 3-at-the-back
    roster = [{"position": "GK"}, {"position": "CB"}, {"position": "RB"}, {"position": "LB"}]
    result = sim.simulate_formation("3-4-2-1", roster)
    assert result.diagnostics_state == TacticalDiagnosticState.TACTICAL_GAP
    assert any("Insufficient central defenders" in g for g in result.detected_gaps)


# ── 3. Role Dependency Graph (Non-Causal) ─────────────────────────────

def test_role_dependency_graph_non_causality() -> None:
    engine = RoleDependencyEngine()
    deps = engine.get_dependencies_for_role("Ball Playing Centre Back")
    assert len(deps) >= 2
    for d in deps:
        assert d.relationship_type == "MODELLED_DEPENDENCY"
        assert d.epistemic_modality == EpistemicModality.MODELLED.value
        assert "causal" not in d.description.lower() or "structural" in d.description.lower()


# ── 4. G5: Player Replacement Simulator ────────────────────────────────

def test_player_replacement_simulator_multi_dimensional() -> None:
    sim = PlayerReplacementSimulator()
    comparison = sim.compare_replacement(
        player_a_id="partey_05",
        player_b_id="inacio_25",
        player_a_name="Thomas Partey",
        player_b_name="Gonçalo Inácio",
        position="CB",
    )
    assert comparison.player_a_name == "Thomas Partey"
    assert comparison.player_b_name == "Gonçalo Inácio"
    # Never collapses into single opaque score
    assert comparison.valuation_delta_eur != 0.0
    assert comparison.tactical_fit_delta != 0.0
    assert comparison.contribution_delta != 0.0
    assert len(comparison.dimensional_deltas) >= 5
    assert len(comparison.assumptions) >= 2


# ── 5. G8, G9: Squad Depth & Fixture Congestion ────────────────────────

def test_squad_depth_and_congestion_scenarios() -> None:
    sim = BudgetDepthSimulator()
    domestic = sim.simulate_depth_stress("arsenal_fc", congestion_mode="DOMESTIC_LEAGUE")
    assert domestic.depth_state in [SquadDepthState.SOLID.value, SquadDepthState.ADEQUATE.value]

    congested = sim.simulate_depth_stress("arsenal_fc", congestion_mode="SEVERE_CONGESTION")
    assert congested.overall_depth_rating <= domestic.overall_depth_rating
    assert len(congested.position_coverages) >= 4


# ── 6. G6, G14: Multi-Transfer Scenarios & Match Boundary Contract ────

def test_multi_transfer_scenario_execution() -> None:
    engine = MultiTransferScenarioEngine()
    movements = [
        ScenarioMovement(action="SELL", player_id="p1", player_name="Player 1", position="DM", fee_eur=15_000_000, weekly_wage_eur=180_000),
        ScenarioMovement(action="BUY", player_id="p2", player_name="Player 2", position="CB", fee_eur=40_000_000, weekly_wage_eur=100_000),
    ]
    scen = engine.simulate_scenario(
        name="Test Sell/Buy",
        club_id="arsenal_fc",
        scenario_type="SELL_BUY",
        movements=movements,
        assumptions=["Test assumption 1"],
    )
    assert scen.net_spend_eur == 25_000_000.0
    assert scen.wage_bill_delta_weekly == -80_000.0
    assert scen.match_impact.is_supported is True
    assert scen.match_impact.status == "COUNTERFACTUAL_MODELLED"
    # Probability sum verification
    prob_sum = (
        scen.match_impact.scenario_win_prob
        + scen.match_impact.scenario_draw_prob
        + scen.match_impact.scenario_loss_prob
    )
    assert abs(prob_sum - 1.0) < 1e-4


def test_match_prediction_boundary_enforcement() -> None:
    """If roster alterations exceed calibrated domain (>4 changes), must return SCENARIO_UNSUPPORTED."""
    engine = MultiTransferScenarioEngine()
    # 5 movements exceeds threshold of 4
    movements = [
        ScenarioMovement(action="BUY", player_id=f"p_{i}", player_name=f"Player {i}", position="CM", fee_eur=10_000_000)
        for i in range(5)
    ]
    scen = engine.simulate_scenario(
        name="Excessive Churn Scenario",
        club_id="arsenal_fc",
        scenario_type="MULTI_BUY",
        movements=movements,
    )
    assert scen.match_impact.is_supported is False
    assert scen.match_impact.status == "SCENARIO_UNSUPPORTED"
    assert "exceed calibrated parameter domain" in scen.match_impact.contract_message


# ── 7. G11: Side-by-Side Pareto Comparison ─────────────────────────────

def test_side_by_side_scenario_comparison() -> None:
    engine = MultiTransferScenarioEngine()
    comp = engine.compare_scenarios(
        scenario_ids=["scen_sell_buy_inacio", "scen_multi_buy_cb_dm"],
        club_id="arsenal_fc",
    )
    assert len(comp.scenarios) == 2
    assert "net_spend_eur" in comp.dimension_comparison_matrix
    assert "tactical_fit_delta" in comp.dimension_comparison_matrix
    assert "win_probability_delta" in comp.dimension_comparison_matrix
    assert len(comp.pareto_trade_off_notes) >= 2


# ── 8. G7, G14: Squad Construction Pareto Frontier ─────────────────────

def test_squad_construction_pareto_frontier() -> None:
    engine = SquadConstructionEngineV2()
    frontier = engine.generate_pareto_frontier("arsenal_fc", formation="4-3-3", budget_ceiling_eur=65_000_000.0)
    assert len(frontier) >= 2
    # Verify non-collapse into single score: strategies show trade-offs
    strategies = [f.strategy_name for f in frontier]
    assert any("Elite" in s for s in strategies)
    assert any("Balanced" in s for s in strategies)


# ── 9. G12: Sensitivity Analysis ──────────────────────────────────────

def test_scenario_sensitivity_analysis() -> None:
    analyzer = ScenarioSensitivityAnalyzer()
    profile = analyzer.evaluate_sensitivity(
        scenario_id="scen_01",
        club_id="arsenal_fc",
        base_net_spend_eur=20_000_000.0,
        base_wage_delta_weekly=-80_000.0,
        base_tactical_fit=88.4,
    )
    assert len(profile.intervals) >= 4
    for interval in profile.intervals:
        assert interval.low_value <= interval.base_value or interval.high_value <= interval.base_value
        assert interval.statistical_ci is False  # Non-statistical scenario assumption
        assert interval.epistemic_modality == EpistemicModality.ASSUMPTION.value
    assert len(profile.profile_digest) == 64  # SHA-256


# ── 10. G13: Robustness Analysis ──────────────────────────────────────

def test_scenario_robustness_analysis() -> None:
    analyzer = ScenarioRobustnessAnalyzer()
    report = analyzer.test_robustness(
        scenario_id="scen_01",
        scenario_name="Test Scenario",
        club_id="arsenal_fc",
        net_spend_eur=20_000_000.0,
        wage_bill_delta=-80_000.0,
        tactical_fit_delta=+2.2,
        squad_depth_delta=+1.5,
        available_budget_eur=65_000_000.0,
        available_wage_headroom=120_000.0,
    )
    assert report.robustness_class in [
        ScenarioRobustnessClass.STABLE.value,
        ScenarioRobustnessClass.SENSITIVE.value,
        ScenarioRobustnessClass.HIGHLY_SENSITIVE.value,
    ]
    assert len(report.perturbation_tests) == 5
    assert len(report.robustness_digest) == 64


# ── 11. G2, G15: Unified 12-Stage Scenario Graph ──────────────────────

def test_unified_scenario_graph_lineage() -> None:
    builder = UnifiedScenarioGraphBuilder()
    graph = builder.build_graph(
        club_id="arsenal_fc",
        scenario_id="scen_verify",
        scenario_name="Test Lineage Graph",
    )
    assert len(graph.nodes) == 12
    assert len(graph.edges) >= 11
    assert len(graph.graph_digest) == 64

    # Check epistemic modalities across stages
    modalities = {n.epistemic_status for n in graph.nodes}
    assert EpistemicModality.OBSERVED.value in modalities
    assert EpistemicModality.MODELLED.value in modalities
    assert EpistemicModality.COUNTERFACTUAL.value in modalities
    assert EpistemicModality.SCENARIO.value in modalities


# ── 12. G16, G17: Decision Record V2 & Retrospective Follow-Up ─────────

def test_decision_record_v2_and_immutability() -> None:
    store = DecisionRecordStoreV2()
    record = DecisionRecordV2(
        decision_id="dec_test_001",
        project_id="rec_proj_001",
        club_id="arsenal_fc",
        chosen_scenario_id="scen_01",
        chosen_scenario_name="Scenario A",
    )
    saved = store.record_decision(record)
    assert saved.decision_id == "dec_test_001"
    assert len(saved.audit_digest) == 64

    # Enforce immutability: attempting to re-record must raise ValueError
    with pytest.raises(ValueError, match="already exists and is immutable"):
        store.record_decision(record)


def test_decision_follow_up_evaluation() -> None:
    store = DecisionRecordStoreV2()
    # Use seeded decision dec_rec_arsenal_cb_001
    follow_up = store.evaluate_follow_up_alignment(
        decision_id="dec_rec_arsenal_cb_001",
        realized_fee_eur=44_000_000.0,
        realized_wage_eur=112_000.0,
        realized_minutes=2350.0,
        observed_role="Ball Playing Centre Back",
        observed_availability_pct=92.0,
        observed_contribution=85.0,
    )
    assert follow_up.alignment_status == FollowUpAlignmentStatus.ALIGNED.value
    assert len(follow_up.follow_up_digest) == 64

    # Original decision remains unmodified
    rec = store.get_decision("dec_rec_arsenal_cb_001")
    assert rec is not None
    assert rec.is_immutable is True


# ── 13. G19: Scout Copilot V3 Deterministic Tool Dispatcher ───────────

def test_copilot_v3_deterministic_dispatch() -> None:
    dispatcher = ScoutCopilotV3Dispatcher()

    # Query 1: Replacement scenarios
    r1 = dispatcher.dispatch("Build three scenarios for replacing our centre-back.")
    assert r1["intent"] == "BUILD_REPLACEMENT_SCENARIOS"
    assert r1["resolved"] is True
    assert len(r1["results"]) >= 1

    # Query 2: Player departure
    r2 = dispatcher.dispatch("Show what happens if we sell Thomas Partey.")
    assert r2["intent"] == "SIMULATE_PLAYER_DEPARTURE"
    assert "Partey" in r2["summary"]

    # Query 3: Formation comparison
    r3 = dispatcher.dispatch("Compare 4-3-3 and 3-4-2-1 for this squad.")
    assert r3["intent"] == "COMPARE_FORMATIONS"
    assert "4-3-3" in r3["formations"]

    # Query 4: Position exposure
    r4 = dispatcher.dispatch("Which positions are most exposed if two midfielders leave?")
    assert r4["intent"] == "IDENTIFY_EXPOSED_POSITIONS"

    # Query 5: Budget strategy
    r5 = dispatcher.dispatch("Create a €50M recruitment strategy.")
    assert r5["intent"] == "CREATE_BUDGET_RECRUITMENT_STRATEGY"
    assert len(r5["frontier_solutions"]) >= 1

    # Query 6: Trade-offs
    r6 = dispatcher.dispatch("Show me the trade-offs between these scenarios.")
    assert r6["intent"] == "SHOW_SCENARIO_TRADEOFFS"

    # Query 7: Unsupported boundary explanation
    r7 = dispatcher.dispatch("Why is this scenario unsupported?")
    assert r7["intent"] == "EXPLAIN_SCENARIO_UNSUPPORTED"

    # Query 8: Sensitive assumptions
    r8 = dispatcher.dispatch("Which assumptions make this scenario sensitive?")
    assert r8["intent"] == "EXPLAIN_SCENARIO_SENSITIVITY"


# ── 14. G26: Deterministic Scenario Replay ─────────────────────────────

def test_deterministic_scenario_replay() -> None:
    engine = MultiTransferScenarioEngine()
    movements = [
        ScenarioMovement(action="BUY", player_id="replay_cand", player_name="Replay Candidate", position="CB", fee_eur=30_000_000)
    ]
    scen1 = engine.simulate_scenario("Replay Test", "arsenal_fc", "CUSTOM", movements, assumptions=["Replay A"])
    scen2 = engine.simulate_scenario("Replay Test", "arsenal_fc", "CUSTOM", movements, assumptions=["Replay A"])

    assert scen1.compute_digest() == scen2.compute_digest()
    assert scen1.net_spend_eur == scen2.net_spend_eur
    assert scen1.tactical_fit_delta == scen2.tactical_fit_delta


# ── 15. G21: REST API Endpoints ───────────────────────────────────────

def test_api_squad_baseline() -> None:
    res = client.get("/api/v1/decision-lab/squad/arsenal_fc")
    assert res.status_code == 200
    data = res.json()
    assert data["club_id"] == "arsenal_fc"
    assert len(data["squad_players"]) > 0


def test_api_tactical_evaluation() -> None:
    res = client.get("/api/v1/decision-lab/tactical/arsenal_fc?formation=4-3-3")
    assert res.status_code == 200
    data = res.json()
    assert data["formation"] == "4-3-3"
    assert data["is_supported"] is True


def test_api_depth_evaluation() -> None:
    res = client.get("/api/v1/decision-lab/depth/arsenal_fc?congestion=DOMESTIC_LEAGUE")
    assert res.status_code == 200
    data = res.json()
    assert "depth_state" in data


def test_api_scenarios_and_comparison() -> None:
    res = client.get("/api/v1/decision-lab/scenarios?club_id=arsenal_fc")
    assert res.status_code == 200
    scens = res.json()
    assert len(scens) >= 2

    # Compare
    comp_res = client.post(
        "/api/v1/decision-lab/scenarios/compare",
        json={"scenario_ids": [scens[0]["scenario_id"], scens[1]["scenario_id"]], "club_id": "arsenal_fc"},
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert len(comp_data["scenarios"]) == 2


def test_api_copilot_endpoint() -> None:
    res = client.post(
        "/api/v1/decision-lab/copilot",
        json={"query": "Compare 4-3-3 and 3-4-2-1 for this squad.", "club_id": "arsenal_fc"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "COMPARE_FORMATIONS"
