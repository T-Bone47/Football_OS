"""Phase 12 — Comprehensive Continuous Learning & Decision Evolution Test Suite (§30).

Tests all Phase 12 release gate criteria (G1–G26):
  - Continuous data impact propagation & historical decision immutability (§3)
  - Decision staleness & freshness assessment engine (§4)
  - Governed continuous model learning loop & zero silent promotion (§5, §28)
  - Deterministic retraining triggers & empirical drift thresholds (§6)
  - Champion vs Challenger comparative evaluation & candidate isolation (§7, §18, §19)
  - Longitudinal player trajectories V2 (OBSERVED/MODELLED/PROJECTED separation) (§8)
  - Breakout detection & developmental velocity (§10)
  - Emerging player multi-dimensional detection (§9)
  - Empirical tactical role transition tracking (§11)
  - Market inefficiency & value gap detection (§12)
  - Versioned benchmark recruitment profiles (§14)
  - Multi-mode recruitment candidate discovery & position gating (§13, §15)
  - Retrospective decision & post-transfer outcome alignment (§16, §17)
  - 10-tier Global Player Evidence Graph & cryptographic digest (§22)
  - Scout Copilot V2 deterministic tool dispatch (§23)
  - Operational Alerts V2 non-causal telemetry (§24)
"""
from __future__ import annotations

import pytest

from app.phase12 import (
    CandidateDiscoveryMode,
    DecisionFreshnessState,
    DecisionOutcomeAlignment,
    MarketOpportunityState,
    RetrainRecommendation,
)
from app.phase12.alerts_v2 import AlertCategoryV2, OperationalAlertsManagerV2
from app.phase12.benchmarks import BenchmarkProfileRegistry
from app.phase12.challenger_framework import ChallengerFramework
from app.phase12.copilot_v2 import ScoutCopilotV2Dispatcher
from app.phase12.data_impact import ContinuousDataImpactEngine
from app.phase12.decision_staleness import DecisionStalenessEngine
from app.phase12.emerging_players import EmergingPlayerEngine
from app.phase12.evidence_graph import PlayerEvidenceGraphBuilder
from app.phase12.learning_loop import ContinuousLearningPipeline
from app.phase12.market_inefficiency import MarketInefficiencyEngine
from app.phase12.player_trajectories import PlayerTrajectoryEngineV2
from app.phase12.post_decision_feedback import PostDecisionFeedbackEngine
from app.phase12.recruitment_discovery import AdvancedRecruitmentDiscoveryEngine
from app.phase12.retraining_triggers import RetrainingTriggerEngine
from app.phase12.role_transitions import RoleTransitionEngine


class TestDataImpactAndImmutability:
    """Tests continuous data impact propagation without mutating historical decisions (§3)."""

    def test_match_ingestion_propagates_impact_cleanly(self):
        engine = ContinuousDataImpactEngine()
        event = engine.propagate_match_ingestion(
            match_id="match_epl_20240401_01",
            competition_id="GB-PL",
            player_ids=["cand_inacio", "cand_saliba"],
            source_snapshot="bronze_test_snapshot_001",
            associated_decision_ids=["dec_rec_inacio_2027"],
        )

        assert event.impact_type == "MATCH_COMPLETION"
        assert "cand_inacio" in event.affected_entities
        assert "dec_rec_inacio_2027" in event.affected_decisions
        assert len(event.affected_features) >= 5
        # Invariant: Historical decisions must not be mutated
        assert event.historical_decisions_mutated is False

    def test_historical_decisions_unmutated_flag_invariant(self):
        engine = ContinuousDataImpactEngine()
        events = engine.list_events()
        for ev in events:
            assert ev.historical_decisions_mutated is False


