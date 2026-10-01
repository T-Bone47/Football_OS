"""Unit tests for Match Prediction & Calibration Engine (Phase 6).

Validates:
- Strict probability normalization: P(Home) + P(Draw) + P(Away) == 1.0 within numerical tolerance.
- Pre-match expected goals and coherent scoreline probability distribution.
- Temporal cutoff filtering: features use ONLY past matches strictly preceding kickoff.
- Team strength Elo calculations and home advantage.
- Baseline models and calibrated multinomial model.
- Multi-class Log Loss, Brier score, and Expected Calibration Error (ECE).
- Non-causal explainability attribution.
- Data sufficiency and Out-of-Distribution gating.
- Model registry and status contracts.
"""
from datetime import datetime, timedelta, timezone
import math
import uuid
import pytest
from pydantic import ValidationError

from app.prediction.calibration import (
    classification_metrics,
    expected_calibration_error,
    goal_regression_metrics,
    multi_class_brier_score,
    multi_class_log_loss,
    TemperatureScalingCalibrator,
)
from app.prediction.elo import EloRatingEngine, elo_to_1x2_probabilities
from app.prediction.explain import MatchExplanationEngine
from app.prediction.features import PreMatchFeatureBuilder
from app.prediction.gating import PredictionGatingEngine
from app.prediction.goals import GoalPredictionEngine
from app.prediction.models import (
    BaselineClassFrequencyModel,
    BaselineEloModel,
    BaselineHomeFormModel,
    BaselinePoissonGoalModel,
    CalibratedMultinomialModel,
    determine_match_target,
    normalize_probabilities,
    target_to_index,
)
from app.prediction.registry import PredictionModelRegistry
from app.prediction.schemas import (
    ExpectedGoals,
    OutcomeProbabilities,
)
from app.prediction.service import MatchPredictionService


# ============================================================
# 1. PROBABILITY NORMALIZATION & SCHEMAS
# ============================================================
class TestProbabilityNormalization:
    """Verifies that probabilities strictly sum to 1.0 within numerical tolerance (< 1e-3)."""

    def test_exact_sum_valid(self):
        probs = OutcomeProbabilities(home_win=0.50, draw=0.25, away_win=0.25)
        total = probs.home_win + probs.draw + probs.away_win
        assert abs(total - 1.0) < 1e-5

    def test_normalization_helper_enforces_exact_sum(self):
        # Arbitrary raw unnormalized scores
        probs = normalize_probabilities(0.85, 0.45, 0.20)
        total = probs.home_win + probs.draw + probs.away_win
        assert abs(total - 1.0) < 1e-4
        assert probs.home_win > probs.draw > probs.away_win

    def test_schema_rejects_sum_deviations(self):
        with pytest.raises(ValidationError):
            OutcomeProbabilities(home_win=0.60, draw=0.30, away_win=0.30)  # sum = 1.20


# ============================================================
# 2. TARGET IDENTIFICATION & ENCODING
# ============================================================
class TestOutcomeTarget:
    """Verifies deterministic target creation from scores."""

    def test_home_win_target(self):
        assert determine_match_target(2, 1) == "HOME_WIN"
        assert target_to_index("HOME_WIN") == 0

    def test_draw_target(self):
        assert determine_match_target(1, 1) == "DRAW"
        assert target_to_index("DRAW") == 1

    def test_away_win_target(self):
        assert determine_match_target(0, 3) == "AWAY_WIN"
        assert target_to_index("AWAY_WIN") == 2

    def test_none_scores_return_none(self):
        assert determine_match_target(None, 1) is None
        assert determine_match_target(2, None) is None


# ============================================================
# 3. ELO TEAM STRENGTH ENGINE
# ============================================================
class TestEloEngine:
    """Tests the deterministic Elo rating mechanism."""

    def setup_method(self):
        self.engine = EloRatingEngine(k_factor=32.0, home_advantage=65.0)

    def test_initial_ratings_are_1500(self):
        club1 = uuid.uuid4()
        club2 = uuid.uuid4()
        h_elo, a_elo, diff = self.engine.get_match_ratings(club1, club2, [], datetime.now(timezone.utc))
        assert h_elo == 1500.0
        assert a_elo == 1500.0
        assert diff == 65.0  # includes home advantage

    def test_rating_update_after_home_win(self):
        r_home, r_away = 1500.0, 1500.0
        new_h, new_a = self.engine.update_ratings(r_home, r_away, home_score=2, away_score=0)
        assert new_h > 1500.0
        assert new_a < 1500.0
        assert round(new_h + new_a, 2) == 3000.0  # Zero-sum exchange

    def test_elo_to_1x2_probabilities_sum_to_one(self):
        h, d, a = elo_to_1x2_probabilities(1600.0, 1450.0)
        assert abs((h + d + a) - 1.0) < 1e-4
        assert h > a  # Higher rated home team should have higher win probability


