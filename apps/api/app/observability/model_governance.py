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
from dataclasses import asdict, dataclass
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

    # Phase 18 (N2): this registry used to bootstrap six models as
    # MODEL_VALIDATED with literal metrics and no artifacts behind them. It now
    # starts empty. The authoritative registry is ops_model_registry
    # (PostgreSQL); see docs/PHASE_18_MODEL_SERVING.md.

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
