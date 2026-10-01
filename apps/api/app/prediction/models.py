"""Outcome Targets, Baseline Predictors, and ML Match Models (Phase 6.6, 6.7, 6.8, 6.9).

Target Encoding:
- 0: HOME_WIN
- 1: DRAW
- 2: AWAY_WIN

Models:
- Baseline 1: Historical Class Frequency
- Baseline 2: Home Advantage + Recent Form
- Baseline 3: Deterministic Elo Rating Model
- Baseline 4: Bivariate Poisson Goal Model
- Active ML Model: Calibrated Multinomial Logit Ensemble with Temperature Scaling
"""
from __future__ import annotations

import math
from typing import Any
from app.prediction.elo import elo_to_1x2_probabilities
from app.prediction.goals import GoalPredictionEngine
from app.prediction.schemas import OutcomeProbabilities

# Historical global league frequencies (baseline prior)
CLASS_PRIOR_HOME = 0.442
CLASS_PRIOR_DRAW = 0.260
CLASS_PRIOR_AWAY = 0.298


def determine_match_target(home_score: int | None, away_score: int | None) -> str | None:
    """Deterministically identifies the canonical outcome target from score."""
    if home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return "HOME_WIN"
    if away_score > home_score:
        return "AWAY_WIN"
    return "DRAW"


def target_to_index(target: str) -> int:
    """Maps outcome string to class index: 0=HOME_WIN, 1=DRAW, 2=AWAY_WIN."""
    if target == "HOME_WIN":
        return 0
    if target == "DRAW":
        return 1
    if target == "AWAY_WIN":
        return 2
    raise ValueError(f"Unknown target: {target}")


def normalize_probabilities(h: float, d: float, a: float) -> OutcomeProbabilities:
    """Clamps and strictly normalizes probabilities so that h + d + a == 1.0."""
    h_c = max(0.01, h)
    d_c = max(0.01, d)
    a_c = max(0.01, a)
    tot = h_c + d_c + a_c

    h_norm = round(h_c / tot, 4)
    d_norm = round(d_c / tot, 4)
    # Ensure exact sum to 1.0 by assigning residue to away
    a_norm = round(1.0 - h_norm - d_norm, 4)

    return OutcomeProbabilities(home_win=h_norm, draw=d_norm, away_win=a_norm)


class BaselineClassFrequencyModel:
    """Baseline 1: Static empirical league frequency."""

    def predict(self, features: dict[str, Any]) -> OutcomeProbabilities:
        return normalize_probabilities(CLASS_PRIOR_HOME, CLASS_PRIOR_DRAW, CLASS_PRIOR_AWAY)


class BaselineHomeFormModel:
    """Baseline 2: Home advantage adjusted by recent rolling points rate."""

    def predict(self, features: dict[str, Any]) -> OutcomeProbabilities:
        p_diff = features.get("points_diff_l5") or 0.0
        # Positive point diff shifts probability from away to home
        shift = max(-0.25, min(0.25, p_diff * 0.08))
        h = CLASS_PRIOR_HOME + shift
        a = CLASS_PRIOR_AWAY - shift
        d = CLASS_PRIOR_DRAW
        return normalize_probabilities(h, d, a)


class BaselineEloModel:
    """Baseline 3: Pure Elo-based logistic outcome model."""

    def predict(self, features: dict[str, Any]) -> OutcomeProbabilities:
        h_elo = features.get("home_elo") or 1500.0
        a_elo = features.get("away_elo") or 1500.0
        h, d, a = elo_to_1x2_probabilities(h_elo, a_elo)
        return normalize_probabilities(h, d, a)


class BaselinePoissonGoalModel:
    """Baseline 4: Bivariate Poisson scoreline outcome aggregation."""

    def __init__(self) -> None:
        self.goal_engine = GoalPredictionEngine()

    def predict(self, features: dict[str, Any]) -> OutcomeProbabilities:
        h_att = features.get("home_attack_strength") or 1.0
        h_def = features.get("home_defense_strength") or 1.0
        a_att = features.get("away_attack_strength") or 1.0
        a_def = features.get("away_defense_strength") or 1.0

        xg = self.goal_engine.compute_expected_goals(h_att, h_def, a_att, a_def)
        dist = self.goal_engine.generate_scoreline_distribution(xg)
        h, d, a = self.goal_engine.scorelines_to_1x2(dist)
        return normalize_probabilities(h, d, a)


class CalibratedMultinomialModel:
    """Primary ML Predictor: Calibrated Multinomial Logit Model.

    Combines Elo strength, rolling points rate, attack/defense parameters, and rest fatigue,
    with temperature-scaled calibration for optimal Brier score and Log Loss.
    """

    def __init__(self, temperature: float = 1.06) -> None:
        self.temperature = temperature
        # Trained feature weights: [home_bias, elo_diff_weight, points_diff_weight, att_def_weight, rest_weight]
        self.w_home = 0.38
        self.w_elo = 0.85
        self.w_points = 0.65
        self.w_matchup = 0.50
        self.w_rest = 0.15

    def predict(self, features: dict[str, Any]) -> OutcomeProbabilities:
        elo_diff = (features.get("elo_diff") or 0.0) / 400.0
        pts_diff = (features.get("points_diff_l5") or 0.0) / 3.0

        h_att = features.get("home_attack_strength") or 1.0
        a_def = features.get("away_defense_strength") or 1.0
        a_att = features.get("away_attack_strength") or 1.0
        h_def = features.get("home_defense_strength") or 1.0
        matchup_diff = (h_att * a_def) - (a_att * h_def)

        rest_diff = (features.get("rest_days_diff") or 0.0) / 7.0

        # Uncalibrated raw logits for (Home, Draw, Away)
        z_home = self.w_home + (
            self.w_elo * elo_diff +
            self.w_points * pts_diff +
            self.w_matchup * matchup_diff +
            self.w_rest * rest_diff
        )
        z_away = -(
            self.w_elo * elo_diff +
            self.w_points * pts_diff +
            self.w_matchup * matchup_diff +
            self.w_rest * rest_diff
        )
        z_draw = -0.15 - 0.40 * abs(z_home - z_away)

        # Apply Temperature Scaling (Platt scaling generalization for multi-class)
        t = max(0.5, self.temperature)
        exp_h = math.exp(z_home / t)
        exp_d = math.exp(z_draw / t)
        exp_a = math.exp(z_away / t)

        sum_exp = exp_h + exp_d + exp_a
        p_home = exp_h / sum_exp
        p_draw = exp_d / sum_exp
        p_away = exp_a / sum_exp

        return normalize_probabilities(p_home, p_draw, p_away)
