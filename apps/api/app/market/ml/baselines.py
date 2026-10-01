"""Baseline Valuation Models Suite (Phase 4.2J).

Implements 4 reference baselines evaluated on identical temporal test sets:
- BASELINE 1: Global Historical Median
- BASELINE 2: Position Group Median
- BASELINE 3: Age + Position Group Empirical Benchmark
- BASELINE 4: Comparable-Transfer Median (Phase 4.1M)

Ensures that machine learning models must strictly demonstrate incremental predictive value.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Sequence
import numpy as np

from app.market.ml.dataset import ValuationMLSample
from app.market.valuation import BaselineValuationEngine


def calculate_metrics(
    y_true_eur: Sequence[float],
    y_pred_eur: Sequence[float],
) -> dict[str, float]:
    """Computes standardized regression evaluation metrics in EUR."""
    if len(y_true_eur) == 0 or len(y_true_eur) != len(y_pred_eur):
        return {}

    y_t = np.array(y_true_eur, dtype=np.float64)
    y_p = np.array(y_pred_eur, dtype=np.float64)

    errors = y_p - y_t
    abs_errors = np.abs(errors)
    sq_errors = errors ** 2

    # Avoid log of zero
    log_y_t = np.log(np.maximum(y_t, 1.0))
    log_y_p = np.log(np.maximum(y_p, 1.0))
    log_abs_errors = np.abs(log_y_p - log_y_t)
    log_sq_errors = (log_y_p - log_y_t) ** 2

    mae = float(np.mean(abs_errors))
    rmse = float(np.sqrt(np.mean(sq_errors)))
    med_ae = float(np.median(abs_errors))
    log_mae = float(np.mean(log_abs_errors))
    log_rmse = float(np.sqrt(np.mean(log_sq_errors)))

    # R-squared
    ss_res = float(np.sum(sq_errors))
    ss_tot = float(np.sum((y_t - np.mean(y_t)) ** 2))
    r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 1e-9 else 0.0

    return {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "med_ae": round(med_ae, 2),
        "log_mae": round(log_mae, 4),
        "log_rmse": round(log_rmse, 4),
        "r2": round(r2, 4),
    }


class GlobalMedianBaseline:
    """Baseline 1: Predicts constant global median of historical training transactions."""

    def __init__(self) -> None:
        self.global_median: float = 20_000_000.0

    def fit(self, train_samples: list[ValuationMLSample]) -> "GlobalMedianBaseline":
        fees = [s.target_fee_eur for s in train_samples if s.target_fee_eur > 0]
        if fees:
            self.global_median = float(statistics.median(fees))
        return self

    def predict(self, samples: list[ValuationMLSample]) -> list[float]:
        return [self.global_median for _ in samples]


class PositionMedianBaseline:
    """Baseline 2: Predicts position group median (GK, DEF, MID, ATT) from training set."""

    def __init__(self) -> None:
        self.position_medians: dict[str, float] = {}
        self.default_median: float = 20_000_000.0

    def fit(self, train_samples: list[ValuationMLSample]) -> "PositionMedianBaseline":
        by_pos: dict[str, list[float]] = {}
        all_fees = [s.target_fee_eur for s in train_samples if s.target_fee_eur > 0]
        self.default_median = float(statistics.median(all_fees)) if all_fees else 20_000_000.0

        for s in train_samples:
            by_pos.setdefault(s.position_group, []).append(s.target_fee_eur)

        for pos, fees in by_pos.items():
            self.position_medians[pos] = float(statistics.median(fees)) if fees else self.default_median
        return self

    def predict(self, samples: list[ValuationMLSample]) -> list[float]:
        return [self.position_medians.get(s.position_group, self.default_median) for s in samples]


class AgePositionBenchmarkBaseline:
    """Baseline 3: Predicts position group median scaled by empirical age curve adjustment."""

    def __init__(self) -> None:
        self.pos_baseline = PositionMedianBaseline()

    def fit(self, train_samples: list[ValuationMLSample]) -> "AgePositionBenchmarkBaseline":
        self.pos_baseline.fit(train_samples)
        return self

    def predict(self, samples: list[ValuationMLSample]) -> list[float]:
        preds: list[float] = []
        base_preds = self.pos_baseline.predict(samples)
        for s, base in zip(samples, base_preds):
            age = s.features.get("age_at_transfer", 25.0)
            age_factor = BaselineValuationEngine.get_age_adjustment(age)
            preds.append(round(base * age_factor, 2))
        return preds


class ComparableMedianBaseline:
    """Baseline 4: Predicts pre-computed comparable cohort median with age scaling."""

    def __init__(self) -> None:
        pass

    def fit(self, train_samples: list[ValuationMLSample]) -> "ComparableMedianBaseline":
        return self

    def predict(self, samples: list[ValuationMLSample]) -> list[float]:
        preds: list[float] = []
        for s in samples:
            comp_med = s.features.get("comparable_median_fee_eur")
            if comp_med and comp_med > 0:
                preds.append(round(comp_med, 2))
            else:
                cohort_med = s.features.get("cohort_median_fee_eur", 20_000_000.0)
                age_factor = s.features.get("age_curve_factor", 1.0)
                preds.append(round(cohort_med * age_factor, 2))
        return preds


def evaluate_all_baselines(
    train_samples: list[ValuationMLSample],
    eval_samples: list[ValuationMLSample],
) -> dict[str, dict[str, float]]:
    """Evaluates all 4 baselines on the provided evaluation samples."""
    y_eval_eur = [s.target_fee_eur for s in eval_samples]

    b1 = GlobalMedianBaseline().fit(train_samples)
    b2 = PositionMedianBaseline().fit(train_samples)
    b3 = AgePositionBenchmarkBaseline().fit(train_samples)
    b4 = ComparableMedianBaseline().fit(train_samples)

    return {
        "global_median": calculate_metrics(y_eval_eur, b1.predict(eval_samples)),
        "position_median": calculate_metrics(y_eval_eur, b2.predict(eval_samples)),
        "age_position_benchmark": calculate_metrics(y_eval_eur, b3.predict(eval_samples)),
        "comparable_baseline": calculate_metrics(y_eval_eur, b4.predict(eval_samples)),
    }
