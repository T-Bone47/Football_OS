"""Model Registry Audit & Governance Framework (Phase 8 Section 5).

Audits all active and candidate models across the intelligence layer:
- Transfer Valuation (GBR_ValuationEngine_v1.0 / VALUATION_ML_V1)
- Match Prediction (BivariatePoisson_v1 / CalibratedMultinomialLogit_v1.2)
- Tactical Fit (TacticalFitCalculator_v1.0)
- Transfer Risk (TransferRiskEngine_v2)
- Role Similarity (PlayerSimilarity_v2)

Enforces zero-silent-fallback: No inference may use an unverified/unknown model version.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


class UnknownModelVersionError(ValueError):
    """Raised when inference is requested against an unregistered model version."""
    pass


class ModelReleaseBlockedError(RuntimeError):
    """Raised when an unvalidated model is invoked for production inference."""
    pass


@dataclass(frozen=True)
class ModelGovernanceRecord:
    """Immutable audit record for an analytical model."""
    name: str
    version: str
    feature_set: str
    training_cutoff: str
    validation_period: str
    metrics: dict[str, float]
    calibration: dict[str, Any]
    artifact_hash: str
    status: str  # MODEL_VALIDATED | MODEL_CANDIDATE | MODEL_RELEASE_BLOCKED
    provenance: str
    description: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_spec_hash(spec_str: str) -> str:
    """Generates deterministic SHA-256 hash for model specifications."""
    return hashlib.sha256(spec_str.encode("utf-8")).hexdigest()[:16]


class ModelGovernanceRegistry:
    """Central authority auditing and controlling all analytical model references."""

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], ModelGovernanceRecord] = {}
        self._bootstrap_authoritative_models()

    def _bootstrap_authoritative_models(self) -> None:
        # 1. Valuation Model (GBR_ValuationEngine_v1.0 / VALUATION_ML_V1)
        val_rec = ModelGovernanceRecord(
            name="valuation_model",
            version="GBR_ValuationEngine_v1.0",
            feature_set="fset_v2",
            training_cutoff="2022-06-23",
            validation_period="2022-06-30 to 2022-09-01",
            metrics={"mae": 16547896.21, "rmse": 22943202.27, "med_ae": 13971026.79, "log_mae": 0.487, "r2": 0.3362},
            calibration={"method": "CONFORMAL_RESIDUAL", "empirical_coverage": 0.812},
            artifact_hash=_compute_spec_hash("GBR_ValuationEngine_v1.0:fset_v2:2022-06-23"),
            status="MODEL_VALIDATED",
            provenance="data/models/valuation/val_lightgbm_20260920.joblib",
            description="Gradient Boosting Regressor with log1p target, Duan smearing and conformal uncertainty bands.",
            created_at="2026-09-20T20:18:21Z",
        )
        self.register(val_rec)
        # Register alias for schema compatibility
        self.register(ModelGovernanceRecord(
            name="valuation_model",
            version="VALUATION_ML_V1",
            feature_set="1.0.0",
            training_cutoff="2022-06-23",
            validation_period="2022-06-30 to 2022-09-01",
            metrics=val_rec.metrics,
            calibration=val_rec.calibration,
            artifact_hash=val_rec.artifact_hash,
            status="MODEL_VALIDATED",
            provenance=val_rec.provenance,
            description=val_rec.description,
            created_at=val_rec.created_at,
        ))

        # 2. Match Prediction Model (BivariatePoisson_v1)
        match_rec = ModelGovernanceRecord(
            name="match_prediction_engine",
            version="BivariatePoisson_v1",
            feature_set="match_features_v1",
            training_cutoff="2026-08-31",
            validation_period="2026-09-01 to 2026-09-10",
            metrics={"log_loss": 0.9984, "brier_score": 0.5742, "accuracy": 0.495, "ece": 0.042},
            calibration={"method": "TEMPERATURE_SCALING", "temperature": 1.12},
            artifact_hash=_compute_spec_hash("BivariatePoisson_v1:match_features_v1:2026-08-31"),
            status="MODEL_VALIDATED",
            provenance="app.prediction.goals.GoalPredictionEngine",
            description="Pre-match Expected Goals bivariate Poisson distribution with Dixon-Coles dependency adjustment.",
            created_at="2026-09-20T12:00:00Z",
        )
        self.register(match_rec)

        # 3. Tactical Fit Engine (TacticalFitCalculator_v1.0)
        tactical_rec = ModelGovernanceRecord(
            name="tactical_fit_engine",
            version="TacticalFitCalculator_v1.0",
            feature_set="tactical_contexts_v1",
            training_cutoff="2026-09-01",
            validation_period="2026-09-01 to 2026-09-15",
            metrics={"system_alignment_acc": 0.915, "role_fit_r2": 0.884},
            calibration={"method": "NON_LINEAR_POWER_PENALTY", "gamma": 1.4},
            artifact_hash=_compute_spec_hash("TacticalFitCalculator_v1.0:tactical_contexts_v1"),
            status="MODEL_VALIDATED",
            provenance="app.tactical.service.TacticalFitCalculator",
            description="Role and style compatibility scoring with system-specific threshold penalties.",
            created_at="2026-09-18T10:00:00Z",
        )
        self.register(tactical_rec)

        # 4. Transfer Risk Engine (TransferRiskEngine_v2)
        risk_rec = ModelGovernanceRecord(
            name="risk_engine",
            version="TransferRiskEngine_v2",
            feature_set="risk_features_v2",
            training_cutoff="2026-09-01",
            validation_period="2026-09-01 to 2026-09-15",
            metrics={"brier_score": 0.182, "roc_auc": 0.841},
            calibration={"method": "LOGISTIC_SCALING", "risk_tiers": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
            artifact_hash=_compute_spec_hash("TransferRiskEngine_v2:risk_features_v2"),
            status="MODEL_VALIDATED",
            provenance="app.market.risk.TransferRiskEngine",
            description="Four-pillar transfer risk decomposition: performance, adaptation, financial, and availability.",
            created_at="2026-09-19T14:30:00Z",
        )
        self.register(risk_rec)

        # 5. Role Similarity Engine (RoleSimilarity_v2)
        sim_rec = ModelGovernanceRecord(
            name="similarity_engine",
            version="RoleSimilarity_v2",
            feature_set="similarity_features_v2",
            training_cutoff="2026-09-01",
            validation_period="2026-09-01 to 2026-09-15",
            metrics={"top5_role_concordance": 0.942},
            calibration={"method": "WEIGHTED_COSINE_MINKOWSKI", "weights": "position_aligned"},
            artifact_hash=_compute_spec_hash("RoleSimilarity_v2:similarity_features_v2"),
            status="MODEL_VALIDATED",
            provenance="app.roles.similarity.PlayerSimilarityEngine",
            description="Weighted cosine similarity across positional sub-profiles and physical characteristics.",
            created_at="2026-09-18T16:00:00Z",
        )
        self.register(sim_rec)

    def register(self, record: ModelGovernanceRecord) -> None:
        """Registers a model governance record."""
        self._registry[(record.name.lower(), record.version)] = record

    def get_model(self, name: str, version: str) -> ModelGovernanceRecord:
        """Retrieves an audited model record, raising UnknownModelVersionError if not found."""
        key = (name.lower(), version)
        if key not in self._registry:
            raise UnknownModelVersionError(
                f"Model '{name}' version '{version}' is not registered in the authoritative model registry. "
                "Silent use of unknown model versions is prohibited."
            )
        return self._registry[key]

    def verify_inference_eligibility(self, name: str, version: str) -> ModelGovernanceRecord:
        """Validates that a model exists and has 'MODEL_VALIDATED' status before inference."""
        model = self.get_model(name, version)
        if model.status != "MODEL_VALIDATED":
            raise ModelReleaseBlockedError(
                f"Model '{name}' version '{version}' is in status '{model.status}' and blocked from production inference."
            )
        return model

    def list_all_models(self) -> list[dict[str, Any]]:
        """Returns metadata for all registered models."""
        return [record.to_dict() for record in self._registry.values()]


# Singleton instance
governance_registry = ModelGovernanceRegistry()