class TestDecisionFreshnessAndStaleness:
    """Tests non-destructive decision freshness evaluations (§4)."""

    def test_current_decision_remains_current_when_stable(self):
        engine = DecisionStalenessEngine()
        assessment = engine.assess_decision(
            decision_id="dec_test_current",
            original_digest="hash_orig_123",
            original_features={"market_valuation_eur": 40_000_000.0, "role": "CB"},
            current_features={"market_valuation_eur": 41_000_000.0, "role": "CB"},
            original_models={"val": "v1.0"},
            current_models={"val": "v1.0"},
            decision_timestamp="2024-01-01",
        )
        assert assessment.freshness_state == DecisionFreshnessState.CURRENT
        assert assessment.materiality == "LOW"
        assert assessment.original_decision_preserved is True

    def test_valuation_shift_triggers_stale_or_monitor(self):
        engine = DecisionStalenessEngine()
        # Large valuation shift (+€12M)
        assessment = engine.assess_decision(
            decision_id="dec_test_val_shift",
            original_digest="hash_orig_456",
            original_features={"market_valuation_eur": 30_000_000.0, "role": "CB"},
            current_features={"market_valuation_eur": 42_000_000.0, "role": "CB"},
            original_models={"val": "v1.0"},
            current_models={"val": "v1.0"},
            decision_timestamp="2023-06-01",
        )
        assert assessment.freshness_state == DecisionFreshnessState.STALE
        assert assessment.materiality == "HIGH"
        assert assessment.valuation_delta_eur == 12_000_000.0
        assert assessment.original_decision_preserved is True

    def test_role_change_triggers_stale_state(self):
        engine = DecisionStalenessEngine()
        assessment = engine.assess_decision(
            decision_id="dec_test_role_shift",
            original_digest="hash_orig_789",
            original_features={"market_valuation_eur": 25_000_000.0, "role": "Traditional Fullback"},
            current_features={"market_valuation_eur": 26_000_000.0, "role": "Inverted Playmaker"},
            original_models={"role": "v1.0"},
            current_models={"role": "v1.0"},
            decision_timestamp="2023-08-01",
        )
        assert assessment.freshness_state == DecisionFreshnessState.STALE
        assert assessment.role_changed is True
        assert assessment.materiality == "HIGH"


class TestRetrainingTriggersAndContinuousLearning:
    """Tests retraining triggers and continuous learning loop safety (§5, §6, §28)."""

    def test_no_retrain_required_under_normal_psi(self):
        engine = RetrainingTriggerEngine()
        rec = engine.evaluate_model(
            model_id="match_model_epl",
            current_version="1.0.0",
            competition_scope="GB-PL",
            feature_psi=0.045,
            delta_brier=0.005,
            delta_ece=0.002,
            new_observations=25,
            days_since_train=40,
        )
        assert rec.recommendation == RetrainRecommendation.NO_RETRAIN_REQUIRED
        assert len(rec.triggers_fired) == 0

    def test_retrain_recommended_on_material_drift_or_calibration_drop(self):
        engine = RetrainingTriggerEngine()
        rec = engine.evaluate_model(
            model_id="match_model_drifted",
            current_version="1.0.0",
            competition_scope="DE-BL",
            feature_psi=0.265,  # Material drift >= 0.25
            delta_brier=0.065,  # Brier degradation >= 0.05
            delta_ece=0.048,    # ECE degradation >= 0.04
            new_observations=110,
            days_since_train=195,
        )
        assert rec.recommendation == RetrainRecommendation.RETRAIN_RECOMMENDED
        assert rec.recommended_action == "SCHEDULE_CHALLENGER_TRAINING_JOB"
        assert len(rec.triggers_fired) >= 3

    def test_learning_pipeline_blocks_silent_promotion(self):
        pipeline = ContinuousLearningPipeline()
        job = pipeline.start_learning_job(
            model_id="calibrated_multinomial_logit_v1",
            champion_version="1.0.0",
            challenger_version="1.1.0-challenger",
            competition_scope="GB-PL",
            dataset_version="DS-EPL-2023-24@v1.0.0",
        )
        assert job.promoted_to_production is False
        assert job.decision == "SHADOW_MONITORING"

        # Explicit promotion requires verified approver
        promoted = pipeline.promote_challenger(job.job_id, approver="Lead MLOps Architect")
        assert promoted.promoted_to_production is True
        assert promoted.decision == "PROMOTED"
        assert promoted.approver == "Lead MLOps Architect"


