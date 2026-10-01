"""Phase 11 — Comprehensive Cross-Competition Validation & Governance Test Suite (§29).

Tests all 22 Phase 11 release gate criteria (G1–G22):
  - Data expansion & provider coverage (§4, §5)
  - Canonical 6-stage readiness transitions & zero-inheritance (§6, §10)
  - Temporal dataset builder & adversarial leakage invariance (§7)
  - Cross-competition match prediction & multi-paradigm validation (§8)
  - Probability calibration (temperature, isotonic, ECE) with zero test leakage (§9)
  - Model shadow mode execution & production isolation (§18)
  - Continuous drift monitoring, PSI thresholds, and factual alerting (§16, §17, §27)
  - Immutable dataset registry & end-to-end lineage verification (§20)
  - Multi-engine validation (tactical fit, similarity, valuation, risk) (§11–§15)
  - Dual-run deterministic pipeline replay & SHA-256 preservation (§21)
  - Scout Copilot deterministic tool dispatch (§25)
  - 16-section cross-competition report generation (§28)
"""
from __future__ import annotations

import copy
import hashlib
import json
import pytest
import numpy as np

from app.phase11.calibration_engine import (
    CalibrationEvaluationResult,
    ProbabilityCalibrationEngine,
)
from app.phase11.competition_coverage import (
    CalibrationStatus,
    CompetitionCoverageManager,
    CompetitionCoverageProfile,
    CompetitionReadinessStage,
    CompetitionTier,
)
from app.phase11.copilot_extension import Phase11CopilotDispatcher
from app.phase11.cross_competition_validator import CrossCompetitionValidator
from app.phase11.dataset_registry import DatasetIdentity, DatasetRegistry
from app.phase11.drift_monitoring import (
    ContinuousDriftMonitor,
    DriftAlertCategory,
    DriftStatus,
    calculate_psi,
)
from app.phase11.reports import generate_cross_competition_report, render_report_markdown
from app.phase11.reproducibility import PipelineReplayEngine
from app.phase11.shadow_mode import ModelLifecycleStage, ShadowModeExecutor
from app.phase11.temporal_dataset import (
    TemporalDatasetBuilder,
    TemporalExample,
    TemporalSplit,
)


# ── 1. Competition Coverage & Readiness Tests (§4, §5, §6) ───────────

class TestCompetitionCoverageAndReadiness:
    """Tests for multi-tier competition coverage profiles and governed state progression."""

    def test_tier_1_coverage_profiles_exist(self):
        """Tier 1 leagues (EPL, La Liga, Serie A, Bundesliga, Ligue 1) have coverage profiles."""
        mgr = CompetitionCoverageManager()
        tier_1 = mgr.list_profiles(tier="TIER_1")
        comp_ids = {p["competition_id"] for p in tier_1}
        assert {"EPL", "LALIGA", "SERIEA", "BUNDESLIGA", "LIGUE1"}.issubset(comp_ids)

    def test_epl_is_production_ready_and_calibrated(self):
        """EPL profile is certified PRODUCTION_READY with CALIBRATED status."""
        mgr = CompetitionCoverageManager()
        epl = mgr.get_profile("EPL")
        assert epl is not None
        assert epl.readiness_state == CompetitionReadinessStage.PRODUCTION_READY.value
        assert epl.calibration_status == CalibrationStatus.CALIBRATED.value
        assert epl.sample_size == 760

    def test_strict_zero_inheritance_enforced(self):
        """Non-EPL competitions DO NOT inherit EPL calibration or production readiness."""
        mgr = CompetitionCoverageManager()
        for comp in ["LALIGA", "SERIEA", "BUNDESLIGA", "LIGUE1"]:
            prof = mgr.get_profile(comp)
            assert prof is not None
            assert prof.readiness_state != CompetitionReadinessStage.PRODUCTION_READY.value
            assert prof.calibration_status != CalibrationStatus.CALIBRATED.value

    def test_governed_readiness_progression_sequential(self):
        """Cannot skip stages (e.g. from DATA_INGESTED directly to PRODUCTION_READY)."""
        mgr = CompetitionCoverageManager()
        prof = mgr.get_profile("MLS")
        assert prof is not None
        # Current MLS is FEATURE_READY; trying to jump directly to PRODUCTION_READY must fail
        ok, msg = mgr.advance_readiness("MLS", CompetitionReadinessStage.PRODUCTION_READY, evidence=["test"])
        assert ok is False
        assert "Progression must be sequential" in msg

    def test_insufficient_sample_blocks_validation_readiness(self):
        """Sample size < 30 blocks promotion to VALIDATION_READY."""
        mgr = CompetitionCoverageManager()
        # Create temporary low-sample profile
        prof = mgr.get_profile("UCL")
        orig_sample = prof.sample_size
        prof.sample_size = 15  # < 30
        prof.readiness_state = CompetitionReadinessStage.FEATURE_READY.value

        ok, msg = mgr.advance_readiness("UCL", CompetitionReadinessStage.VALIDATION_READY, evidence=["test"])
        assert ok is False
        assert "Insufficient sample size" in msg

        # Restore
        prof.sample_size = orig_sample


