"""Phase 15 Comprehensive Test Suite: Global Football Research, Adaptive Intelligence,
Cross-Competition Generalization, and Adversarial Integrity Tests.
"""

import hashlib
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.phase15 import (
    DataSufficiencyStatus,
    EpistemicModality,
    FeeTaxonomy,
    GeneralizationDomain,
    HypothesisValidationResult,
    PatternFamily,
    ResearchLifecycleState,
    RoleTransitionStatus,
    TrajectoryClass,
    ValidationMatrixStatus,
)
from app.phase15.adaptive_candidates import AdaptiveModelCandidateEngine
from app.phase15.causality_guardrail import CausalityGuardrail, CausalityViolationError
from app.phase15.cohort_engine import CohortEngine
from app.phase15.copilot_v5 import CopilotV5Dispatcher
from app.phase15.cross_competition_generalization import CrossCompetitionGeneralizationEngine
from app.phase15.experiment_engine import ExperimentEngine
from app.phase15.feature_discovery import FeatureDiscoveryEngine
from app.phase15.global_validation_matrix import GlobalValidationMatrix
from app.phase15.hypothesis_governance import HypothesisGovernanceEngine
from app.phase15.league_translation import LeagueTranslationEngine
from app.phase15.model_error_research import ModelErrorResearchEngine
from app.phase15.pattern_discovery import PatternDiscoveryEngine
from app.phase15.player_trajectory_research import PlayerTrajectoryResearchEngine
from app.phase15.research_evidence_graph import (
    ResearchEvidenceGraphBuilder,
    ResearchGraphEdge,
    ResearchGraphNode,
)
from app.phase15.research_questions import ResearchQuestionRegistry
from app.phase15.role_transition_research import RoleTransitionResearchEngine
from app.phase15.tactical_pattern_research import TacticalPatternResearchEngine
from app.phase15.transfer_market_research import TransferMarketResearchEngine


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. COHORT ENGINE & IMMUTABILITY TESTS
# ==============================================================================

def test_cohort_creation_and_hashing():
    engine = CohortEngine()
    cohort = engine.create_cohort(
        cohort_id="c_test_01",
        cohort_type="PLAYER",
        name="U21 Central Midfielders",
        filter_criteria={"age_max": 21, "position": "CM"},
        entity_ids=["p1", "p2", "p3"],
    )
    assert cohort.cohort_id == "c_test_01"
    assert cohort.sample_size == 3
    assert len(cohort.cohort_hash) == 64
    assert cohort.is_immutable is False


def test_adversarial_cohort_immutability():
    """Adversarial Test #2: Modify an old cohort after being sealed."""
    engine = CohortEngine()
    cohort = engine.create_cohort(
        cohort_id="c_sealed_01",
        cohort_type="TRANSFER",
        name="Cross-League Transfers",
        filter_criteria={"min_fee": 10000000},
        entity_ids=["t1", "t2"],
        version="1.0.0",
    )
    engine.seal_cohort("c_sealed_01")
    assert cohort.is_immutable is True

    # Attempting to update a sealed cohort MUST NOT overwrite the original in place.
    # It must fork into a new version.
    updated = engine.update_cohort(
        cohort_id="c_sealed_01",
        new_filter_criteria={"min_fee": 15000000},
        new_entity_ids=["t1", "t2", "t3"],
    )

    # Original cohort must remain unchanged
    original = engine.get_cohort("c_sealed_01")
    assert original.version == "1.0.0"
    assert original.sample_size == 2
    assert original.is_immutable is True

    # Forked cohort has new version and parent lineage
    assert updated.version == "2.0.0"
    assert updated.parent_version == "1.0.0"
    assert updated.sample_size == 3


# ==============================================================================
# 2. PATTERN DISCOVERY & NON-CAUSAL POLICY
# ==============================================================================

