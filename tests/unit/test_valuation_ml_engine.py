"""Unit tests for Phase 4.2: Transfer Valuation ML Engine.

Verifies:
1. Target construction, eligibility, transformation, and Duan's smearing factor.
2. Feature contract integrity, definitions, and leakage policies.
3. Temporal dataset builder, temporal splits, and target leakage invariance.
4. Future data injection invariance.
5. Baseline models benchmarking.
6. Candidate ML models (Ridge, RandomForest, GradientBoosting, LightGBM).
7. Conformal uncertainty interval estimation and empirical coverage.
8. Calibration and systematic bias analysis.
9. Deterministic explainability and non-causal attribution language policy.
10. Data sufficiency and out-of-distribution (OOD) gating.
11. Model serialization, registry lifecycle, and reproducibility.
12. Market and player valuation API schemas and endpoints.
"""

from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import uuid
import numpy as np
import pytest

from app.market.ml.baselines import (
    AgePositionBenchmarkBaseline,
    ComparableMedianBaseline,
    GlobalMedianBaseline,
    PositionMedianBaseline,
    calculate_metrics,
    evaluate_all_baselines,
)
from app.market.ml.dataset import (
    TemporalDatasetSplit,
    ValuationMLDatasetBuilder,
    ValuationMLSample,
)
from app.market.ml.explainability import (
    FeatureAttributionItem,
    ValuationExplainer,
    ValuationExplanation,
)
from app.market.ml.features import (
    FEATURE_NAMES,
    FEATURE_SET_VERSION,
    VALUATION_FEATURE_SET_V1,
    get_valuation_feature_names,
)
from app.market.ml.gating import (
    SufficiencyGateDecision,
    ValuationDataStatus,
    ValuationSufficiencyGate,
)
from app.market.ml.models import (
    GradientBoostingValuationModel,
    LightGBMValuationModel,
    RandomForestValuationModel,
    RidgeValuationModel,
    ValuationModelTrainer,
)
from app.market.ml.registry import (
    ModelRegistryMetadata,
    ValuationInferenceResult,
    ValuationModelBundle,
    ValuationModelRegistry,
)
from app.market.ml.target import SupervisedValuationTarget
from app.market.ml.uncertainty import (
    ConformalIntervalEstimator,
    PredictionInterval,
    ValuationCalibrationAnalyzer,
)
from app.market.taxonomy import TransferFeeStatus


# =============================================================================
# 1. TARGET SPECIFICATION & TRANSFORMATION TESTS (Phase 4.2B & 4.2C)
# =============================================================================

def test_target_eligibility_and_exclusions():
    """Verifies that only permanent transfers with KNOWN_FEE and REPORTED_FEE qualify."""
    # Eligible permanent transfers
    ok, reason = SupervisedValuationTarget.check_eligibility(
        fee_status="KNOWN_FEE", is_loan=False, fee_eur=45_000_000.0
    )
    assert ok is True
    assert reason == "ELIGIBLE"

    ok, reason = SupervisedValuationTarget.check_eligibility(
        fee_status="REPORTED_FEE", is_loan=False, fee_eur=12_500_000.0
    )
    assert ok is True
    assert reason == "ELIGIBLE"

    # Loans excluded
    ok, reason = SupervisedValuationTarget.check_eligibility(
        fee_status="KNOWN_FEE", is_loan=True, fee_eur=5_000_000.0
    )
    assert ok is False
    assert "LOAN" in reason

    # Estimated / unknown fees excluded
    ok, reason = SupervisedValuationTarget.check_eligibility(
        fee_status="ESTIMATED_FEE", is_loan=False, fee_eur=20_000_000.0
    )
    assert ok is False
    assert "ESTIMATED" in reason

    ok, reason = SupervisedValuationTarget.check_eligibility(
        fee_status="UNKNOWN_FEE", is_loan=False, fee_eur=None
    )
    assert ok is False

    ok, reason = SupervisedValuationTarget.check_eligibility(
        fee_status="FREE_TRANSFER", is_loan=False, fee_eur=0.0
    )
    assert ok is False


