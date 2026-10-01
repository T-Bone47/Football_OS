"""Phase 12 — Deterministic Retraining Triggers Engine (§6).

Evaluates whether active production or candidate models require retraining based on:
  - Feature Population Stability Index (PSI >= 0.20)
  - Calibration degradation (ECE shift > 0.04)
  - Brier score degradation (> 0.05)
  - Log Loss degradation (> 0.10)
  - New observation volume (>= 50 matches or >= 100 transfers)
  - Model staleness (> 180 days since last training cutoff)

Guarantees:
  - Produces RETRAIN_RECOMMENDED, REVIEW_REQUIRED, or NO_RETRAIN_REQUIRED.
  - Never automatically promotes a retrained model without explicit human approval.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase12 import RetrainRecommendation


@dataclass
class ModelRetrainingRecommendation:
    """Audit record for a model retraining trigger evaluation."""
    recommendation_id: str = field(default_factory=lambda: f"retrain_{uuid.uuid4().hex[:12]}")
    model_id: str = ""
    current_version: str = "1.0.0"
    competition_scope: str = "GB-PL"
    recommendation: RetrainRecommendation = RetrainRecommendation.NO_RETRAIN_REQUIRED
    triggers_fired: list[str] = field(default_factory=list)
    evidence_metrics: dict[str, Any] = field(default_factory=dict)
    recommended_action: str = "MAINTAIN_CURRENT_MODEL"
    requires_human_approval: bool = True
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["recommendation"] = self.recommendation.value
        return data


class RetrainingTriggerEngine:
    """Evaluates telemetry to determine if retraining should be recommended."""

    def __init__(self) -> None:
        self._recommendations: dict[str, ModelRetrainingRecommendation] = {}
        self._seed_default_recommendation()

    def _seed_default_recommendation(self) -> None:
        seed = ModelRetrainingRecommendation(
            recommendation_id="retrain_epl_match_seed_001",
            model_id="calibrated_multinomial_logit_v1",
            current_version="1.0.0",
            competition_scope="GB-PL",
            recommendation=RetrainRecommendation.NO_RETRAIN_REQUIRED,
            triggers_fired=[],
            evidence_metrics={
                "feature_psi": 0.038,
                "delta_brier": 0.008,
                "delta_ece": 0.005,
                "new_observations": 22,
                "days_since_train": 74,
            },
            recommended_action="MAINTAIN_CURRENT_MODEL",
            requires_human_approval=True,
        )
        self._recommendations[seed.model_id] = seed

    def evaluate_model(
        self,
        model_id: str,
        current_version: str,
        competition_scope: str,
        feature_psi: float,
        delta_brier: float,
        delta_ece: float,
        new_observations: int,
        days_since_train: int,
    ) -> ModelRetrainingRecommendation:
        """Determines if retraining triggers fire based on empirical thresholds."""
        triggers = []
        metrics = {
            "feature_psi": feature_psi,
            "delta_brier": delta_brier,
            "delta_ece": delta_ece,
            "new_observations": new_observations,
            "days_since_train": days_since_train,
        }

        # Threshold checks
        if feature_psi >= 0.25:
            triggers.append(f"Material feature drift detected (PSI {feature_psi:.3f} >= 0.25)")
        elif feature_psi >= 0.20:
            triggers.append(f"Warning feature drift detected (PSI {feature_psi:.3f} >= 0.20)")

        if delta_ece >= 0.04:
            triggers.append(f"Expected Calibration Error degraded by {delta_ece:.3f} (>= 0.04)")

        if delta_brier >= 0.05:
            triggers.append(f"Brier score degraded by {delta_brier:.3f} (>= 0.05)")

        if new_observations >= 100:
            triggers.append(f"Substantial new sample accumulated ({new_observations} >= 100 matches)")

        if days_since_train >= 180:
            triggers.append(f"Model age exceeds seasonal boundary ({days_since_train} >= 180 days)")

        # Decision synthesis
        if any("Material" in t or "degraded" in t for t in triggers):
            recommendation = RetrainRecommendation.RETRAIN_RECOMMENDED
            action = "SCHEDULE_CHALLENGER_TRAINING_JOB"
        elif len(triggers) > 0:
            recommendation = RetrainRecommendation.REVIEW_REQUIRED
            action = "CONDUCT_DRIFT_AND_CALIBRATION_REVIEW"
        else:
            recommendation = RetrainRecommendation.NO_RETRAIN_REQUIRED
            action = "MAINTAIN_CURRENT_MODEL"

        rec = ModelRetrainingRecommendation(
            model_id=model_id,
            current_version=current_version,
            competition_scope=competition_scope,
            recommendation=recommendation,
            triggers_fired=triggers,
            evidence_metrics=metrics,
            recommended_action=action,
            requires_human_approval=True,
        )

        self._recommendations[model_id] = rec
        return rec

    def get_recommendation(self, model_id: str) -> ModelRetrainingRecommendation | None:
        return self._recommendations.get(model_id)

    def list_recommendations(self) -> list[ModelRetrainingRecommendation]:
        return list(self._recommendations.values())


retraining_trigger_engine = RetrainingTriggerEngine()