def test_pattern_discovery_candidate_and_sample_gating():
    engine = PatternDiscoveryEngine(min_sample_threshold=10)

    # Low sample candidate
    p_low = engine.discover_pattern(
        pattern_id="pat_low_01",
        family=PatternFamily.PLAYER_TRAJECTORY,
        title="Apparent sprint speed increase",
        description="Observed slight speed increase",
        sample_size=4,
        temporal_scope={"start": "2023-01-01", "end": "2023-06-01"},
        competition_scope=["EPL"],
        effect_estimate=0.12,
        uncertainty="Very high (N=4)",
    )
    assert p_low.data_quality_status == DataSufficiencyStatus.LOW_SAMPLE
    assert p_low.epistemic_status == EpistemicModality.ANALYSIS

    # Adequate sample candidate
    p_good = engine.discover_pattern(
        pattern_id="pat_good_01",
        family=PatternFamily.TRANSFER_MARKET,
        title="Market residual across leagues",
        description="Realized fee variance across transfers",
        sample_size=25,
        temporal_scope={"start": "2022-01-01", "end": "2024-01-01"},
        competition_scope=["EPL", "Bundesliga"],
        effect_estimate=0.22,
        uncertainty="Moderate",
    )
    assert p_good.data_quality_status == DataSufficiencyStatus.DATA_AVAILABLE


def test_adversarial_causality_guardrail():
    """Adversarial Test #7: Claim causality from correlation."""
    # Strict audit must reject causal assertions
    compliant, violations = CausalityGuardrail.audit_text("Signing player X caused victory against opponent.", strict=False)
    assert compliant is False
    assert len(violations) > 0

    with pytest.raises(CausalityViolationError):
        CausalityGuardrail.audit_text("Tactical formation caused the win.", strict=True)

    # Sanitizer must replace causal phrasing
    sanitized = CausalityGuardrail.sanitize_text("The tactical change caused improved progression and caused the win.")
    assert "caused" not in sanitized.lower()
    assert "associated with" in sanitized.lower() or "coincided with" in sanitized.lower()


# ==============================================================================
# 3. HYPOTHESIS GOVERNANCE & LIFECYCLE
# ==============================================================================

def test_hypothesis_lifecycle_and_validation():
    engine = HypothesisGovernanceEngine(min_validation_sample=20)
    hypo = engine.create_hypothesis(
        hypothesis_id="hypo_test_01",
        statement="Fullbacks transitioning to wide centre-back maintain progressive passing under pressure.",
        source_patterns=["pat_test"],
        supporting_observations=[{"obs": "good retention"}],
        sample_size=15,
        affected_competitions=["EPL"],
        affected_seasons=["2023/24"],
    )
    assert hypo.lifecycle_state == ResearchLifecycleState.HYPOTHESIS
    assert hypo.epistemic_status == EpistemicModality.HYPOTHESIS
    assert hypo.is_causal_claim is False

    # Independent holdout validation with sufficient sample & effect
    val = engine.validate_hypothesis(
        hypothesis_id="hypo_test_01",
        validation_id="val_test_01",
        methodology="INDEPENDENT_COHORT",
        holdout_sample_size=28,
        holdout_window={"start": "2024-01-01", "end": "2024-05-30"},
        metrics={"effect_size": 0.24, "p_value": 0.015},
    )
    assert val.result == HypothesisValidationResult.SUPPORTED
    assert hypo.lifecycle_state == ResearchLifecycleState.VALIDATED