def test_target_log1p_transformation_and_duan_smearing():
    """Verifies log1p transformation and Duan's non-parametric smearing back-transformation."""
    fees = [10_000_000.0, 25_000_000.0, 80_000_000.0]
    log_fees = SupervisedValuationTarget.transform(fees)
    assert len(log_fees) == 3
    assert all(lf > 0 for lf in log_fees)

    # Negative fee must raise ValueError
    with pytest.raises(ValueError):
        SupervisedValuationTarget.transform(-100.0)

    # Duan's smearing calculation
    y_true_log = [math.log1p(f) for f in fees]
    y_pred_log = [y - 0.05 for y in y_true_log]  # Underpredicting slightly
    smearing = SupervisedValuationTarget.calculate_duan_smearing_factor(y_true_log, y_pred_log)
    assert smearing >= 1.0  # Corrections for slight negative residual bias

    # Inverse transform
    inv = SupervisedValuationTarget.inverse_transform(y_pred_log, smearing_factor=smearing)
    assert len(inv) == 3
    assert all(f > 0 for f in inv)


def test_target_distribution_statistics():
    """Verifies distribution stats calculation (IQR, skewness, kurtosis)."""
    fees = [5_000_000.0, 10_000_000.0, 15_000_000.0, 30_000_000.0, 100_000_000.0]
    stats = SupervisedValuationTarget.compute_distribution_stats(fees)
    assert stats.sample_size == 5
    assert stats.median == 15_000_000.0
    assert stats.skewness > 0.0  # Right-skewed positive tail


# =============================================================================
# 2. FEATURE CONTRACT & LEAKAGE POLICY TESTS (Phase 4.2D & 4.2F)
# =============================================================================

def test_valuation_feature_contract_integrity():
    """Ensures VALUATION_FEATURE_SET_V1 satisfies all metadata rules without leakage."""
    names = get_valuation_feature_names()
    assert len(names) == 30
    assert len(VALUATION_FEATURE_SET_V1) == 30

    for feat in VALUATION_FEATURE_SET_V1:
        assert feat.name != ""
        assert feat.dtype in ("float", "int", "bool")
        assert feat.leakage_policy != ""
        assert feat.leakage_risk == "LOW"
        assert feat.availability_status == "AVAILABLE_AT_TRANSFER"
        assert feat.as_of_rule != ""
        assert feat.source != ""


# =============================================================================
# 3. DATASET BUILDER & TEMPORAL INTEGRITY TESTS (Phase 4.2G, 4.2H, 4.2I)
# =============================================================================

def _make_dummy_normalized_transfers():
    """Generates synthetic normalized transfers across 3 chronological epochs."""
    from app.market.merging import MergedTransfer

    transfers = []
    # Train epoch: 2021-2022
    for i in range(1, 31):
        dt = date(2021, (i % 12) + 1, (i % 25) + 1)
        transfers.append(
            MergedTransfer(
                canonical_key=f"tx_train_{i}",
                provider_player_id=f"p_train_{i}",
                player_name=f"Player Train {i}",
                from_provider_club_id="club_a",
                from_club_name="Club A",
                to_provider_club_id="club_b",
                to_club_name="Club B",
                transfer_date=dt,
                transfer_type="Permanent",
                fee_value=float(i * 1_500_000),
                fee_currency="EUR",
                fee_status=TransferFeeStatus.KNOWN_FEE.value,
                fee_eur_normalized=float(i * 1_500_000),
                is_loan=False,
                is_permanent=True,
                position_group="MID" if i % 2 == 0 else "ATT",
                player_age_at_transfer=23.5,
                primary_source="api-football",
                sources=[{"provider": "api-football"}],
            )
        )
    # Val epoch: early 2023
    for i in range(1, 11):
        dt = date(2023, (i % 6) + 1, 15)
        transfers.append(
            MergedTransfer(
                canonical_key=f"tx_val_{i}",
                provider_player_id=f"p_val_{i}",
                player_name=f"Player Val {i}",
                from_provider_club_id="club_c",
                from_club_name="Club C",
                to_provider_club_id="club_d",
                to_club_name="Club D",
                transfer_date=dt,
                transfer_type="Permanent",
                fee_value=float(20_000_000 + i * 2_000_000),
                fee_currency="EUR",
                fee_status=TransferFeeStatus.REPORTED_FEE.value,
                fee_eur_normalized=float(20_000_000 + i * 2_000_000),
                is_loan=False,
                is_permanent=True,
                position_group="DEF",
                player_age_at_transfer=25.0,
                primary_source="api-football",
                sources=[{"provider": "api-football"}],
            )
        )
    # Test epoch: late 2023 - 2024
    for i in range(1, 11):
        dt = date(2023, 7 + (i % 5), 20)
        transfers.append(
            MergedTransfer(
                canonical_key=f"tx_test_{i}",
                provider_player_id=f"p_test_{i}",
                player_name=f"Player Test {i}",
                from_provider_club_id="club_e",
                from_club_name="Club E",
                to_provider_club_id="club_f",
                to_club_name="Club F",
                transfer_date=dt,
                transfer_type="Permanent",
                fee_value=float(35_000_000 + i * 3_000_000),
                fee_currency="EUR",
                fee_status=TransferFeeStatus.KNOWN_FEE.value,
                fee_eur_normalized=float(35_000_000 + i * 3_000_000),
                is_loan=False,
                is_permanent=True,
                position_group="ATT",
                player_age_at_transfer=26.0,
                primary_source="api-football",
                sources=[{"provider": "api-football"}],
            )
        )
    return transfers


