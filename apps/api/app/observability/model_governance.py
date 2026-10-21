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
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
    status: str  # MODEL_VALIDATED | MODEL_CANDIDATE_ONLY | MODEL_RELEASE_BLOCKED | MODEL_UNVALIDATED
    provenance: str
    description: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_spec_hash(spec_str: str) -> str:
    """Generates deterministic SHA-256 hash for model specifications."""
    return hashlib.sha256(spec_str.encode("utf-8")).hexdigest()[:16]


_VALUATION_DIR = Path(__file__).resolve().parents[4] / "data" / "models" / "valuation"


def _unvalidated(name: str, version: str, feature_set: str, provenance: str, description: str) -> ModelGovernanceRecord:
    """A component with NO recorded validation run and NO trained artifact. Nothing is claimed for it."""
    return ModelGovernanceRecord(
        name=name,
        version=version,
        feature_set=feature_set,
        training_cutoff="UNKNOWN",
        validation_period="NOT_VALIDATED",
        metrics={},
        calibration={},
        artifact_hash="NO_ARTIFACT",
        status="MODEL_UNVALIDATED",
        provenance=provenance,
        description=description,
        created_at="UNKNOWN",
    )


def _valuation_ml_record() -> ModelGovernanceRecord:
    """Derived from the real registry manifest (status, test metrics and pinned SHA-256)."""
    try:
        manifest = json.loads((_VALUATION_DIR / "registry_manifest.json").read_text(encoding="utf-8"))
        entry = manifest["models"][manifest["active_model_id"]]
    except (OSError, ValueError, KeyError, TypeError):
        return _unvalidated(
            "valuation_model", "VALUATION_ML_V1", "VALUATION_FEATURE_SET_V1", "app.market.ml",
            "No valuation artifact is registered.",
        )
    return ModelGovernanceRecord(
        name="valuation_model",
        version=entry.get("model_version", "VALUATION_ML_V1"),
        feature_set=entry.get("feature_set_version", "UNKNOWN"),
        training_cutoff=(entry.get("training_period") or ["", "UNKNOWN"])[-1] or "UNKNOWN",
        validation_period=" to ".join(entry.get("validation_period") or []) or "UNKNOWN",
        metrics={k: float(v) for k, v in (entry.get("test_metrics") or {}).items()},
        calibration=dict(entry.get("release_gate_evaluation") or {}),
        artifact_hash=entry.get("artifact_sha256") or "UNPINNED",
        status=entry.get("status", "UNKNOWN"),
        provenance="data/models/valuation/registry_manifest.json",
        description="LightGBM transfer-fee model. " + "; ".join(entry.get("blocking_reasons") or []),
        created_at=entry.get("created_at", "UNKNOWN"),
    )


class ModelGovernanceRegistry:
    """Central authority auditing and controlling all analytical model references.

    Records are derived from real evidence. Components without a recorded validation run are
    MODEL_UNVALIDATED and are refused by verify_inference_eligibility().
    """

    def __init__(self) -> None:
        self._registry: dict[tuple[str, str], ModelGovernanceRecord] = {}
        self._bootstrap_authoritative_models()

    def _bootstrap_authoritative_models(self) -> None:
        self.register(_valuation_ml_record())
        self.register(_unvalidated(
            "valuation_model", "GBR_ValuationEngine_v1.0", "baseline_features", "app.market.valuation",
            "Deterministic baseline valuation (age curve x cohort median); not a trained model.",
        ))
        self.register(_unvalidated(
            "match_prediction_engine", "BivariatePoisson_v1", "match_features_v1", "app.prediction",
            "No trained match-prediction artifact or validation run exists in this repository.",
        ))
        self.register(_unvalidated(
            "tactical_fit_engine", "TacticalFitCalculator_v1.0", "tactical_features_v1", "app.market.tactical",
            "Rule-based calculator; no validation study recorded.",
        ))
        self.register(_unvalidated(
            "risk_engine", "TransferRiskEngine_v2", "risk_features_v2", "app.market.risk.TransferRiskEngine",
            "Rule-based risk decomposition; no validation study recorded.",
        ))
        self.register(_unvalidated(
            "similarity_engine", "RoleSimilarity_v2", "similarity_features_v2", "app.roles.similarity.PlayerSimilarityEngine",
            "Weighted cosine similarity; no validation study recorded.",
        ))

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