def test_adversarial_hypothesis_leakage_and_modality():
    """Adversarial Test #1 & #4: Leakage detection rejects validation; hypothesis != fact."""
    engine = HypothesisGovernanceEngine(min_validation_sample=20)
    hypo = engine.create_hypothesis(
        hypothesis_id="hypo_leak_01",
        statement="Young strikers show higher conversion in second seasons.",
        source_patterns=[],
        supporting_observations=[],
        sample_size=30,
        affected_competitions=["EPL"],
        affected_seasons=["2023/24"],
    )

    # When leakage is detected in validation cohort, result is NOT_SUPPORTED and state is REJECTED
    val = engine.validate_hypothesis(
        hypothesis_id="hypo_leak_01",
        validation_id="val_leak_01",
        methodology="TEMPORAL_HOLDOUT",
        holdout_sample_size=25,
        holdout_window={"start": "2024-01-01", "end": "2024-05-30"},
        metrics={"effect_size": 0.35, "p_value": 0.001},
        leakage_detected=True,
    )
    assert val.result == HypothesisValidationResult.NOT_SUPPORTED
    assert val.leakage_audit_passed is False
    assert hypo.lifecycle_state == ResearchLifecycleState.REJECTED
    # Epistemic status remains HYPOTHESIS, never OBSERVED
    assert hypo.epistemic_status == EpistemicModality.HYPOTHESIS


# ==============================================================================
# 4. CROSS-COMPETITION GENERALIZATION & ANTI-POOLING
# ==============================================================================

def test_cross_competition_evaluation_and_anti_pooling():
    """Adversarial Test #5: Prohibit silent pooling; flag cross-league degradation."""
    engine = CrossCompetitionGeneralizationEngine(min_test_samples=15)

    # In-domain: EPL -> EPL
    res_in = engine.evaluate_generalization(
        engine_name="Valuation",
        train_competitions=["EPL"],
        test_competition="EPL",
        sample_size_train=500,
        sample_size_test=100,
        in_domain_metric=0.12,
        cross_domain_metric=0.12,
    )
    assert res_in.generalization_domain == GeneralizationDomain.IN_DOMAIN
    assert res_in.validation_status == ValidationMatrixStatus.VALIDATED

    # Cross-domain with degradation: EPL -> Ligue_1
    res_cross = engine.evaluate_generalization(
        engine_name="Valuation",
        train_competitions=["EPL"],
        test_competition="Ligue_1",
        sample_size_train=500,
        sample_size_test=80,
        in_domain_metric=0.12,
        cross_domain_metric=0.155,  # ~29% degradation
    )
    assert res_cross.generalization_domain == GeneralizationDomain.CROSS_DOMAIN
    assert res_cross.validation_status == ValidationMatrixStatus.PARTIALLY_VALIDATED


def test_adversarial_ood_generalization():
    """Adversarial Test #9: High drift / OOD data cannot be VALIDATED."""
    engine = CrossCompetitionGeneralizationEngine(min_test_samples=15)
    res_ood = engine.evaluate_generalization(
        engine_name="MatchPredictor",
        train_competitions=["EPL"],
        test_competition="UnknownLeague",
        sample_size_train=500,
        sample_size_test=40,
        in_domain_metric=0.15,
        cross_domain_metric=0.28,
        distribution_drift_psi=0.35,  # > 0.25 threshold
    )
    assert res_ood.generalization_domain == GeneralizationDomain.OOD
    assert res_ood.validation_status == ValidationMatrixStatus.OOD
    assert res_ood.is_statistically_sound is False


# ==============================================================================
# 5. LEAGUE TRANSLATION INTELLIGENCE
# ==============================================================================

def test_descriptive_league_translation():
    engine = LeagueTranslationEngine(min_samples_per_dimension=5)
    sample_data = [
        {"contribution_src": 0.60, "contribution_tgt": 0.54, "minutes_src": 2500, "minutes_tgt": 2100, "valuation_src": 30.0, "valuation_tgt": 36.0},
        {"contribution_src": 0.50, "contribution_tgt": 0.45, "minutes_src": 2200, "minutes_tgt": 1800, "valuation_src": 20.0, "valuation_tgt": 22.0},
        {"contribution_src": 0.70, "contribution_tgt": 0.62, "minutes_src": 2800, "minutes_tgt": 2300, "valuation_src": 45.0, "valuation_tgt": 52.0},
        {"contribution_src": 0.55, "contribution_tgt": 0.50, "minutes_src": 2400, "minutes_tgt": 2000, "valuation_src": 25.0, "valuation_tgt": 28.0},
        {"contribution_src": 0.65, "contribution_tgt": 0.58, "minutes_src": 2600, "minutes_tgt": 2200, "valuation_src": 35.0, "valuation_tgt": 40.0},
        {"contribution_src": 0.45, "contribution_tgt": 0.40, "minutes_src": 1900, "minutes_tgt": 1500, "valuation_src": 15.0, "valuation_tgt": 18.0},
    ]
    rep = engine.analyze_translation("Serie_A", "EPL", sample_data)
    assert rep.total_transitioned_players == 6
    assert "contribution" in rep.dimensions
    assert rep.dimensions["contribution"].evidence_status == "OBSERVED_ASSOCIATION"
    assert "caused" not in rep.non_causal_statement.lower()