class TestChampionChallengerFramework:
    """Tests Champion vs Challenger comparative evaluations (§7, §18, §19)."""

    def test_challenger_comparison_metrics_and_recommendation(self):
        framework = ChallengerFramework()
        comp = framework.compare_models(
            model_family="MATCH_PREDICTION",
            competition_scope="GB-PL",
            champion_id="calibrated_multinomial_logit_v1",
            champion_version="1.0.0",
            challenger_id="challenger_logit_v2",
            challenger_version="2.0.0-candidate",
            dataset_version="DS-EPL-2023-24@v1.0.0",
            sample_size=120,
            metrics={
                "champion_brier": 0.538,
                "challenger_brier": 0.528,  # Better
                "champion_log_loss": 0.941,
                "challenger_log_loss": 0.925,  # Better
                "champion_ece": 0.042,
                "challenger_ece": 0.038,  # Better
            },
        )
        assert comp.challenger_outperforms is True
        assert comp.recommendation == "PROMOTE_TO_CANDIDATE"

    def test_challenger_rejected_when_metrics_degrade(self):
        framework = ChallengerFramework()
        comp = framework.compare_models(
            model_family="MATCH_PREDICTION",
            competition_scope="ES-L1",
            champion_id="champion_laliga_v1",
            champion_version="1.0.0",
            challenger_id="challenger_degraded_v1",
            challenger_version="1.1.0",
            dataset_version="DS-LALIGA-2023-24@v1.0.0",
            sample_size=80,
            metrics={
                "champion_brier": 0.580,
                "challenger_brier": 0.610,  # Worse
                "champion_log_loss": 1.010,
                "challenger_log_loss": 1.080,  # Worse
                "champion_ece": 0.080,
                "challenger_ece": 0.110,  # Worse
            },
        )
        assert comp.challenger_outperforms is False
        assert comp.recommendation == "REJECT_CHALLENGER"


class TestPlayerTrajectoryAndBreakout:
    """Tests Player Trajectory V2 and Breakout Detection (§8, §10)."""

    def test_observed_modelled_projected_separation(self):
        engine = PlayerTrajectoryEngineV2()
        history = [
            {"date": "2023-09-01", "minutes": 450, "contribution": 70.0, "data_class": "OBSERVED"},
            {"date": "2023-11-01", "minutes": 900, "contribution": 75.0, "data_class": "OBSERVED"},
            {"date": "2024-01-01", "minutes": 1350, "contribution": 80.0, "data_class": "OBSERVED"},
        ]
        profile = engine.evaluate_trajectory(
            player_id="player_test_traj",
            player_name="Test Player",
            current_club="Club A",
            competition_id="GB-PL",
            age=21,
            position="CB",
            role="Ball Playing Defender",
            history=history,
        )

        assert len(profile.observed_history) == 3
        for pt in profile.observed_history:
            assert pt["data_class"] == "OBSERVED"

        assert profile.modelled_state["data_class"] == "MODELLED"
        assert len(profile.projected_path) == 2
        for pt in profile.projected_path:
            assert pt["data_class"] == "PROJECTED"

    def test_breakout_detection_thresholds(self):
        engine = PlayerTrajectoryEngineV2()
        history = [
            {"date": "2023-09-01", "minutes": 450, "contribution": 70.0},
            {"date": "2023-11-01", "minutes": 900, "contribution": 78.0},
            {"date": "2024-01-01", "minutes": 1350, "contribution": 84.0},
        ]
        profile = engine.evaluate_trajectory(
            player_id="player_breakout",
            player_name="Breakout Talent",
            current_club="Club B",
            competition_id="GB-PL",
            age=20,
            position="CB",
            role="Ball Playing Defender",
            history=history,
        )
        assert profile.breakout_signal is not None
        assert profile.breakout_signal.breakout_detected is True
        assert profile.development_velocity >= 3.0

    def test_insufficient_sample_blocks_breakout(self):
        engine = PlayerTrajectoryEngineV2()
        # Only 200 minutes (< 450 required)
        history = [{"date": "2023-09-01", "minutes": 200, "contribution": 85.0}]
        profile = engine.evaluate_trajectory(
            player_id="player_small_sample",
            player_name="Small Sample Player",
            current_club="Club C",
            competition_id="GB-PL",
            age=19,
            position="FW",
            role="Winger",
            history=history,
        )
        assert profile.breakout_signal.minimum_sample_met is False
        assert profile.breakout_signal.breakout_detected is False