# ============================================================
# 4. PRE-MATCH EXPECTED GOALS & SCORELINE DISTRIBUTION
# ============================================================
class TestGoalPredictionEngine:
    """Verifies bivariate Poisson and Dixon-Coles goal model."""

    def setup_method(self):
        self.engine = GoalPredictionEngine()

    def test_compute_expected_goals(self):
        xg = self.engine.compute_expected_goals(
            home_attack_strength=1.20,
            home_defense_strength=0.90,
            away_attack_strength=1.00,
            away_defense_strength=1.10,
        )
        assert isinstance(xg, ExpectedGoals)
        assert xg.home > 0.0
        assert xg.away > 0.0
        assert round(xg.home + xg.away, 2) == round(xg.total, 2)

    def test_scoreline_distribution_integrity(self):
        xg = ExpectedGoals(home=1.65, away=1.15, total=2.80)
        dist = self.engine.generate_scoreline_distribution(xg, top_k=6)

        assert len(dist.top_scorelines) > 0
        # Probabilities bounded between 0 and 1
        assert 0.0 <= dist.over_2_5 <= 1.0
        assert 0.0 <= dist.under_2_5 <= 1.0
        assert abs((dist.over_2_5 + dist.under_2_5) - 1.0) < 0.05
        assert 0.0 <= dist.both_teams_to_score <= 1.0

    def test_scorelines_to_1x2_probabilities(self):
        xg = ExpectedGoals(home=1.80, away=0.90, total=2.70)
        dist = self.engine.generate_scoreline_distribution(xg)
        h, d, a = self.engine.scorelines_to_1x2(dist)
        assert abs((h + d + a) - 1.0) < 1e-4
        assert h > a  # Home expected goals higher -> higher home win probability


# ============================================================
# 5. PRE-MATCH FEATURE BUILDER & TEMPORAL FILTERING
# ============================================================
class TestPreMatchFeatureBuilder:
    """Ensures features use ONLY historical matches strictly before cutoff."""

    def test_strict_temporal_filtering(self):
        builder = PreMatchFeatureBuilder()
        home_id = uuid.uuid4()
        away_id = uuid.uuid4()
        match_id = uuid.uuid4()

        t0 = datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)
        t_match = datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc)
        t_future = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)

        matches = [
            # Past match for home team (should be included)
            {
                "id": uuid.uuid4(),
                "home_club_id": home_id,
                "away_club_id": uuid.uuid4(),
                "home_score": 2,
                "away_score": 1,
                "date": t0,
                "status": "FT",
            },
            # Current match itself (must be excluded even if date <= kickoff)
            {
                "id": match_id,
                "home_club_id": home_id,
                "away_club_id": away_id,
                "home_score": 3,
                "away_score": 0,
                "date": t_match,
                "status": "FT",
            },
            # Future match (must be excluded)
            {
                "id": uuid.uuid4(),
                "home_club_id": home_id,
                "away_club_id": uuid.uuid4(),
                "home_score": 5,
                "away_score": 0,
                "date": t_future,
                "status": "FT",
            },
        ]

        snapshot = builder.build_features(
            match_id=match_id,
            home_club_id=home_id,
            away_club_id=away_id,
            kickoff_time=t_match,
            historical_matches=matches,
        )

        assert snapshot.home_sample_size == 1
        assert snapshot.away_sample_size == 0
        assert snapshot.features["home_points_l5"] == 3.0  # Only the 2-1 win at t0


# ============================================================
# 6. BASELINES & ML MODELS
# ============================================================
class TestModels:
    """Tests all baseline and ML models return strictly normalized probabilities."""

    def setup_method(self):
        self.sample_features = {
            "elo_diff": 120.0,
            "home_elo": 1580.0,
            "away_elo": 1460.0,
            "points_diff_l5": 0.8,
            "home_attack_strength": 1.25,
            "away_defense_strength": 1.10,
            "away_attack_strength": 0.95,
            "home_defense_strength": 0.85,
            "rest_days_diff": 2.0,
        }

    def test_baseline_1_class_frequency(self):
        model = BaselineClassFrequencyModel()
        p = model.predict(self.sample_features)
        assert abs((p.home_win + p.draw + p.away_win) - 1.0) < 1e-4
        assert p.home_win > p.away_win

    def test_baseline_2_home_form(self):
        model = BaselineHomeFormModel()
        p = model.predict(self.sample_features)
        assert abs((p.home_win + p.draw + p.away_win) - 1.0) < 1e-4

    def test_baseline_3_elo(self):
        model = BaselineEloModel()
        p = model.predict(self.sample_features)
        assert abs((p.home_win + p.draw + p.away_win) - 1.0) < 1e-4
        assert p.home_win > p.away_win

    def test_baseline_4_poisson(self):
        model = BaselinePoissonGoalModel()
        p = model.predict(self.sample_features)
        assert abs((p.home_win + p.draw + p.away_win) - 1.0) < 1e-4

    def test_calibrated_multinomial_model(self):
        model = CalibratedMultinomialModel(temperature=1.06)
        p = model.predict(self.sample_features)
        assert abs((p.home_win + p.draw + p.away_win) - 1.0) < 1e-4
        assert p.home_win > p.draw
        assert p.home_win > p.away_win