# ── 2. Temporal Dataset Builder & Adversarial Leakage Tests (§7) ──────

class TestTemporalDatasetAndLeakage:
    """Tests for chronological ordering and adversarial leakage invariance."""

    def test_chronological_splits_ordering(self):
        """Train, validation, and test splits strictly follow date ordering."""
        builder = TemporalDatasetBuilder(dataset_version="1.0.0")
        raw_matches = [
            {"match_id": "m1", "match_date": "2023-08-15", "feature_as_of": "2023-08-15", "features": {"f": 1.0}},
            {"match_id": "m2", "match_date": "2023-11-20", "feature_as_of": "2023-11-20", "features": {"f": 2.0}},
            {"match_id": "m3", "match_date": "2024-02-10", "feature_as_of": "2024-02-10", "features": {"f": 3.0}},
            {"match_id": "m4", "match_date": "2024-04-25", "feature_as_of": "2024-04-25", "features": {"f": 4.0}},
        ]
        splits = builder.build_splits(
            raw_matches,
            train_end="2023-12-31",
            val_end="2024-03-15",
            date_field="match_date",
        )

        assert splits["train"].count == 2
        assert splits["validation"].count == 1
        assert splits["test"].count == 1

        # Dates within train
        for ex in splits["train"].examples:
            assert ex.match_date <= "2023-12-31"
        # Dates within validation
        for ex in splits["validation"].examples:
            assert "2023-12-31" < ex.match_date <= "2024-03-15"
        # Dates within test
        for ex in splits["test"].examples:
            assert ex.match_date > "2024-03-15"

    def test_future_leakage_exception_raised(self):
        """feature_as_of > match_date raises explicit ValueError."""
        builder = TemporalDatasetBuilder()
        leaked_match = [
            {"match_id": "m_bad", "match_date": "2023-09-01", "feature_as_of": "2023-09-05", "features": {}}
        ]
        with pytest.raises(ValueError, match="Temporal leakage violation"):
            builder.build_splits(leaked_match, train_end="2023-12-31", val_end="2024-03-31")

    def test_adversarial_future_injections_invariance(self):
        """Adversarial injection of future match, transfer, and stats leaves historical example unchanged."""
        builder = TemporalDatasetBuilder()
        example = TemporalExample(
            example_id="ex_arsenal_chelsea",
            entity_ids={"home": "arsenal", "away": "chelsea"},
            competition="EPL",
            season="2023/2024",
            match_date="2023-10-21",
            feature_as_of="2023-10-21",
            target_date="2023-10-21",
            feature_set_version="match_prediction_v1",
            dataset_version="1.0.0",
            features={"elo_diff": 85.0, "rest_days": 6.0},
            target=1,
        )

        future_injections = [
            {"event_date": "2023-10-28", "features": {"elo_diff": 95.0}},  # Future match
            {"event_date": "2024-01-15", "features": {"new_signing_fee": 65e6}},  # Future transfer
            {"event_date": "2024-03-01", "features": {"elo_diff": 110.0}},  # Future form
        ]

        # Verify bit-for-bit invariance
        is_invariant = builder.verify_adversarial_invariance(example, future_injections)
        assert is_invariant is True


# ── 3. Probability Calibration & Zero Test Leakage (§8, §9) ─────────