# ==============================================================================
# 6. PLAYER TRAJECTORY RESEARCH
# ==============================================================================

def test_player_trajectory_representation_and_breakout():
    engine = PlayerTrajectoryResearchEngine()
    rep = engine.analyze_player_trajectory(
        player_id="ply_young_prodigy",
        metric_name="goal_contributions_p90",
        past_observed=[
            {"season": "2021/22", "competition": "EPL", "minutes": 1400, "value": 0.32},
            {"season": "2022/23", "competition": "EPL", "minutes": 2200, "value": 0.44},
            {"season": "2023/24", "competition": "EPL", "minutes": 2800, "value": 0.62},
        ],
        current_observed={"season": "2024/25", "competition": "EPL", "minutes": 1500, "value": 0.71},
    )
    assert len(rep.past_observed) == 3
    assert rep.current_observed is not None
    assert rep.is_breakout is True
    assert rep.trajectory_classification == TrajectoryClass.SUSTAINED_IMPROVEMENT
    assert rep.projected_range is not None


# ==============================================================================
# 7. ROLE TRANSITION RESEARCH
# ==============================================================================

def test_role_transition_sample_gating():
    engine = RoleTransitionResearchEngine(min_minutes=450, min_appearances=5)

    # 1 match: Insufficient data
    r_one = engine.evaluate_transition(
        player_id="p1",
        source_role="CB",
        target_role="FB",
        target_role_minutes=90,
        target_role_appearances=1,
        competition="EPL",
        temporal_span={"start": "2024-01-01", "end": "2024-01-02"},
    )
    assert r_one.status == RoleTransitionStatus.INSUFFICIENT_DATA

    # 3 matches, 250 mins: Possible
    r_poss = engine.evaluate_transition(
        player_id="p2",
        source_role="CM",
        target_role="AM",
        target_role_minutes=250,
        target_role_appearances=3,
        competition="La_Liga",
        temporal_span={"start": "2024-01-01", "end": "2024-02-15"},
    )
    assert r_poss.status == RoleTransitionStatus.ROLE_TRANSITION_POSSIBLE

    # 10 matches, 850 mins: Confirmed
    r_conf = engine.evaluate_transition(
        player_id="p3",
        source_role="Winger",
        target_role="Central Forward",
        target_role_minutes=850,
        target_role_appearances=10,
        competition="Bundesliga",
        temporal_span={"start": "2023-08-01", "end": "2024-01-30"},
    )
    assert r_conf.status == RoleTransitionStatus.ROLE_TRANSITION_CONFIRMED


# ==============================================================================
# 8. TACTICAL PATTERN RESEARCH & EPISTEMIC SEPARATION
# ==============================================================================

def test_tactical_research_epistemic_separation():
    engine = TacticalPatternResearchEngine()
    rep = engine.record_tactical_research(
        team_id="mancity",
        competition="EPL",
        season="2023/24",
        matches_observed=38,
        primary_shape="4-3-3",
        in_possession_structure="3-2-4-1",
        out_of_possession_structure="4-4-2",
        measured_width=54.2,
        high_press_line=51.0,
        progression_bias={"left": 0.35, "central": 0.35, "right": 0.30},
        counter_press_index=0.92,
        box_density=0.81,
        counterfactuals=[{"scenario_id": "cf_01", "simulated_formation": "3-5-2", "simulated_variation": "twin_strikers"}],
    )
    assert rep.observed_pattern.modality == "OBSERVED"
    assert rep.modelled_interpretation.modality == "MODELLED"
    assert rep.counterfactual_scenarios[0].modality == "COUNTERFACTUAL"
    assert rep.epistemic_audit_passed is True