# ============================================================
# 7. CALIBRATION & EVALUATION METRICS
# ============================================================
class TestCalibrationMetrics:
    """Verifies Brier score, Log Loss, and ECE."""

    def test_multi_class_brier_score(self):
        # Perfect predictions -> 0.0
        y_true = [0, 1, 2]
        y_prob_perfect = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        assert multi_class_brier_score(y_true, y_prob_perfect) == 0.0

        # Uniform predictions -> (0.333-1)^2 + 2*(0.333-0)^2 = 0.444 + 0.222 = 0.667
        y_prob_uniform = [[0.333, 0.333, 0.334] for _ in range(3)]
        brier = multi_class_brier_score(y_true, y_prob_uniform)
        assert 0.60 < brier < 0.70

    def test_multi_class_log_loss(self):
        y_true = [0, 1]
        y_prob_confident = [[0.90, 0.05, 0.05], [0.10, 0.85, 0.05]]
        loss = multi_class_log_loss(y_true, y_prob_confident)
        assert loss < 0.25

    def test_expected_calibration_error(self):
        y_true = [0, 1, 2, 0, 1]
        y_prob = [
            [0.8, 0.1, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
            [0.8, 0.1, 0.1],
            [0.1, 0.8, 0.1],
        ]
        ece = expected_calibration_error(y_true, y_prob, n_bins=5)
        assert 0.0 <= ece <= 1.0

    def test_temperature_scaling_calibrator_fitting(self):
        calibrator = TemperatureScalingCalibrator()
        val_logits = [
            [2.5, 0.5, -0.5],
            [0.2, 2.0, -0.2],
            [-0.5, 0.1, 2.2],
            [1.8, 0.2, -0.2],
        ]
        y_val = [0, 1, 2, 0]
        optimal_t = calibrator.fit(val_logits, y_val)
        assert 0.5 <= optimal_t <= 2.5


# ============================================================
# 8. EXPLAINABILITY & NON-CAUSAL ATTRIBUTION
# ============================================================
class TestExplainability:
    """Verifies that explanations are non-causal and grounded in real features."""

    def test_explanation_uses_non_causal_language(self):
        engine = MatchExplanationEngine()
        features = {
            "elo_diff": 150.0,
            "home_elo": 1620.0,
            "away_elo": 1470.0,
            "points_diff_l5": 1.2,
            "home_attack_strength": 1.35,
            "away_defense_strength": 1.20,
            "away_attack_strength": 0.90,
            "home_defense_strength": 0.80,
            "rest_days_diff": 3.0,
            "h2h_home_wins": 2,
            "h2h_away_wins": 0,
            "h2h_draws": 1,
        }

        explanation = engine.explain("Arsenal", "Chelsea", features, 0.62, 0.22, 0.16)

        assert "contributing" in explanation.summary.lower() or "contributed" in explanation.summary.lower()
        # Strictly forbid causal claims
        assert "caused" not in explanation.summary.lower()
        assert len(explanation.key_factors) > 0
        assert any(f.direction == "FAVORS_HOME" for f in explanation.key_factors)


# ============================================================
# 9. DATA SUFFICIENCY & OOD GATING
# ============================================================
class TestGatingEngine:
    """Verifies status transitions for sparse or shifted match data."""

    def setup_method(self):
        self.gating = PredictionGatingEngine()

    def test_insufficient_data_when_zero_matches(self):
        res = self.gating.evaluate(features={}, home_sample_size=0, away_sample_size=0)
        assert res.status == "INSUFFICIENT_DATA"
        assert res.confidence_multiplier == 0.0

    def test_low_confidence_when_sparse_matches(self):
        res = self.gating.evaluate(features={"elo_diff": 50.0}, home_sample_size=1, away_sample_size=2)
        assert res.status == "LOW_CONFIDENCE"
        assert res.confidence_multiplier < 1.0

    def test_out_of_distribution_on_extreme_elo(self):
        res = self.gating.evaluate(features={"elo_diff": 620.0}, home_sample_size=10, away_sample_size=10)
        assert res.status == "OUT_OF_DISTRIBUTION"
        assert res.is_ood is True

    def test_prediction_available_on_sufficient_data(self):
        res = self.gating.evaluate(features={"elo_diff": 80.0}, home_sample_size=8, away_sample_size=7)
        assert res.status == "PREDICTION_AVAILABLE"
        assert res.confidence_multiplier == 1.0


# ============================================================
# 10. MODEL REGISTRY
# ============================================================
class TestModelRegistry:
    """Verifies registry contracts and active model retrieval."""

    def test_active_model_registered_and_validated(self):
        registry = PredictionModelRegistry()
        active = registry.get_active_model()
        assert active.status == "MODEL_VALIDATED"
        assert active.temporal_validation_passed is True
        assert active.leakage_tests_passed is True

        resp = registry.get_status_response()
        assert resp.active_model_id == active.model_id
        assert resp.status == "MODEL_VALIDATED"