class TestEmergingPlayerEngine:
    """Tests multi-dimensional emerging talent signals (§9)."""

    def test_detect_emergence_u23_candidate(self):
        engine = EmergingPlayerEngine()
        opp = engine.detect_emergence(
            player_id="player_emg_test",
            player_name="Emerging Midfielder",
            age=21,
            current_club="Club D",
            competition_id="GB-PL",
            position="CM",
            role="Box to Box Midfielder",
            minutes_gain_pct=42.0,
            contribution_gain_pts=14.5,
            role_stability="HIGH",
            tactical_fit_score=87.0,
            modelled_valuation_eur=18_000_000.0,
            comparable_range_eur="€25M–€30M",
            valuation_lag_pct=32.0,
        )
        assert opp.status == "EMERGING_OPPORTUNITY"
        assert opp.confidence == "HIGH"
        assert len(opp.evidence) >= 3


class TestRoleTransitionEngine:
    """Tests tactical role transitions and non-causal reporting (§11)."""

    def test_role_transition_detection_and_non_causal_text(self):
        engine = RoleTransitionEngine()
        trans = engine.detect_transition(
            player_id="player_trans_test",
            player_name="Tactical Fullback",
            current_club="Club E",
            competition_id="GB-PL",
            position="LB",
            previous_role="Traditional Fullback",
            current_role="Inverted Playmaker",
            sample_minutes=1200,
            metric_shifts={
                "central_touches_pct": {"previous": 22.0, "current": 48.0},
            },
        )
        assert trans is not None
        assert trans.previous_role == "Traditional Fullback"
        assert trans.current_role == "Inverted Playmaker"
        # Non-causal verification: mentions "Observed role profile shifted"
        assert any("Observed role profile shifted" in ev for ev in trans.observational_evidence)


class TestMarketInefficiencyAndValueGaps:
    """Tests market value gap detection (§12)."""

    def test_value_gap_opportunity_state_assignment(self):
        engine = MarketInefficiencyEngine()
        signal = engine.evaluate_opportunity(
            player_id="player_gap_test",
            player_name="Undervalued CB",
            current_club="Club F",
            competition_id="PT-PL",
            position="CB",
            age=22,
            observed_reference_eur=25_000_000.0,
            modelled_valuation_eur=36_000_000.0,
            lower_bound_eur=32_000_000.0,
            upper_bound_eur=41_000_000.0,
            comparable_min_eur=33_000_000.0,
            comparable_max_eur=39_000_000.0,
        )
        assert signal.opportunity_state == MarketOpportunityState.HIGH_DATA_CONFIDENCE_VALUE_GAP
        assert signal.raw_value_gap_eur == 11_000_000.0
        assert signal.value_gap_pct == 44.0


class TestBenchmarkProfilesAndRecruitmentDiscovery:
    """Tests benchmark profile definition and multi-mode candidate generation (§13, §14, §15)."""

    def test_create_versioned_benchmark_normalizes_weights(self):
        registry = BenchmarkProfileRegistry()
        profile = registry.create_benchmark(
            name="2026 CB Benchmark",
            position="CB",
            target_role="Ball Playing Defender",
            formation="4-3-3",
            dimension_weights={"defending": 50.0, "passing": 50.0},
            source_reference_players=["Player X"],
            competition_scope=["GB-PL"],
            version="1.0.0",
        )
        assert profile.dimension_weights["defending"] == 0.5
        assert profile.dimension_weights["passing"] == 0.5
        assert profile.profile_digest != ""

    def test_multi_mode_discovery_with_hard_position_gating(self):
        engine = AdvancedRecruitmentDiscoveryEngine()
        candidates = engine.discover_candidates(
            target_position="CB",
            target_role="Ball Playing Defender",
            mode=CandidateDiscoveryMode.EMERGING,
            max_age=25,
            max_budget_eur=50_000_000.0,
        )
        assert len(candidates) >= 1
        for c in candidates:
            assert c.position == "CB"
            assert c.age <= 25
            assert c.modelled_valuation_eur <= 50_000_000.0


