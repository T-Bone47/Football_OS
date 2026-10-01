"""Phase 4.2: Transfer Valuation ML Engine — Uncertainty & Prediction Intervals.

Implements defensible, leakage-safe prediction intervals using Split Conformal Prediction
and empirical residual analysis.

Mathematical Methodology:
-------------------------
Transfer fees exhibit severe heteroscedasticity in raw Euro space, but variance is stabilized
in log space: z = ln(1 + fee).
Given a point estimate z_hat = f(x) on the log scale:
1. On the validation/calibration split D_cal = {(x_i, y_i)}_{i=1}^N:
   Residuals: r_i = |z_i - z_hat_i|
2. For target coverage level 1 - alpha (e.g., 80%, alpha = 0.20):
   Conformal quantile: q_alpha = Quantile_{ceil((N+1)(1-alpha))/N}(r_1, ..., r_N)
3. Conformal log interval: [z_hat - q_alpha, z_hat + q_alpha]
4. Inverse transformation to Euro space:
   lower_bound = max(0.0, exp(z_hat - q_alpha) - 1.0)
   upper_bound = exp(z_hat + q_alpha) - 1.0
   uncertainty = (upper_bound - lower_bound) / 2.0

Zero fabricated intervals: empirical coverage is rigorously measured on unseen test splits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass(frozen=True)
class PredictionInterval:
    """Represents a bounded valuation interval with confidence metadata."""
    estimated_value_eur: float
    lower_bound_eur: float
    upper_bound_eur: float
    uncertainty_eur: float
    coverage_level: float
    method: str = "split_conformal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimated_value_eur": round(self.estimated_value_eur, 2),
            "lower_bound_eur": round(self.lower_bound_eur, 2),
            "upper_bound_eur": round(self.upper_bound_eur, 2),
            "uncertainty_eur": round(self.uncertainty_eur, 2),
            "coverage_level": self.coverage_level,
            "method": self.method,
        }


@dataclass
class UncertaintyCoverageReport:
    """Empirical evaluation of prediction intervals on an evaluation dataset."""
    coverage_target: float
    empirical_coverage: float
    sample_size: int
    mean_interval_width_eur: float
    median_interval_width_eur: float
    min_interval_width_eur: float
    max_interval_width_eur: float
    undercoverage_rate: float
    overcoverage_rate: float
    coverage_by_position: Dict[str, float] = field(default_factory=dict)
    coverage_by_fee_band: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coverage_target": self.coverage_target,
            "empirical_coverage": round(self.empirical_coverage, 4),
            "sample_size": self.sample_size,
            "mean_interval_width_eur": round(self.mean_interval_width_eur, 2),
            "median_interval_width_eur": round(self.median_interval_width_eur, 2),
            "min_interval_width_eur": round(self.min_interval_width_eur, 2),
            "max_interval_width_eur": round(self.max_interval_width_eur, 2),
            "undercoverage_rate": round(self.undercoverage_rate, 4),
            "overcoverage_rate": round(self.overcoverage_rate, 4),
            "coverage_by_position": {k: round(v, 4) for k, v in self.coverage_by_position.items()},
            "coverage_by_fee_band": {k: round(v, 4) for k, v in self.coverage_by_fee_band.items()},
        }


class ConformalIntervalEstimator:
    """Split-conformal prediction interval generator for log-scale regression."""

    def __init__(self, target_coverage: float = 0.80) -> None:
        if not (0.50 <= target_coverage < 1.0):
            raise ValueError(f"Target coverage must be in [0.50, 1.0), got {target_coverage}")
        self.target_coverage = target_coverage
        self.q_alpha_: Optional[float] = None
        self.position_q_alpha_: Dict[str, float] = {}
        self.n_calibration_samples_: int = 0
        self.calibration_residuals_: List[float] = []

    @property
    def is_calibrated(self) -> bool:
        return self.q_alpha_ is not None

    def calibrate(
        self,
        y_true_eur: np.ndarray,
        y_pred_log: np.ndarray,
        positions: Optional[List[str]] = None,
    ) -> ConformalIntervalEstimator:
        """Calibrate conformal non-conformity scores on validation data.
        
        Args:
            y_true_eur: True target fees in Euros.
            y_pred_log: Model predicted log-scale targets z_hat.
            positions: Optional position groups for stratified conformal analysis.
        """
        if len(y_true_eur) == 0:
            raise ValueError("Cannot calibrate on empty data.")

        y_true_arr = np.asarray(y_true_eur, dtype=np.float64)
        y_pred_arr = np.asarray(y_pred_log, dtype=np.float64)
        y_true_log = np.log1p(np.maximum(0.0, y_true_arr))
        # Absolute residuals on log scale
        residuals = np.abs(y_true_log - y_pred_arr)
        self.calibration_residuals_ = residuals.tolist()
        self.n_calibration_samples_ = len(residuals)

        # Standard split conformal quantile with finite sample correction: ceil((N+1)(1-alpha))/N
        alpha = 1.0 - self.target_coverage
        n = len(residuals)
        p = min(1.0, math.ceil((n + 1) * (1.0 - alpha)) / n)
        self.q_alpha_ = float(np.quantile(residuals, p, method="higher" if hasattr(np, "quantile") else "linear"))

        # Stratified conformal quantile by position if provided and sample size per position >= 10
        if positions is not None and len(positions) == n:
            pos_dict: Dict[str, List[float]] = {}
            for pos, r in zip(positions, residuals):
                pos_dict.setdefault(pos, []).append(r)
            for pos, pos_res in pos_dict.items():
                if len(pos_res) >= 10:
                    pos_n = len(pos_res)
                    pos_p = min(1.0, math.ceil((pos_n + 1) * (1.0 - alpha)) / pos_n)
                    self.position_q_alpha_[pos] = float(np.quantile(pos_res, pos_p))

        return self

    def predict_interval(
        self,
        pred_log: float,
        pred_eur: float,
        position_group: Optional[str] = None,
    ) -> PredictionInterval:
        """Generate prediction interval for a single prediction."""
        if self.q_alpha_ is None:
            raise RuntimeError("Estimator must be calibrated before generating intervals.")

        # Use position-specific quantile if available, else global
        q = self.position_q_alpha_.get(position_group, self.q_alpha_) if position_group else self.q_alpha_

        # Log space interval
        lower_log = max(0.0, pred_log - q)
        upper_log = pred_log + q

        # Euro space back-transform
        lower_eur = max(0.0, math.expm1(lower_log))
        upper_eur = max(0.0, math.expm1(upper_log))
        
        # Ensure point estimate is within interval and interval is well-ordered
        lower_eur = min(lower_eur, pred_eur)
        upper_eur = max(upper_eur, pred_eur)
        uncertainty_eur = (upper_eur - lower_eur) / 2.0

        return PredictionInterval(
            estimated_value_eur=pred_eur,
            lower_bound_eur=lower_eur,
            upper_bound_eur=upper_eur,
            uncertainty_eur=uncertainty_eur,
            coverage_level=self.target_coverage,
            method="split_conformal",
        )

    def evaluate_coverage(
        self,
        y_true_eur: np.ndarray,
        y_pred_log: np.ndarray,
        y_pred_eur: np.ndarray,
        positions: Optional[List[str]] = None,
    ) -> UncertaintyCoverageReport:
        """Evaluate empirical coverage and interval properties on an independent split."""
        if self.q_alpha_ is None:
            raise RuntimeError("Estimator must be calibrated before evaluating coverage.")

        n = len(y_true_eur)
        if n == 0:
            raise ValueError("Evaluation set is empty.")

        covered = 0
        undercovered = 0  # true fee < lower bound
        overcovered = 0   # true fee > upper bound
        widths: List[float] = []

        pos_stats: Dict[str, Dict[str, int]] = {}
        fee_band_stats: Dict[str, Dict[str, int]] = {
            "<10M": {"total": 0, "covered": 0},
            "10-30M": {"total": 0, "covered": 0},
            "30-70M": {"total": 0, "covered": 0},
            ">70M": {"total": 0, "covered": 0},
        }

        for i in range(n):
            true_fee = float(y_true_eur[i])
            p_log = float(y_pred_log[i])
            p_eur = float(y_pred_eur[i])
            pos = positions[i] if positions and i < len(positions) else None

            interval = self.predict_interval(p_log, p_eur, pos)
            width = interval.upper_bound_eur - interval.lower_bound_eur
            widths.append(width)

            is_cov = interval.lower_bound_eur <= true_fee <= interval.upper_bound_eur
            if is_cov:
                covered += 1
            elif true_fee < interval.lower_bound_eur:
                undercovered += 1
            else:
                overcovered += 1

            if pos:
                stat = pos_stats.setdefault(pos, {"total": 0, "covered": 0})
                stat["total"] += 1
                if is_cov:
                    stat["covered"] += 1

            band = (
                "<10M" if true_fee < 10_000_000
                else "10-30M" if true_fee < 30_000_000
                else "30-70M" if true_fee < 70_000_000
                else ">70M"
            )
            fee_band_stats[band]["total"] += 1
            if is_cov:
                fee_band_stats[band]["covered"] += 1

        coverage_by_pos = {
            pos: s["covered"] / s["total"] for pos, s in pos_stats.items() if s["total"] > 0
        }
        coverage_by_band = {
            band: s["covered"] / s["total"] for band, s in fee_band_stats.items() if s["total"] > 0
        }

        return UncertaintyCoverageReport(
            coverage_target=self.target_coverage,
            empirical_coverage=covered / n,
            sample_size=n,
            mean_interval_width_eur=float(np.mean(widths)),
            median_interval_width_eur=float(np.median(widths)),
            min_interval_width_eur=float(np.min(widths)),
            max_interval_width_eur=float(np.max(widths)),
            undercoverage_rate=undercovered / n,
            overcoverage_rate=overcovered / n,
            coverage_by_position=coverage_by_pos,
            coverage_by_fee_band=coverage_by_band,
        )


class ValuationCalibrationAnalyzer:
    """Evaluates whether predictions are systematically under- or over-valued across segments."""

    @staticmethod
    def analyze_calibration(
        y_true_eur: np.ndarray,
        y_pred_eur: np.ndarray,
        positions: Optional[List[str]] = None,
        ages: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Calculates mean error (bias), ratio of median pred to median true, and segment calibration."""
        n = len(y_true_eur)
        if n == 0:
            return {}

        y_true_arr = np.asarray(y_true_eur, dtype=np.float64)
        y_pred_arr = np.asarray(y_pred_eur, dtype=np.float64)
        errors = y_pred_arr - y_true_arr
        mean_bias = float(np.mean(errors))
        median_bias = float(np.median(errors))
        median_pred = float(np.median(y_pred_arr))
        median_true = float(np.median(y_true_arr))
        ratio = median_pred / median_true if median_true > 0 else 1.0

        # Fee band calibration
        bands = {"<10M": [], "10-30M": [], "30-70M": [], ">70M": []}
        for yt, yp in zip(y_true_eur, y_pred_eur):
            b = "<10M" if yt < 10e6 else "10-30M" if yt < 30e6 else "30-70M" if yt < 70e6 else ">70M"
            bands[b].append(yp - yt)

        band_calib = {
            b: {
                "count": len(diffs),
                "mean_error_eur": round(float(np.mean(diffs)), 2) if diffs else 0.0,
                "median_error_eur": round(float(np.median(diffs)), 2) if diffs else 0.0,
                "tendency": "OVERPREDICTED" if diffs and np.median(diffs) > 1e6 else "UNDERPREDICTED" if diffs and np.median(diffs) < -1e6 else "WELL_CALIBRATED",
            }
            for b, diffs in bands.items()
        }

        # Position calibration
        pos_calib = {}
        if positions and len(positions) == n:
            pos_dict: Dict[str, List[float]] = {}
            for pos, yt, yp in zip(positions, y_true_eur, y_pred_eur):
                pos_dict.setdefault(pos, []).append(yp - yt)
            pos_calib = {
                pos: {
                    "count": len(diffs),
                    "mean_error_eur": round(float(np.mean(diffs)), 2),
                    "median_error_eur": round(float(np.median(diffs)), 2),
                    "tendency": "OVERPREDICTED" if np.median(diffs) > 1e6 else "UNDERPREDICTED" if np.median(diffs) < -1e6 else "WELL_CALIBRATED",
                }
                for pos, diffs in pos_dict.items()
            }

        return {
            "overall_mean_bias_eur": round(mean_bias, 2),
            "overall_median_bias_eur": round(median_bias, 2),
            "median_ratio": round(ratio, 4),
            "systematic_tendency": "OVERPREDICTED" if median_bias > 1e6 else "UNDERPREDICTED" if median_bias < -1e6 else "WELL_CALIBRATED",
            "fee_band_calibration": band_calib,
            "position_calibration": pos_calib,
        }