# ==============================================================================
# 9. TRANSFER MARKET & FEE TAXONOMY (ZERO-FABRICATION)
# ==============================================================================

def test_adversarial_transfer_fee_taxonomy_and_zero_fabrication():
    """Adversarial Test #10: Undisclosed / unknown fee must NEVER be converted to 0.0."""
    engine = TransferMarketResearchEngine()

    # Free transfer: realized fee is explicitly 0.0
    r_free = engine.record_transfer(
        transfer_id="t_free",
        player_id="pf",
        selling_club="A",
        buying_club="B",
        source_competition="EPL",
        destination_competition="La_Liga",
        transfer_date="2024-07-01",
        fee_type=FeeTaxonomy.FREE_TRANSFER,
        realized_fee_eur=0.0,
        modelled_valuation_eur=50000000.0,
        age_at_transfer=26,
        position="FW",
    )
    assert r_free.realized_fee_eur == 0.0
    assert r_free.is_valid_for_residuals is True

    # Undisclosed fee: realized fee must be None (even if caller attempted 0.0)
    r_undisclosed = engine.record_transfer(
        transfer_id="t_undisc",
        player_id="pu",
        selling_club="C",
        buying_club="D",
        source_competition="Bundesliga",
        destination_competition="EPL",
        transfer_date="2024-08-01",
        fee_type=FeeTaxonomy.UNDISCLOSED,
        realized_fee_eur=0.0,  # Adversarial injection of 0.0
        modelled_valuation_eur=30000000.0,
        age_at_transfer=22,
        position="MF",
    )
    # Anti-fabrication check: must be converted to None, and excluded from residual calculation
    assert r_undisclosed.realized_fee_eur is None
    assert r_undisclosed.is_valid_for_residuals is False
    assert r_undisclosed.valuation_residual_pct is None


# ==============================================================================
# 10. MODEL ERROR RESEARCH & ANTI-SMOOTHING
# ==============================================================================

def test_adversarial_weak_subgroup_not_hidden():
    """Adversarial Test #6: Prohibit hiding weak subgroups through aggregate averaging."""
    engine = ModelErrorResearchEngine(min_sample_size=10)
    slices = [
        {"slice_type": "GLOBAL", "slice_key": "ALL", "sample_size": 1000, "mae": 0.12, "brier": 0.16, "log_loss": 0.42, "ece": 0.035},
        {"slice_type": "POSITION", "slice_key": "Winger", "sample_size": 250, "mae": 0.22, "brier": 0.28, "log_loss": 0.65, "ece": 0.12},  # Severe weakness!
        {"slice_type": "AGE", "slice_key": "Prime", "sample_size": 750, "mae": 0.09, "brier": 0.12, "log_loss": 0.35, "ece": 0.02},
    ]
    rep = engine.analyze_model_errors(
        model_id="test_model",
        model_version="1.0.0",
        evaluation_window={"start": "2023-01-01", "end": "2023-12-31"},
        prediction_slices=slices,
    )
    assert rep.silent_averaging_audit_passed is True
    # The winger slice MUST be captured in weakest_subgroups
    assert len(rep.weakest_subgroups) >= 1
    winger_slice = rep.weakest_subgroups[0]
    assert winger_slice.slice_key == "Winger"
    assert winger_slice.is_weak_subgroup is True
    assert len(rep.systematic_bias_indicators) >= 1


# ==============================================================================
# 11. EXPERIMENT ENGINE & DETERMINISTIC REPLAY
# ==============================================================================