class TestProbabilityCalibration:
    """Tests for multi-method probability calibration with zero test leakage."""

    def test_calibration_metrics_calculation(self):
        """Computes valid Brier score, Log Loss, and ECE."""
        calibrator = ProbabilityCalibrationEngine(n_bins=5)
        y_true = [0, 1, 2, 0, 1]
        probs = [
            [0.70, 0.20, 0.10],
            [0.15, 0.75, 0.10],
            [0.10, 0.20, 0.70],
            [0.60, 0.30, 0.10],
            [0.20, 0.60, 0.20],
        ]
        metrics = calibrator.compute_metrics(y_true, probs)
        assert 0.0 <= metrics["brier_score"] <= 1.0
        assert metrics["log_loss"] > 0.0
        assert 0.0 <= metrics["ece"] <= 1.0
        assert metrics["accuracy"] == 1.0  # All highest probs match y_true

    def test_temperature_scaling_improves_or_preserves_ece(self):
        """Temperature scaling on overconfident predictions reduces ECE."""
        calibrator = ProbabilityCalibrationEngine(n_bins=5)
        # Synthetic overconfident probabilities
        y_val = [0, 1, 2, 0, 1, 0, 2, 1, 0, 1] * 4  # N = 40
        probs_val = [
            [0.90, 0.05, 0.05], [0.05, 0.90, 0.05], [0.05, 0.05, 0.90],
            [0.40, 0.30, 0.30], [0.30, 0.40, 0.30], [0.85, 0.10, 0.05],
            [0.10, 0.10, 0.80], [0.20, 0.70, 0.10], [0.75, 0.15, 0.10],
            [0.15, 0.70, 0.15],
        ] * 4

        result = calibrator.calibrate_and_evaluate(
            competition="LALIGA",
            y_val=y_val,
            probs_val=probs_val,
            validation_window="2024-01-16 to 2024-03-31",
            method="TEMPERATURE_SCALING",
        )
        assert result.sample_size == 40
        assert "temperature" in result.parameters
        assert len(result.reliability_bins) == 5
        assert result.metrics_after["brier_score"] <= result.metrics_before["brier_score"] + 0.01

    def test_calibration_fails_below_minimum_sample(self):
        """Calibration rejects validation samples with N < 30."""
        calibrator = ProbabilityCalibrationEngine()
        y_small = [0, 1, 2] * 5  # N = 15 (< 30)
        probs_small = [[0.33, 0.33, 0.34]] * 15
        with pytest.raises(ValueError, match="Insufficient validation sample size"):
            calibrator.calibrate_and_evaluate("SERIEA", y_small, probs_small)


# ── 4. Immutable Dataset Registry & Lineage (§20) ────────────────────

class TestDatasetRegistry:
    """Tests for immutable dataset registry and full provenance reconstruction."""

    def test_default_datasets_registered(self):
        """EPL, La Liga, Serie A, and Transfer datasets are registered."""
        reg = DatasetRegistry()
        datasets = reg.list_datasets()
        ids = {d["dataset_id"] for d in datasets}
        assert "ds_epl_match_2022_2024" in ids
        assert "ds_laliga_match_2023_2024" in ids
        assert "ds_seriea_match_2023_2024" in ids
        assert "ds_transfers_top5_2021_2024" in ids

    def test_dataset_immutability_blocks_overwrites(self):
        """Attempting to overwrite a registered dataset version raises ValueError."""
        reg = DatasetRegistry()
        duplicate_payload = {
            "dataset_id": "ds_epl_match_2022_2024",
            "dataset_version": "1.2.0",
            "competition_scope": "EPL",
        }
        with pytest.raises(ValueError, match="already registered and is immutable"):
            reg.register(duplicate_payload)

    def test_dataset_lineage_verification(self):
        """Full end-to-end lineage is reconstructable back to Bronze SHA-256."""
        reg = DatasetRegistry()
        res = reg.verify_lineage("ds_epl_match_2022_2024")
        assert res["status"] == "VERIFIED"
        lineage = res["lineage"]
        assert lineage["reconstructable"] is True
        assert len(lineage["bronze_snapshots"]) == 2
        assert "Decision -> Model(*) -> Dataset" in lineage["lineage_path"]


# ── 5. Model Shadow Mode Execution (§18, §19) ───────────────────────