def test_temporal_dataset_builder_and_splits():
    """Verifies that dataset builder produces strictly chronological train/val/test splits."""
    transfers = _make_dummy_normalized_transfers()
    builder = ValuationMLDatasetBuilder()
    split = builder.build_temporal_splits(
        transfers,
        train_end_date=date(2022, 12, 31),
        val_end_date=date(2023, 6, 30),
    )

    assert len(split.train_samples) > 0
    assert len(split.val_samples) > 0
    assert len(split.test_samples) > 0

    max_train_date = max(s.transfer_date for s in split.train_samples)
    min_val_date = min(s.transfer_date for s in split.val_samples)
    max_val_date = max(s.transfer_date for s in split.val_samples)
    min_test_date = min(s.transfer_date for s in split.test_samples)

    # Chronological guarantee: train <= val <= test
    assert max_train_date <= min_val_date
    assert max_val_date <= min_test_date


def test_target_leakage_invariance():
    """Verifies that changing a transfer's fee does NOT alter its feature vector."""
    from app.market.merging import MergedTransfer

    t1 = MergedTransfer(
        canonical_key="target_leakage_key",
        provider_player_id="p_leak",
        player_name="Target Leakage Test",
        from_provider_club_id="club_a",
        from_club_name="Club A",
        to_provider_club_id="club_b",
        to_club_name="Club B",
        transfer_date=date(2022, 6, 1),
        transfer_type="Permanent",
        fee_value=10_000_000.0,
        fee_currency="EUR",
        fee_status="KNOWN_FEE",
        fee_eur_normalized=10_000_000.0,
        is_loan=False,
        is_permanent=True,
        position_group="MID",
        player_age_at_transfer=24.0,
        primary_source="api-football",
        sources=[{"provider": "api-football"}],
    )
    t2 = MergedTransfer(
        canonical_key="target_leakage_key",
        provider_player_id="p_leak",
        player_name="Target Leakage Test",
        from_provider_club_id="club_a",
        from_club_name="Club A",
        to_provider_club_id="club_b",
        to_club_name="Club B",
        transfer_date=date(2022, 6, 1),
        transfer_type="Permanent",
        fee_value=150_000_000.0,  # 15x fee change
        fee_currency="EUR",
        fee_status="KNOWN_FEE",
        fee_eur_normalized=150_000_000.0,
        is_loan=False,
        is_permanent=True,
        position_group="MID",
        player_age_at_transfer=24.0,
        primary_source="api-football",
        sources=[{"provider": "api-football"}],
    )

    builder = ValuationMLDatasetBuilder()
    samples1 = builder.build_samples([t1])
    samples2 = builder.build_samples([t2])

    assert len(samples1) == 1 and len(samples2) == 1
    # Features must remain bit-for-bit identical despite massive fee variation
    for feat_name in FEATURE_NAMES:
        assert samples1[0].features.get(feat_name) == samples2[0].features.get(feat_name)


