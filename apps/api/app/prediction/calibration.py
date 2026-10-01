"""Probability Calibration & Multi-Class Evaluation Engine (Phase 6.12, 6.13, 6.14).

Primary Probabilistic Metrics:
- Multi-Class Log Loss (Cross-Entropy)
- Multi-Class Brier Score (Quadratic Scoring Rule)
- Expected Calibration Error (ECE) across reliability bins

Secondary Metrics:
- Accuracy, Macro F1, Goal MAE, Goal RMSE
"""
from __future__ import annotations

import math
from typing import Sequence
import numpy as np


def multi_class_brier_score(
    y_true: Sequence[int],
    y_prob: Sequence[Sequence[float]],
) -> float:
    """Calculates multi-class Brier score: lower is better (0.0 = perfect, 0.667 = random)."""
    n = len(y_true)
    if n == 0:
        return 0.0

    total = 0.0
    for i in range(n):
        true_k = y_true[i]
        probs = y_prob[i]
        for k in range(len(probs)):
            target = 1.0 if k == true_k else 0.0
            total += (probs[k] - target) ** 2

    return round(total / n, 4)


def multi_class_log_loss(
    y_true: Sequence[int],
    y_prob: Sequence[Sequence[float]],
    eps: float = 1e-15,
) -> float:
    """Calculates multi-class log loss: lower is better."""
    n = len(y_true)
    if n == 0:
        return 0.0

    total = 0.0
    for i in range(n):
        true_k = y_true[i]
        p = max(eps, min(1.0 - eps, y_prob[i][true_k]))
        total -= math.log(p)

    return round(total / n, 4)


def expected_calibration_error(
    y_true: Sequence[int],
    y_prob: Sequence[Sequence[float]],
    n_bins: int = 10,
) -> float:
    """Calculates Expected Calibration Error (ECE) across confidence bins."""
    n = len(y_true)
    if n == 0:
        return 0.0

    confidences = []
    accuracies = []

    for i in range(n):
        probs = y_prob[i]
        pred_k = int(np.argmax(probs))
        conf = float(probs[pred_k])
        is_correct = 1.0 if pred_k == y_true[i] else 0.0
        confidences.append(conf)
        accuracies.append(is_correct)

    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0

    for b in range(n_bins):
        bin_low = bin_boundaries[b]
        bin_high = bin_boundaries[b + 1]

        in_bin = [
            i for i, c in enumerate(confidences)
            if (bin_low <= c < bin_high) or (b == n_bins - 1 and bin_low <= c <= bin_high)
        ]

        if in_bin:
            bin_size = len(in_bin)
            bin_acc = sum(accuracies[idx] for idx in in_bin) / bin_size
            bin_conf = sum(confidences[idx] for idx in in_bin) / bin_size
            ece += (bin_size / n) * abs(bin_acc - bin_conf)

    return round(ece, 4)


def classification_metrics(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    n_classes: int = 3,
) -> dict[str, float]:
    """Calculates accuracy and macro F1 score."""
    n = len(y_true)
    if n == 0:
        return {"accuracy": 0.0, "macro_f1": 0.0}

    correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    accuracy = correct / n

    f1_scores = []
    for k in range(n_classes):
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == k and yp == k)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt != k and yp == k)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == k and yp != k)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        f1_scores.append(f1)

    macro_f1 = sum(f1_scores) / n_classes
    return {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
    }


def goal_regression_metrics(
    actual: Sequence[float],
    predicted: Sequence[float],
) -> dict[str, float]:
    """Calculates Mean Absolute Error and Root Mean Squared Error for goal predictions."""
    n = len(actual)
    if n == 0:
        return {"mae": 0.0, "rmse": 0.0}

    mae = sum(abs(a - p) for a, p in zip(actual, predicted)) / n
    mse = sum((a - p) ** 2 for a, p in zip(actual, predicted)) / n
    return {
        "mae": round(mae, 3),
        "rmse": round(math.sqrt(mse), 3),
    }


class TemperatureScalingCalibrator:
    """Calibrates model logits by optimizing temperature T on validation split."""

    def __init__(self, initial_temperature: float = 1.0) -> None:
        self.temperature = initial_temperature

    def fit(self, val_logits: list[list[float]], y_val: list[int]) -> float:
        """Finds temperature T in [0.5, 3.0] minimizing validation cross-entropy."""
        best_t = 1.0
        best_loss = float("inf")

        # Grid search over feasible temperatures
        for candidate_t in np.linspace(0.6, 2.5, 39):
            probs = []
            for logits in val_logits:
                exp_z = [math.exp(z / candidate_t) for z in logits]
                s = sum(exp_z)
                probs.append([v / s for v in exp_z])

            loss = multi_class_log_loss(y_val, probs)
            if loss < best_loss:
                best_loss = loss
                best_t = candidate_t

        self.temperature = round(best_t, 3)
        return self.temperature