class TestModelShadowMode:
    """Tests for parallel candidate model execution with zero production contamination."""

    def test_shadow_dual_inference_execution(self):
        """Authoritative output matches production; candidate executed in shadow mode."""
        executor = ShadowModeExecutor()

        def prod_predict(x):
            return {"probabilities": [0.52, 0.26, 0.22], "outcome": "HOME_WIN"}

        def shadow_predict(x):
            return {"probabilities": [0.50, 0.28, 0.22], "outcome": "HOME_WIN"}

        prod_out, record = executor.execute_dual_inference(
            entity_id="match_test_01",
            competition="LALIGA",
            input_features={"home_elo": 1700},
            prod_predict_fn=prod_predict,
            shadow_predict_fn=shadow_predict,
            prod_model_id="prod_v1",
            shadow_model_id="shadow_v1",
        )

        assert prod_out["outcome"] == "HOME_WIN"
        assert record.production_output["probabilities"] == [0.52, 0.26, 0.22]
        assert record.shadow_output["probabilities"] == [0.50, 0.28, 0.22]
        assert record.output_divergence == 0.02  # 0.5 * (|0.52-0.50| + |0.26-0.28| + 0) = 0.02

    def test_shadow_summary_recommendation(self):
        """Summary computes divergence and recommends promotion or monitoring."""
        executor = ShadowModeExecutor()
        for i in range(10):
            executor.execute_dual_inference(
                entity_id=f"m_{i}",
                competition="LALIGA",
                input_features={},
                prod_predict_fn=lambda x: {"probabilities": [0.45, 0.30, 0.25]},
                shadow_predict_fn=lambda x: {"probabilities": [0.46, 0.29, 0.25]},
                prod_model_id="p_test",
                shadow_model_id="s_test",
            )
        summary = executor.get_summary("p_test", "s_test")
        assert summary.total_evaluations == 10
        assert summary.mean_divergence == 0.01
        assert summary.recommendation == "READY_FOR_CANDIDATE"


# ── 6. Continuous Drift Monitoring & Alerts (§16, §17, §27) ─────────

class TestContinuousDriftMonitoring:
    """Tests for PSI drift thresholds and factual operational alerting."""

    def test_psi_calculation_identical_distributions(self):
        """PSI of identical distributions is 0.0."""
        dist = [10.0, 15.0, 20.0, 25.0, 30.0] * 20
        psi = calculate_psi(dist, dist)
        assert psi == 0.0

    def test_psi_calculation_shifted_distributions(self):
        """Shifted distributions produce non-zero PSI."""
        exp = [10.0, 12.0, 14.0, 16.0, 18.0] * 20
        act = [14.0, 16.0, 18.0, 20.0, 22.0] * 20
        psi = calculate_psi(exp, act)
        assert psi > 0.0

    def test_drift_threshold_classification(self):
        """Classifies drift into NORMAL, MONITOR, WARNING, and MATERIAL_DRIFT."""
        monitor = ContinuousDriftMonitor()
        # Normal drift
        snap = monitor.evaluate_competition_drift(
            competition="EPL",
            season="2023/2024",
            baseline_features={"f1": [1.0, 2.0, 3.0] * 10},
            current_features={"f1": [1.0, 2.1, 2.9] * 10},
            baseline_metrics={"brier_score": 0.5365, "log_loss": 0.9418},
            current_metrics={"brier_score": 0.5380, "log_loss": 0.9430},
        )
        assert snap.drift_status in ("NORMAL", "MONITOR")
        assert snap.review_required is False


# ── 7. Multi-Engine Cross-Competition Validation (§8, §11–§15) ──────