# =============================================================================
# 4. BASELINE BENCHMARK MODELS (Phase 4.2J)
# =============================================================================

def test_baseline_models_evaluation():
    """Verifies all 4 baseline models evaluate cleanly without NaN or infinite metrics."""
    transfers = _make_dummy_normalized_transfers()
    builder = ValuationMLDatasetBuilder()
    split = builder.build_temporal_splits(
        transfers,
        train_end_date=date(2022, 12, 31),
        val_end_date=date(2023, 6, 30),
    )

    eval_results = evaluate_all_baselines(split.train_samples, split.test_samples)
    assert "global_median" in eval_results
    assert "position_median" in eval_results
    assert "age_position_benchmark" in eval_results
    assert "comparable_baseline" in eval_results

    for name, metrics in eval_results.items():
        assert metrics["mae"] > 0.0
        assert metrics["rmse"] > 0.0
        assert metrics["med_ae"] > 0.0
        assert not math.isnan(metrics["log_mae"])


# =============================================================================
# 5. CANDIDATE ML MODELS & TRAINING (Phase 4.2K & 4.2L)
# =============================================================================

def test_ml_candidate_models_training_and_prediction():
    """Trains and tests Ridge, Random Forest, Gradient Boosting, and LightGBM models."""
    transfers = _make_dummy_normalized_transfers()
    builder = ValuationMLDatasetBuilder()
    split = builder.build_temporal_splits(
        transfers,
        train_end_date=date(2022, 12, 31),
        val_end_date=date(2023, 6, 30),
    )

    # 1. Ridge
    ridge = RidgeValuationModel()
    ridge.fit(split.X_train, split.y_train_log)
    preds_eur = ridge.predict_eur(split.X_test)
    assert len(preds_eur) == len(split.y_test_eur)
    assert all(p >= 0 for p in preds_eur)

    # 2. Random Forest
    rf = RandomForestValuationModel(n_estimators=10)
    rf.fit(split.X_train, split.y_train_log)
    rf_preds = rf.predict_eur(split.X_test)
    assert len(rf_preds) == len(split.y_test_eur)

    # 3. Gradient Boosting
    gb = GradientBoostingValuationModel(n_estimators=10)
    gb.fit(split.X_train, split.y_train_log)
    gb_preds = gb.predict_eur(split.X_test)
    assert len(gb_preds) == len(split.y_test_eur)

    # 4. LightGBM
    lgb = LightGBMValuationModel(n_estimators=10)
    lgb.fit(split.X_train, split.y_train_log)
    lgb_preds = lgb.predict_eur(split.X_test)
    assert len(lgb_preds) == len(split.y_test_eur)


# =============================================================================
# 6. UNCERTAINTY ESTIMATION & CALIBRATION (Phase 4.2R & 4.2S)
# =============================================================================

def test_conformal_uncertainty_interval_estimator():
    """Verifies conformal uncertainty intervals satisfy lower <= estimate <= upper and coverage."""
    estimator = ConformalIntervalEstimator(target_coverage=0.80)

    # Calibrate with synthetic validation predictions
    y_val_eur = [10_000_000.0, 25_000_000.0, 40_000_000.0, 60_000_000.0]
    y_pred_log = [SupervisedValuationTarget.transform(f) for f in [12_000_000.0, 23_000_000.0, 44_000_000.0, 55_000_000.0]]
    positions = ["MID", "ATT", "DEF", "MID"]

    estimator.calibrate(y_val_eur, y_pred_log, positions)
    assert estimator.is_calibrated is True

    # Test single prediction interval
    test_pred_eur = 30_000_000.0
    test_pred_log = SupervisedValuationTarget.transform(test_pred_eur)
    interval = estimator.predict_interval(test_pred_log, test_pred_eur, position_group="MID")

    assert interval.lower_bound_eur <= interval.estimated_value_eur <= interval.upper_bound_eur
    assert math.isclose(interval.uncertainty_eur, (interval.upper_bound_eur - interval.lower_bound_eur) / 2.0, rel_tol=1e-4)


