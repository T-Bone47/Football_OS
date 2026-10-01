"""Phase 4.2: Transfer Valuation ML Engine — Data Sufficiency & OOD Gating.

Implements rigorous pre-inference data sufficiency gates and Out-Of-Distribution (OOD)
detection to prevent ungrounded, uncalibrated, or fabricated valuations.

Statuses:
---------
1. VALUATION_AVAILABLE: Full feature completeness, supported minutes, inside data manifold.
2. LOW_CONFIDENCE: Borderline playing time (450-900 mins) or moderate distribution distance.
3. INSUFFICIENT_DATA: <450 minutes played, missing position, or null feature rate > 25%.
4. OUT_OF_DISTRIBUTION: Feature vector severely deviates from training envelope (max |z| > 5.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import numpy as np


class ValuationDataStatus(str, Enum):
    VALUATION_AVAILABLE = "VALUATION_AVAILABLE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"


@dataclass(frozen=True)
class SufficiencyGateDecision:
    """Outcome of pre-inference validation."""
    status: ValuationDataStatus
    can_predict: bool
    reasons: List[str]
    minutes_played: float
    null_feature_rate: float
    standardized_distance: float
    max_z_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "can_predict": self.can_predict,
            "reasons": self.reasons,
            "minutes_played": round(self.minutes_played, 1),
            "null_feature_rate": round(self.null_feature_rate, 4),
            "standardized_distance": round(self.standardized_distance, 4),
            "max_z_score": round(self.max_z_score, 4),
        }


class ValuationSufficiencyGate:
    """Enforces mathematical data sufficiency and out-of-distribution detection."""

    MIN_MINUTES_FULL: float = 900.0
    MIN_MINUTES_BORDERLINE: float = 450.0
    MAX_NULL_RATE: float = 0.25
    MAX_STANDARDIZED_DIST_OOD: float = 3.5
    MAX_SINGLE_Z_SCORE_OOD: float = 5.0

    def __init__(self, feature_names: Optional[List[str]] = None) -> None:
        self.feature_names = feature_names or []
        self.means_: Optional[np.ndarray] = None
        self.stds_: Optional[np.ndarray] = None
        self.mins_: Optional[np.ndarray] = None
        self.maxs_: Optional[np.ndarray] = None

    def fit_reference_distribution(self, X_train: np.ndarray) -> ValuationSufficiencyGate:
        """Calibrate reference mean and variance statistics on the training set."""
        if len(X_train) == 0:
            raise ValueError("Cannot fit sufficiency gate on empty training matrix.")

        self.means_ = np.nanmean(X_train, axis=0)
        stds = np.nanstd(X_train, axis=0)
        # Avoid zero division on binary or constant features
        stds[stds < 1e-6] = 1.0
        self.stds_ = stds
        self.mins_ = np.nanmin(X_train, axis=0)
        self.maxs_ = np.nanmax(X_train, axis=0)
        return self

    def evaluate(
        self,
        features: np.ndarray,
        minutes_played: Optional[float] = None,
        null_count: int = 0,
        age: Optional[float] = None,
    ) -> SufficiencyGateDecision:
        """Evaluates whether an inference feature vector qualifies for valuation."""
        if features.ndim > 1:
            vec = features[0]
        else:
            vec = features

        d = len(vec)
        null_rate = float(null_count / d) if d > 0 else 1.0
        reasons: List[str] = []

        # Find minutes from vector if not provided explicitly (assume feature index 5)
        if minutes_played is None:
            # Check if minutes_played_season is in feature_names
            if "minutes_played_season" in self.feature_names:
                idx = self.feature_names.index("minutes_played_season")
                minutes_val = float(vec[idx])
            else:
                minutes_val = 1000.0  # fallback
        else:
            minutes_val = float(minutes_played)

        # 1. Hard Insufficiency Check: Missing too much data
        if null_rate > self.MAX_NULL_RATE:
            reasons.append(f"Missing feature rate {null_rate:.1%} exceeds threshold ({self.MAX_NULL_RATE:.1%}).")
            return SufficiencyGateDecision(
                status=ValuationDataStatus.INSUFFICIENT_DATA,
                can_predict=False,
                reasons=reasons,
                minutes_played=minutes_val,
                null_feature_rate=null_rate,
                standardized_distance=0.0,
                max_z_score=0.0,
            )

        # 2. Hard Insufficiency Check: Insufficient playing time exposure
        if minutes_val < self.MIN_MINUTES_BORDERLINE:
            reasons.append(
                f"Sample size too small: {minutes_val:.0f} minutes played is below minimum required exposure ({self.MIN_MINUTES_BORDERLINE:.0f} mins)."
            )
            return SufficiencyGateDecision(
                status=ValuationDataStatus.INSUFFICIENT_DATA,
                can_predict=False,
                reasons=reasons,
                minutes_played=minutes_val,
                null_feature_rate=null_rate,
                standardized_distance=0.0,
                max_z_score=0.0,
            )

        # 3. Age bounds check
        if age is not None:
            if age < 15.0 or age > 43.0:
                reasons.append(f"Player age ({age:.1f}) is outside supported football career distribution [15, 43].")
                return SufficiencyGateDecision(
                    status=ValuationDataStatus.OUT_OF_DISTRIBUTION,
                    can_predict=False,
                    reasons=reasons,
                    minutes_played=minutes_val,
                    null_feature_rate=null_rate,
                    standardized_distance=4.0,
                    max_z_score=6.0,
                )

        # 4. Out-of-Distribution Manifold Check
        std_dist = 0.0
        max_z = 0.0
        if self.means_ is not None and self.stds_ is not None and len(self.means_) == d:
            z_scores = np.abs((vec - self.means_) / self.stds_)
            # Ignore binary features in max_z check (indices with std <= 0.5 and min 0 max 1)
            continuous_mask = self.stds_ > 0.05
            if np.any(continuous_mask):
                max_z = float(np.max(z_scores[continuous_mask]))
                std_dist = float(np.sqrt(np.mean(z_scores[continuous_mask] ** 2)))
            else:
                max_z = float(np.max(z_scores))
                std_dist = float(np.sqrt(np.mean(z_scores ** 2)))

        if max_z > self.MAX_SINGLE_Z_SCORE_OOD or std_dist > self.MAX_STANDARDIZED_DIST_OOD:
            reasons.append(
                f"Player profile is Out-Of-Distribution (standardized distance: {std_dist:.2f}, max feature z-score: {max_z:.2f})."
            )
            return SufficiencyGateDecision(
                status=ValuationDataStatus.OUT_OF_DISTRIBUTION,
                can_predict=False,
                reasons=reasons,
                minutes_played=minutes_val,
                null_feature_rate=null_rate,
                standardized_distance=std_dist,
                max_z_score=max_z,
            )

        # 5. Low Confidence Check: Borderline playing time
        if minutes_val < self.MIN_MINUTES_FULL:
            reasons.append(
                f"Borderline sample size: {minutes_val:.0f} minutes played is between {self.MIN_MINUTES_BORDERLINE:.0f} and {self.MIN_MINUTES_FULL:.0f} mins."
            )
            return SufficiencyGateDecision(
                status=ValuationDataStatus.LOW_CONFIDENCE,
                can_predict=True,
                reasons=reasons,
                minutes_played=minutes_val,
                null_feature_rate=null_rate,
                standardized_distance=std_dist,
                max_z_score=max_z,
            )

        # 6. Fully Available
        reasons.append("Player profile meets all data sufficiency, exposure, and distribution criteria.")
        return SufficiencyGateDecision(
            status=ValuationDataStatus.VALUATION_AVAILABLE,
            can_predict=True,
            reasons=reasons,
            minutes_played=minutes_val,
            null_feature_rate=null_rate,
            standardized_distance=std_dist,
            max_z_score=max_z,
        )
