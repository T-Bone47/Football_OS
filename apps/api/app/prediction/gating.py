"""Data Sufficiency & Out-Of-Distribution (OOD) Gating Engine (Phase 6.19 & 6.20).

Prevents over-confident predictions on sparse, shifted, or unobserved team histories.
Gates predictions into:
- PREDICTION_AVAILABLE: Full sample depth, regular distribution
- LOW_CONFIDENCE: Sparse sample size (1-2 matches), wider uncertainty
- INSUFFICIENT_DATA: 0 matches found for one or both clubs prior to cutoff
- OUT_OF_DISTRIBUTION: Feature distance or extreme domain shifts detected
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class GatingResult(BaseModel):
    """Result of data sufficiency and distribution checks."""
    model_config = ConfigDict(extra="ignore")

    status: str  # PREDICTION_AVAILABLE, LOW_CONFIDENCE, INSUFFICIENT_DATA, OUT_OF_DISTRIBUTION
    confidence_multiplier: float = 1.0  # 1.0 for normal, 0.6 for low confidence, 0.0 for insufficient
    reasons: list[str] = Field(default_factory=list)
    home_matches_count: int = 0
    away_matches_count: int = 0
    is_ood: bool = False


class PredictionGatingEngine:
    """Evaluates whether pre-match features meet the statistical requirements for inference."""

    MIN_MATCHES_CONFIDENT = 5
    MIN_MATCHES_PERMISSIBLE = 2
    MAX_ELO_DIFF_IN_DISTRIBUTION = 550.0

    def evaluate(
        self,
        features: dict[str, Any],
        home_sample_size: int,
        away_sample_size: int,
        h2h_sample_size: int = 0,
    ) -> GatingResult:
        """Determines data status and gating flags based on historical depth and feature ranges."""
        reasons: list[str] = []
        is_ood = False

        # 1. Check for Complete Lack of Data
        if home_sample_size == 0 and away_sample_size == 0:
            reasons.append("Zero historical matches recorded for either club prior to kickoff.")
            return GatingResult(
                status="INSUFFICIENT_DATA",
                confidence_multiplier=0.0,
                reasons=reasons,
                home_matches_count=0,
                away_matches_count=0,
                is_ood=False,
            )

        if home_sample_size == 0:
            reasons.append("Zero historical matches recorded for home club prior to kickoff.")
            return GatingResult(
                status="INSUFFICIENT_DATA",
                confidence_multiplier=0.0,
                reasons=reasons,
                home_matches_count=0,
                away_matches_count=away_sample_size,
                is_ood=False,
            )

        if away_sample_size == 0:
            reasons.append("Zero historical matches recorded for away club prior to kickoff.")
            return GatingResult(
                status="INSUFFICIENT_DATA",
                confidence_multiplier=0.0,
                reasons=reasons,
                home_matches_count=home_sample_size,
                away_matches_count=0,
                is_ood=False,
            )

        # 2. Check for Out-Of-Distribution (OOD) Features
        elo_diff = abs(features.get("elo_diff") or 0.0)
        if elo_diff > self.MAX_ELO_DIFF_IN_DISTRIBUTION:
            is_ood = True
            reasons.append(
                f"Extreme Elo rating disparity (|ΔElo|={elo_diff:.0f} > {self.MAX_ELO_DIFF_IN_DISTRIBUTION:.0f}) "
                "outside standard competitive distribution."
            )

        home_points = features.get("home_points_l5")
        away_points = features.get("away_points_l5")
        if home_points is not None and (home_points < 0.0 or home_points > 3.0):
            is_ood = True
            reasons.append(f"Invalid home points rate ({home_points}).")
        if away_points is not None and (away_points < 0.0 or away_points > 3.0):
            is_ood = True
            reasons.append(f"Invalid away points rate ({away_points}).")

        if is_ood:
            return GatingResult(
                status="OUT_OF_DISTRIBUTION",
                confidence_multiplier=0.5,
                reasons=reasons,
                home_matches_count=home_sample_size,
                away_matches_count=away_sample_size,
                is_ood=True,
            )

        # 3. Check for Low Confidence (Sparse Sample)
        if home_sample_size < self.MIN_MATCHES_PERMISSIBLE or away_sample_size < self.MIN_MATCHES_PERMISSIBLE:
            reasons.append(
                f"Limited sample size: home team has {home_sample_size} matches, away team has {away_sample_size} "
                f"matches (minimum {self.MIN_MATCHES_PERMISSIBLE} required for normal confidence)."
            )
            return GatingResult(
                status="LOW_CONFIDENCE",
                confidence_multiplier=0.65,
                reasons=reasons,
                home_matches_count=home_sample_size,
                away_matches_count=away_sample_size,
                is_ood=False,
            )

        # 4. Standard Prediction Available
        if home_sample_size < self.MIN_MATCHES_CONFIDENT or away_sample_size < self.MIN_MATCHES_CONFIDENT:
            reasons.append(
                f"Moderate sample depth ({home_sample_size} home / {away_sample_size} away historical fixtures)."
            )
        else:
            reasons.append(
                f"Robust sample depth ({home_sample_size} home / {away_sample_size} away historical fixtures)."
            )

        if h2h_sample_size > 0:
            reasons.append(f"{h2h_sample_size} direct head-to-head match(es) observed in dataset.")

        return GatingResult(
            status="PREDICTION_AVAILABLE",
            confidence_multiplier=1.0,
            reasons=reasons,
            home_matches_count=home_sample_size,
            away_matches_count=away_sample_size,
            is_ood=False,
        )