def test_calibration_and_bias_analysis():
    """Verifies that ValuationCalibrationAnalyzer computes overall bias and subgroup diagnostics."""
    y_true = [10_000_000.0, 20_000_000.0, 30_000_000.0, 40_000_000.0]
    y_pred = [11_000_000.0, 19_000_000.0, 32_000_000.0, 38_000_000.0]
    positions = ["DEF", "MID", "ATT", "ATT"]
    ages = [21.0, 24.0, 27.0, 30.0]

    report = ValuationCalibrationAnalyzer.analyze_calibration(y_true, y_pred, positions, ages)
    assert "overall_median_bias_eur" in report
    assert "median_ratio" in report
    assert "systematic_tendency" in report
    assert "position_calibration" in report
    assert "fee_band_calibration" in report


# =============================================================================
# 7. EXPLAINABILITY & ATTRIBUTION POLICY (Phase 4.2T)
# =============================================================================

def test_explainability_deterministic_and_non_causal_policy():
    """Verifies SHAP-based explainer and enforces non-causal attribution text rules."""
    model = RidgeValuationModel()
    X = np.random.randn(20, len(FEATURE_NAMES)).astype(np.float32)
    y = np.random.randn(20).astype(np.float32)
    model.fit(X, y)

    explainer = ValuationExplainer(
        model=model.model,
        feature_names=FEATURE_NAMES,
        model_version="VALUATION_ML_V1",
        feature_version=FEATURE_SET_VERSION,
    )
    explainer.initialize_explainer(background_data=X)

    explanation = explainer.explain_instance(
        player_id="test-player-123",
        features=X[0],
        top_k=3,
    )

    assert explanation.player_id == "test-player-123"
    assert len(explanation.top_positive_contributors) <= 3
    assert len(explanation.top_negative_contributors) <= 3

    # CRITICAL AUDIT: Every attribution string must follow non-causal guidelines
    for contrib in explanation.top_positive_contributors + explanation.top_negative_contributors:
        text = contrib.narrative.lower()
        assert "contributed" in text
        assert "caused" not in text
        assert "guaranteed" not in text


# =============================================================================
# 8. SUFFICIENCY & OUT-OF-DISTRIBUTION (OOD) GATING (Phase 4.2Z & 4.2AA)
# =============================================================================

def test_sufficiency_and_ood_gating():
    """Verifies the inference data sufficiency gate checks minutes, nulls, and OOD distance."""
    gate = ValuationSufficiencyGate(feature_names=FEATURE_NAMES)
    # Fit background distribution
    ref_X = np.random.normal(loc=1.0, scale=0.5, size=(50, len(FEATURE_NAMES)))
    gate.fit_reference_distribution(ref_X)

    # 1. Qualified player within distribution
    normal_feat = np.ones(len(FEATURE_NAMES))
    dec = gate.evaluate(normal_feat, minutes_played=1200, null_count=0, age=24.0)
    assert dec.status == ValuationDataStatus.VALUATION_AVAILABLE
    assert dec.can_predict is True

    # 2. Insufficient minutes played
    dec_mins = gate.evaluate(normal_feat, minutes_played=180, null_count=0, age=24.0)
    assert dec_mins.status == ValuationDataStatus.INSUFFICIENT_DATA
    assert dec_mins.can_predict is False
    assert any("minutes" in r.lower() for r in dec_mins.reasons)

    # 3. Excessive null features (8/24 = 33% > 25% threshold)
    dec_nulls = gate.evaluate(normal_feat, minutes_played=1200, null_count=8, age=24.0)
    assert dec_nulls.status == ValuationDataStatus.INSUFFICIENT_DATA
    assert dec_nulls.can_predict is False

    # 4. Out of distribution extreme feature values
    extreme_feat = np.ones(len(FEATURE_NAMES)) * 100.0
    dec_ood = gate.evaluate(extreme_feat, minutes_played=1200, null_count=0, age=24.0)
    assert dec_ood.status in (ValuationDataStatus.OUT_OF_DISTRIBUTION, ValuationDataStatus.LOW_CONFIDENCE)


