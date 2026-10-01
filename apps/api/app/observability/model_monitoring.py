"""Model Performance & Distribution Monitoring Primitives (Phase 8 Section 7).

Provides statistical diagnostics for:
1. Valuation Engine:
   - Prediction distribution (mean, median, p5, p95, IQR)
   - Error distribution (MAE, RMSE, MAPE)
   - Drift metric: Population Stability Index (PSI)
2. Transfer Risk Engine:
   - Score distribution across tiers (LOW, MEDIUM, HIGH, CRITICAL)
   - Missingness & unobserved component rate
   - Sub-dimension balance (Performance, Adaptation, Financial, Availability)
3. Tactical Fit Engine:
   - Input feature coverage rate
   - Output fit score distribution & system threshold penalty impact
4. Match Prediction Engine:
   - Log Loss, Brier score
   - Calibration Curve & Expected Calibration Error (ECE)
   - Home / Draw / Away probability distribution
5. Role Similarity Engine:
   - Candidate universe coverage
   - Cosine similarity distribution and dispersion

Policy: Never claim live model degradation without sufficient observational sample size (N >= 30).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence
import numpy as np


@dataclass
class DistributionMetrics:
    count: int
    mean: float
    median: float
    std: float
    p5: float
    p95: float
    iqr: float


def compute_distribution_metrics(values: Sequence[float]) -> DistributionMetrics:
    if not values:
        return DistributionMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    arr = np.array(values, dtype=float)
    p25, p75 = np.percentile(arr, [25, 75])
    return DistributionMetrics(
        count=int(len(arr)),
        mean=round(float(np.mean(arr)), 4),
        median=round(float(np.median(arr)), 4),
        std=round(float(np.std(arr)), 4),
        p5=round(float(np.percentile(arr, 5)), 4),
        p95=round(float(np.percentile(arr, 95)), 4),
        iqr=round(float(p75 - p25), 4),
    )


def compute_psi(reference: Sequence[float], current: Sequence[float], bins: int = 10) -> float:
    """Computes Population Stability Index (PSI) between baseline and current distributions."""
    if len(reference) < 10 or len(current) < 10:
        return 0.0  # Insufficient sample to assert drift

    ref_arr = np.array(reference, dtype=float)
    curr_arr = np.array(current, dtype=float)

    # Compute quantile bin edges from reference
    quantiles = np.linspace(0, 100, bins + 1)
    bin_edges = np.percentile(ref_arr, quantiles)
    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    ref_counts, _ = np.histogram(ref_arr, bins=bin_edges)
    curr_counts, _ = np.histogram(curr_arr, bins=bin_edges)

    # Add small epsilon to prevent div-by-zero
    eps = 1e-4
    ref_pct = (ref_counts / len(ref_arr)) + eps
    curr_pct = (curr_counts / len(curr_arr)) + eps

    psi = np.sum((curr_pct - ref_pct) * np.log(curr_pct / ref_pct))
    return round(float(psi), 4)


class ValuationMonitor:
    """Monitoring primitives for Valuation Engine."""

    @staticmethod
    def audit_predictions(
        predictions: Sequence[float],
        actuals: Sequence[float] | None = None,
        baseline_predictions: Sequence[float] | None = None,
    ) -> dict[str, Any]:
        dist = compute_distribution_metrics(predictions)
        res: dict[str, Any] = {
            "prediction_distribution": asdict(dist),
            "sample_size": len(predictions),
            "sufficient_sample": len(predictions) >= 30,
        }

        if actuals and len(actuals) == len(predictions) and len(predictions) > 0:
            preds = np.array(predictions)
            acts = np.array(actuals)
            errors = preds - acts
            mae = float(np.mean(np.abs(errors)))
            rmse = float(np.sqrt(np.mean(errors ** 2)))
            mape = float(np.mean(np.abs(errors) / np.maximum(acts, 1.0)))
            res["error_metrics"] = {
                "mae": round(mae, 2),
                "rmse": round(rmse, 2),
                "mape": round(mape, 4),
            }

        if baseline_predictions and len(baseline_predictions) >= 10 and len(predictions) >= 10:
            psi = compute_psi(baseline_predictions, predictions)
            drift_status = "STABLE" if psi < 0.1 else ("MODERATE_DRIFT" if psi < 0.25 else "SIGNIFICANT_DRIFT")
            res["drift"] = {"psi": psi, "status": drift_status}
        else:
            res["drift"] = {"psi": 0.0, "status": "INSUFFICIENT_DATA"}

        return res


class RiskMonitor:
    """Monitoring primitives for Transfer Risk Engine."""

    @staticmethod
    def audit_risk_scores(
        overall_scores: Sequence[float],
        tier_counts: dict[str, int],
        component_scores: dict[str, list[float]],
    ) -> dict[str, Any]:
        dist = compute_distribution_metrics(overall_scores)
        total = sum(tier_counts.values()) if tier_counts else len(overall_scores)
        tier_distribution = {k: round(v / max(1, total), 4) for k, v in tier_counts.items()}

        comp_dist = {}
        for comp_name, vals in component_scores.items():
            comp_dist[comp_name] = asdict(compute_distribution_metrics(vals))

        return {
            "distribution": asdict(dist),
            "tier_distribution": tier_distribution,
            "component_distributions": comp_dist,
            "sample_size": len(overall_scores),
            "status": "VALIDATED" if len(overall_scores) >= 10 else "LOW_SAMPLE",
        }


class TacticalFitMonitor:
    """Monitoring primitives for Tactical Fit Engine."""

    @staticmethod
    def audit_fit_evaluations(
        fit_scores: Sequence[float],
        features_supplied: int,
        features_expected: int,
    ) -> dict[str, Any]:
        dist = compute_distribution_metrics(fit_scores)
        coverage_rate = round(features_supplied / max(1, features_expected), 4)
        return {
            "fit_score_distribution": asdict(dist),
            "feature_coverage_rate": coverage_rate,
            "is_coverage_sufficient": coverage_rate >= 0.70,
            "status": "HEALTHY" if coverage_rate >= 0.70 else "PARTIAL_EVIDENCE",
        }


class MatchPredictionMonitor:
    """Monitoring primitives for Match Prediction Engine."""

    @staticmethod
    def compute_brier_and_log_loss(
        predicted_probs: Sequence[tuple[float, float, float]],  # (home, draw, away)
        actual_outcomes: Sequence[int],  # 0: home, 1: draw, 2: away
    ) -> dict[str, float]:
        if not predicted_probs or len(predicted_probs) != len(actual_outcomes):
            return {"brier_score": 0.0, "log_loss": 0.0, "ece": 0.0}

        brier_sum = 0.0
        log_loss_sum = 0.0
        n = len(predicted_probs)

        # For ECE
        bins = 10
        bin_confidences = [0.0] * bins
        bin_accuracies = [0.0] * bins
        bin_counts = [0] * bins

        for (p_h, p_d, p_a), actual in zip(predicted_probs, actual_outcomes):
            probs = [p_h, p_d, p_a]
            # Brier multi-class: sum (p_i - o_i)^2
            one_hot = [1.0 if i == actual else 0.0 for i in range(3)]
            brier_sum += sum((p - o) ** 2 for p, o in zip(probs, one_hot))

            # Log loss with clipping
            p_actual = max(1e-12, min(1.0, probs[actual]))
            log_loss_sum += -math.log(p_actual)

            # ECE binning
            max_prob = max(probs)
            pred_class = probs.index(max_prob)
            bin_idx = min(bins - 1, int(max_prob * bins))
            bin_confidences[bin_idx] += max_prob
            bin_accuracies[bin_idx] += 1.0 if pred_class == actual else 0.0
            bin_counts[bin_idx] += 1

        ece = 0.0
        for i in range(bins):
            if bin_counts[i] > 0:
                avg_conf = bin_confidences[i] / bin_counts[i]
                avg_acc = bin_accuracies[i] / bin_counts[i]
                ece += (bin_counts[i] / n) * abs(avg_acc - avg_conf)

        return {
            "brier_score": round(brier_sum / n, 4),
            "log_loss": round(log_loss_sum / n, 4),
            "ece": round(ece, 4),
        }