class TestPostDecisionFeedbackEngine:
    """Tests retrospective decision evaluation without temporal leakage (§16, §17)."""

    def test_aligned_decision_outcome(self):
        engine = PostDecisionFeedbackEngine()
        rec = engine.evaluate_feedback(
            decision_id="dec_feedback_test",
            player_id="player_feed_test",
            player_name="Transferred Player",
            destination_club="Arsenal",
            decision_date="2023-08-01",
            expected_minutes=1200,
            realized_minutes=1250,
            expected_contrib=80.0,
            realized_contrib=82.0,
            expected_fit=85.0,
            realized_fit=86.5,
            fee_paid_eur=35_000_000.0,
            current_valuation_eur=42_000_000.0,
        )
        assert rec.alignment_state == DecisionOutcomeAlignment.ALIGNED
        assert rec.minutes_alignment_pct >= 100.0
        assert rec.temporal_isolation_verified is True

    def test_insufficient_followup_for_low_minutes(self):
        engine = PostDecisionFeedbackEngine()
        rec = engine.evaluate_feedback(
            decision_id="dec_injured_test",
            player_id="player_injured",
            player_name="Injured Signing",
            destination_club="Arsenal",
            decision_date="2023-08-01",
            expected_minutes=1200,
            realized_minutes=90,  # < 200 mins
            expected_contrib=80.0,
            realized_contrib=75.0,
            expected_fit=85.0,
            realized_fit=80.0,
            fee_paid_eur=30_000_000.0,
            current_valuation_eur=28_000_000.0,
        )
        assert rec.alignment_state == DecisionOutcomeAlignment.INSUFFICIENT_FOLLOWUP


class TestEvidenceGraphAndCopilotV2:
    """Tests 10-tier evidence graph and deterministic Copilot V2 (§22, §23, §24)."""

    def test_player_evidence_graph_assembly_and_digest(self):
        builder = PlayerEvidenceGraphBuilder()
        graph = builder.build_graph(player_id="cand_inacio", player_name="Gonçalo Inácio")
        assert len(graph.nodes) == 10
        assert len(graph.edges) >= 9
        assert graph.graph_digest != ""
        assert graph.nodes[0].source_layer == "Bronze"
        assert graph.nodes[-1].source_layer == "DecisionStore"

    def test_copilot_v2_deterministic_queries(self):
        dispatcher = ScoutCopilotV2Dispatcher()

        # Query 1: Emerging players
        res1 = dispatcher.dispatch("Find emerging U23 centre backs.")
        assert res1["intent"] == "FIND_EMERGING_PLAYERS"
        assert res1["resolved"] is True
        assert res1["count"] >= 1

        # Query 2: Value gaps
        res2 = dispatcher.dispatch("Show players whose valuation appears below their comparable range.")
        assert res2["intent"] == "DETECT_VALUE_GAPS"
        assert res2["resolved"] is True

        # Query 3: Role change
        res3 = dispatcher.dispatch("Why did this player's role change?")
        assert res3["intent"] == "INSPECT_ROLE_TRANSITIONS"
        assert res3["resolved"] is True

        # Query 4: Stale decisions
        res4 = dispatcher.dispatch("Which recruitment decisions are stale?")
        assert res4["intent"] == "AUDIT_DECISION_FRESHNESS"
        assert res4["resolved"] is True

        # Query 5: Retraining
        res5 = dispatcher.dispatch("Which models need retraining?")
        assert res5["intent"] == "EVALUATE_RETRAINING_TRIGGERS"
        assert res5["resolved"] is True

    def test_operational_alerts_v2(self):
        manager = OperationalAlertsManagerV2()
        alerts = manager.list_alerts()
        assert len(alerts) >= 3
        cats = [a.category for a in alerts]
        assert AlertCategoryV2.EMERGING_PLAYER in cats
        assert AlertCategoryV2.ROLE_TRANSITION in cats
        assert AlertCategoryV2.DECISION_STALE in cats