def test_experiment_reproducibility_and_immutability():
    """Adversarial Test #3: Completed experiments are immutable; replay produces identical hash."""
    engine = ExperimentEngine()
    exp = engine.create_experiment(
        experiment_id="exp_rep_01",
        hypothesis_id="h1",
        cohort_id="c1",
        dataset_id="d1",
        features_used=["f1", "f2"],
        methodology="COHORT_REGRESSION",
        evaluation_window={"start": "2023-01-01", "end": "2023-12-31"},
        validation_strategy="OUT_OF_SAMPLE_20",
    )
    initial_hash = exp.experiment_hash

    # Complete experiment
    engine.complete_experiment(
        experiment_id="exp_rep_01",
        effect_estimate=0.25,
        confidence_interval=(0.10, 0.40),
        p_value=0.012,
        subgroup_breakdown={"sub1": {"effect": 0.25}},
        summary_findings=["Positive association detected."],
    )
    completed_hash = exp.experiment_hash
    assert completed_hash != initial_hash
    assert exp.is_completed is True

    # Attempting to re-complete or modify must raise ValueError
    with pytest.raises(ValueError):
        engine.complete_experiment(
            experiment_id="exp_rep_01",
            effect_estimate=0.30,
            confidence_interval=(0.15, 0.45),
            p_value=0.005,
            subgroup_breakdown={},
            summary_findings=[],
        )


# ==============================================================================
# 12. FEATURE DISCOVERY & ADAPTIVE MODEL PROMOTION
# ==============================================================================

def test_feature_discovery_and_governed_promotion():
    """Adversarial Test #8: Automated model promotion is strictly blocked."""
    f_engine = FeatureDiscoveryEngine()
    feat = f_engine.register_candidate(
        candidate_id="f_cand_01",
        feature_name="deep_progression_p90",
        target_metric="xg_chain",
        rationale="Strong correlation with team goal conversion",
        discovered_in_experiments=["exp_rep_01"],
        effect_magnitude=0.28,
        stability_score=0.91,
    )
    assert feat.production_ready is False

    ad_engine = AdaptiveModelCandidateEngine()

    # Attempting auto-promotion must raise PermissionError
    with pytest.raises(PermissionError):
        ad_engine.review_candidate_for_promotion(
            candidate_id="challenger_m1",
            champion_id="champion_m1",
            target_type="MODEL",
            champion_metrics={"brier": 0.18, "ece": 0.04},
            challenger_metrics={"brier": 0.15, "ece": 0.035},
            evaluation_windows=[{"name": "w1"}],
            subgroup_parity_passed=True,
            author="bot",
            auto_promote_attempt=True,
        )

    # Governed human-approved promotion
    promo = ad_engine.review_candidate_for_promotion(
        candidate_id="challenger_m1",
        champion_id="champion_m1",
        target_type="MODEL",
        champion_metrics={"brier": 0.18, "ece": 0.04},
        challenger_metrics={"brier": 0.15, "ece": 0.035},
        evaluation_windows=[{"name": "w1"}],
        subgroup_parity_passed=True,
        author="lead_scout_analyst",
        auto_promote_attempt=False,
    )
    assert promo.promotion_status == "PROMOTED"


# ==============================================================================
# 13. GLOBAL VALIDATION MATRIX
# ==============================================================================

def test_global_validation_matrix_coverage():
    matrix = GlobalValidationMatrix()
    matrix.register_cell(
        engine="ValuationEngine",
        competition="EPL",
        season="2023/24",
        position="MF",
        role="CM",
        age_band="21-24",
        confidence_tier="HIGH",
        ood_status="IN_DOMAIN",
        data_status=DataSufficiencyStatus.DATA_AVAILABLE,
        sample_size=45,
        primary_metric_name="MAE",
        metric_value=0.11,
    )
    cells = matrix.query_cells(engine="ValuationEngine")
    assert len(cells) == 1
    assert cells[0].validation_status == ValidationMatrixStatus.VALIDATED

    summary = matrix.get_summary_coverage()
    assert summary["validated_cells"] == 1