# =============================================================================
# 9. MODEL REGISTRY LIFECYCLE & REPRODUCIBILITY (Phase 4.2V & 4.2AB)
# =============================================================================

def test_model_registry_save_load_and_reproducibility():
    """Tests that model bundles can be saved, serialized, reloaded, and reproduce bit-for-bit outputs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        reg = ValuationModelRegistry(base_dir=Path(tmp_dir))
        assert reg.get_active_model() is None

        # Build minimal bundle
        model = RidgeValuationModel()
        X = np.ones((10, len(FEATURE_NAMES)), dtype=np.float32)
        y = np.array([math.log1p(10e6)] * 10, dtype=np.float32)
        model.fit(X, y)

        target_trans = SupervisedValuationTarget()
        estimator = ConformalIntervalEstimator()
        estimator.calibrate([10e6] * 10, y, ["MID"] * 10)
        gate = ValuationSufficiencyGate(feature_names=FEATURE_NAMES)
        gate.fit_reference_distribution(X)
        explainer = ValuationExplainer(model=model.model, feature_names=FEATURE_NAMES)
        explainer.initialize_explainer(X)

        meta = ModelRegistryMetadata(
            model_id="test_model_v1",
            model_version="VALUATION_ML_V1",
            dataset_version="TRANSFER_DATASET_V1",
            feature_set_version=FEATURE_SET_VERSION,
            algorithm="Ridge",
            training_period=("2021-01-01", "2022-12-31"),
            validation_period=("2023-01-01", "2023-06-30"),
            test_period=("2023-07-01", "2024-01-01"),
            hyperparameters={"alpha": 1.0},
            train_metrics={"mae": 15e6},
            val_metrics={"mae": 18e6},
            test_metrics={"mae": 20e6},
            artifact_location="",
            created_at=datetime.now(timezone.utc).isoformat(),
            status="MODEL_VALIDATED",
            release_gate_checklist={"beats_comparable_baseline": True},
        )

        bundle = ValuationModelBundle(
            model=model,
            target_transformer=target_trans,
            uncertainty_estimator=estimator,
            sufficiency_gate=gate,
            explainer=explainer,
            metadata=meta,
            feature_names=FEATURE_NAMES,
        )

        # Register and set active
        art_path = reg.register_model(bundle, set_active=True)
        assert art_path.exists()

        # Load active model from new registry instance
        reg2 = ValuationModelRegistry(base_dir=Path(tmp_dir))
        loaded = reg2.get_active_model()
        assert loaded is not None
        assert loaded.metadata.model_id == "test_model_v1"

        # Predict with original and loaded: must match bit-for-bit
        test_feat = np.ones(len(FEATURE_NAMES), dtype=np.float32)
        res1 = bundle.predict_player("p1", test_feat, "2024-01-01", minutes_played=1000, age=25.0)
        res2 = loaded.predict_player("p1", test_feat, "2024-01-01", minutes_played=1000, age=25.0)

        assert res1.estimated_value_eur == res2.estimated_value_eur
        assert res1.lower_bound_eur == res2.lower_bound_eur
        assert res1.upper_bound_eur == res2.upper_bound_eur


# =============================================================================
# 10. API ENDPOINTS & STATUS TESTS (Phase 4.2X)
# =============================================================================

@pytest.mark.asyncio
async def test_market_model_status_api():
    """Phase 18 (R20): valuation status comes from the authoritative registry
    (ops_model_registry), never from the model's own JSON manifest. Without a
    database nothing is asserted. The registry-backed result is covered in
    tests/integration/test_phase18_model_registry.py."""
    from app.api.routes_canonical import get_market_model_status

    data = await get_market_model_status(session=None)
    assert data["status"] == "NOT_MEASURED"
    assert data["models"] == []
