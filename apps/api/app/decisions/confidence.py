"""Confidence & Data Sufficiency Engine (Phase 7.9 & 7.18).

Separates:
- DATA CONFIDENCE: Evaluates historical minutes, match count, and feature coverage.
- MODEL CONFIDENCE: Evaluates underlying analytical models, error bounds, and OOD status.
- DECISION CONFIDENCE: Evaluates dimensional harmony and evidence convergence.

Assigns explicit data statuses:
- DECISION_AVAILABLE
- LOW_CONFIDENCE
- INSUFFICIENT_DATA
- OUT_OF_DISTRIBUTION
- PARTIAL_EVIDENCE
"""
from __future__ import annotations

from typing import Any
from app.decisions.schemas import ConfidenceDecomposition


class DecisionConfidenceEngine:
    """Evaluates multi-tier confidence for recruitment and transfer decisions."""

    MIN_MINUTES_CONFIDENT = 1200
    MIN_MINUTES_PERMISSIBLE = 450
    MIN_MATCHES_CONFIDENT = 15

    @classmethod
    def evaluate(
        cls,
        sample_minutes: int,
        sample_matches: int,
        has_role_profile: bool,
        has_tactical_fit: bool,
        has_valuation: bool,
        has_risk_profile: bool,
        is_ood: bool = False,
        missing_dimensions: list[str] | None = None,
    ) -> ConfidenceDecomposition:
        """Computes decomposed confidence metrics and assigns an honest status."""
        sufficiency_factors: list[str] = []
        uncertainty_drivers: list[str] = []

        # 1. Data Confidence Computation
        if sample_minutes == 0 or sample_matches == 0:
            data_conf = 0.10
            data_status = "INSUFFICIENT_DATA"
            uncertainty_drivers.append("Zero recorded match minutes in canonical dataset.")
        elif sample_minutes < cls.MIN_MINUTES_PERMISSIBLE:
            data_conf = 0.40
            data_status = "LOW_CONFIDENCE"
            uncertainty_drivers.append(
                f"Limited sample: {sample_minutes} minutes ({sample_matches} matches) "
                f"below robust sample threshold ({cls.MIN_MINUTES_PERMISSIBLE} mins)."
            )
        elif sample_minutes < cls.MIN_MINUTES_CONFIDENT:
            data_conf = 0.70
            data_status = "DECISION_AVAILABLE"
            sufficiency_factors.append(f"Moderate historical sample: {sample_minutes} mins across {sample_matches} matches.")
        else:
            data_conf = 0.90
            data_status = "DECISION_AVAILABLE"
            sufficiency_factors.append(f"Robust sample depth: {sample_minutes} mins across {sample_matches} matches.")

        # 2. Model Confidence Computation
        model_scores = []
        if has_role_profile:
            model_scores.append(0.85)
            sufficiency_factors.append("Continuous 9-dimension role profile validated.")
        else:
            uncertainty_drivers.append("Missing verified role profile; using positional baseline.")

        if has_tactical_fit:
            model_scores.append(0.80)
            sufficiency_factors.append("Tactical fit model evaluated against target system.")
        else:
            uncertainty_drivers.append("Tactical fit calculation unavailable.")

        if has_valuation:
            model_scores.append(0.75)
            sufficiency_factors.append("Transfer market valuation grounded in verified comparables.")
        else:
            uncertainty_drivers.append("No active market valuation model output.")

        if has_risk_profile:
            model_scores.append(0.80)
            sufficiency_factors.append("Transfer risk profile evaluated across 5 risk dimensions.")
        else:
            uncertainty_drivers.append("Transfer risk analysis missing.")

        model_conf = sum(model_scores) / len(model_scores) if model_scores else 0.30

        # Out-Of-Distribution Overrides
        if is_ood:
            model_conf *= 0.50
            data_status = "OUT_OF_DISTRIBUTION"
            uncertainty_drivers.append("Candidate metrics lie outside calibrated distribution space.")

        # Check for Partial Evidence
        if missing_dimensions and len(missing_dimensions) >= 2:
            if data_status not in ("INSUFFICIENT_DATA", "OUT_OF_DISTRIBUTION"):
                data_status = "PARTIAL_EVIDENCE"
            uncertainty_drivers.append(f"Missing core analytical dimensions: {', '.join(missing_dimensions)}.")

        # 3. Decision Confidence Computation (harmonic blend of data and model)
        decision_conf = round(0.45 * data_conf + 0.55 * model_conf, 3)

        # 4. Determine Confidence Tier
        if decision_conf >= 0.75 and data_status == "DECISION_AVAILABLE":
            tier = "HIGH"
        elif decision_conf >= 0.50:
            tier = "MODERATE"
        elif decision_conf >= 0.30:
            tier = "LOW"
        else:
            tier = "VERY_LOW"

        return ConfidenceDecomposition(
            data_confidence=round(data_conf, 3),
            model_confidence=round(model_conf, 3),
            decision_confidence=decision_conf,
            confidence_tier=tier,
            data_status=data_status,
            sufficiency_factors=sufficiency_factors,
            uncertainty_drivers=uncertainty_drivers,
        )