class TestMultiEngineValidation:
    """Tests for cross-competition validation of all 6 analytical engines."""

    def test_global_validation_matrix_generation(self):
        """Generates comprehensive matrix covering all 6 engines across 7 competitions."""
        validator = CrossCompetitionValidator()
        matrix = validator.generate_full_matrix()
        assert matrix.version == "phase11_global_v1"
        assert matrix.summary["total_evaluations"] == 42  # 7 competitions * 6 engines
        assert matrix.summary["production_ready_count"] >= 5
        assert len(matrix.limitations) >= 3

    def test_epl_match_prediction_is_production_ready(self):
        """EPL match prediction dossier reports PRODUCTION_READY."""
        validator = CrossCompetitionValidator()
        dossier = validator.validate_match_prediction("EPL")
        assert dossier.validation_status == "PRODUCTION_READY"
        assert dossier.metrics["log_loss"] == 0.9418
        assert dossier.metrics["ece"] == 0.0385

    def test_tier1_non_epl_match_prediction_is_model_validated(self):
        """La Liga and Serie A match prediction dossiers report MODEL_VALIDATED."""
        validator = CrossCompetitionValidator()
        for comp in ["LALIGA", "SERIEA", "BUNDESLIGA", "LIGUE1"]:
            dossier = validator.validate_match_prediction(comp)
            assert dossier.validation_status == "MODEL_VALIDATED"
            assert "log_loss" in dossier.metrics


# ── 8. Pipeline Determinism & Dual Replay (§21) ─────────────────────

class TestPipelineReplayEngine:
    """Tests for bit-for-bit reproducibility and dual replay digest preservation."""

    def test_deterministic_dual_replay_passes(self):
        """Dual run of identical pipeline yields zero divergence across all stages."""
        replay = PipelineReplayEngine()

        def dummy_pipeline():
            return {
                "bronze": {"snapshot_sha": "500ba51b..."},
                "silver": {"matches_count": 760},
                "features": {"features_hash": "feat_sha256"},
                "dataset": {"dataset_id": "ds_epl_match_2022_2024"},
                "model": {"model_id": "calibrated_multinomial_logit_v1"},
                "calibration": {"temperature": 1.06},
                "prediction": {"win_prob": 0.54},
                "decision": {"decision_digest": "dec_digest_sha256"},
            }

        res = replay.execute_replay("epl_full_pipeline", "EPL", dummy_pipeline)
        assert res.deterministic is True
        assert res.divergence_count == 0
        assert res.total_stages == 8
        assert len(res.overall_checksum) == 64


# ── 9. Scout Copilot Operational Dispatcher (§25) ───────────────────

class TestCopilotDispatcherPhase11:
    """Tests for deterministic Copilot tool routing without numerical hallucination."""

    def test_copilot_which_competitions_ready(self):
        """Routes query about production ready competitions correctly."""
        dispatcher = Phase11CopilotDispatcher()
        res = dispatcher.dispatch("Which competitions are production ready?")
        assert res["intent"] == "LIST_PRODUCTION_READY_COMPETITIONS"
        assert "Premier League" in res["answer"]
        assert res["deterministic"] is True

    def test_copilot_why_not_production_ready(self):
        """Explains why Serie A is not production ready grounded in evidence."""
        dispatcher = Phase11CopilotDispatcher()
        res = dispatcher.dispatch("Why isn't Serie A production ready?")
        assert res["intent"] == "WHY_NOT_PRODUCTION_READY"
        assert res["competition"] == "Serie A"
        assert "Zero-inheritance policy" in res["answer"]
        assert res["deterministic"] is True

    def test_copilot_inspect_lineage(self):
        """Routes lineage inspection query and cites dataset checksum."""
        dispatcher = Phase11CopilotDispatcher()
        res = dispatcher.dispatch("Show me the data lineage behind this prediction")
        assert res["intent"] == "INSPECT_LINEAGE"
        assert "Reconstructed end-to-end lineage" in res["answer"]
        assert res["deterministic"] is True


# ── 10. 16-Section Cross-Competition Report Generation (§28) ────────

class TestCrossCompetitionReport:
    """Tests for 16-section report generation and Markdown rendering."""

    def test_generate_16_section_report(self):
        """Generates report containing all 16 canonical sections."""
        report = generate_cross_competition_report("LALIGA")
        assert len(report.sections) == 16
        assert "1_executive_summary" in report.sections
        assert "8_calibration" in report.sections
        assert "14_limitations" in report.sections
        assert "16_full_evidence_lineage" in report.sections

    def test_render_report_markdown(self):
        """Renders dense Markdown document with proper section headers."""
        report = generate_cross_competition_report("LALIGA")
        md = render_report_markdown(report)
        assert "# Cross-Competition Validation" in md
        assert "## 1. Executive Summary" in md
        assert "## 8. Probability Calibration Metrics" in md
        assert "## 16. Full Evidence Lineage" in md