# ==============================================================================
# 14. RESEARCH EVIDENCE GRAPH
# ==============================================================================

def test_research_evidence_graph_digest():
    nodes = [
        ResearchGraphNode(node_id="n1", node_type="QUESTION", label="Q1", epistemic_status=EpistemicModality.ANALYSIS, provenance="p1"),
        ResearchGraphNode(node_id="n2", node_type="HYPOTHESIS", label="H1", epistemic_status=EpistemicModality.HYPOTHESIS, provenance="p2"),
    ]
    edges = [ResearchGraphEdge(source_id="n1", target_id="n2", edge_type="FRAMES")]
    graph = ResearchEvidenceGraphBuilder.build_graph("g1", nodes, edges)
    assert len(graph.graph_digest) == 64
    assert graph.node_count == 2
    assert graph.edge_count == 1


# ==============================================================================
# 15. COPILOT V5 DETERMINISTIC RESEARCH DISPATCHER
# ==============================================================================

def test_copilot_v5_dispatch_query_classes():
    dispatcher = CopilotV5Dispatcher()

    # 1. Hypothesis evidence
    r1 = dispatcher.dispatch("Find evidence for hypothesis")
    assert r1.query_class == "FIND_EVIDENCE_FOR_HYPOTHESIS"
    assert "caused" not in r1.summary_answer.lower()

    # 2. Transfer market residuals
    r2 = dispatcher.dispatch("Explain transfer-market residuals and valuation errors")
    assert r2.query_class == "EXPLAIN_TRANSFER_MARKET_RESIDUALS"
    assert r2.data_sufficiency == "DATA_AVAILABLE"

    # 3. Model failure boundary
    r3 = dispatcher.dispatch("Show where the pattern fails for this model")
    assert r3.query_class == "SHOW_WHERE_PATTERN_FAILS"

    # 4. Role transitions
    r4 = dispatcher.dispatch("Compare tactical role transitions for central defenders")
    assert r4.query_class == "COMPARE_TACTICAL_ROLE_TRANSITIONS"

    # 5. Champion vs Challenger
    r5 = dispatcher.dispatch("Compare champion vs challenger performance")
    assert r5.query_class == "COMPARE_CHAMPION_VS_CHALLENGER"


# ==============================================================================
# 16. REST API VALIDATION
# ==============================================================================

def test_api_research_endpoints(client: TestClient):
    # Questions
    rq = client.get("/api/v1/research/questions")
    assert rq.status_code == 200
    assert len(rq.json()) >= 1

    # Hypotheses
    rh = client.get("/api/v1/research/hypotheses")
    assert rh.status_code == 200
    assert len(rh.json()) >= 1

    # Cohorts
    rc = client.get("/api/v1/research/cohorts")
    assert rc.status_code == 200
    assert len(rc.json()) >= 1

    # Cross-competition
    rcc = client.get("/api/v1/research/cross-competition")
    assert rcc.status_code == 200
    assert len(rcc.json()) >= 1

    # Player trajectories
    rpt = client.get("/api/v1/research/player-trajectories")
    assert rpt.status_code == 200
    assert len(rpt.json()) >= 1

    # Transfer market
    rtm = client.get("/api/v1/research/transfer-market")
    assert rtm.status_code == 200
    data_tm = rtm.json()
    assert "summary_residuals" in data_tm

    # Model errors
    rme = client.get("/api/v1/research/model-errors")
    assert rme.status_code == 200
    assert len(rme.json()) >= 1

    # Validation matrix
    rvm = client.get("/api/v1/research/validation-matrix")
    assert rvm.status_code == 200
    assert "summary" in rvm.json()

    # Copilot V5
    rcop = client.post("/api/v1/research/copilot", json={"query": "Find evidence for hypothesis"})
    assert rcop.status_code == 200
    assert rcop.json()["query_class"] == "FIND_EVIDENCE_FOR_HYPOTHESIS"
