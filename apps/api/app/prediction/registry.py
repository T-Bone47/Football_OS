"""Model Registry & Validation Lifecycle Engine (Phase 6.21).

Manages model versions, verified backtest performance, calibration parameters,
and release gate verification. Only models meeting strict temporal and leakage validation
criteria are marked as MODEL_VALIDATED and allowed for active inference.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.prediction.schemas import ModelStatusResponse

MODEL_REGISTRY_VERSION = "registry_v1"


_REPO_ROOT = Path(__file__).resolve().parents[4]


class ModelMetadata(BaseModel):
    """Registry record for a match-prediction model.

    Everything that would constitute validation evidence is optional and defaults to "unknown" (None / {}): counts,
    periods, metrics, calibration and the temporal/leakage flags. A record may only claim MODEL_VALIDATED when the
    registry can verify the evidence file named by evidence_ref against evidence_sha256 (PredictionModelRegistry.register).
    """
    model_config = ConfigDict(extra="ignore")

    model_id: str
    model_version: str
    feature_version: str
    dataset_version: str | None = None
    algorithm: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    training_matches_count: int | None = None
    validation_matches_count: int | None = None
    test_matches_count: int | None = None
    training_period: str | None = None
    validation_period: str | None = None
    test_period: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    calibration_method: str = "NONE"
    calibration_params: dict[str, Any] = Field(default_factory=dict)
    status: str = "MODEL_UNVALIDATED"  # MODEL_VALIDATED (evidence required), MODEL_CANDIDATE, MODEL_UNVALIDATED, MODEL_RELEASE_BLOCKED
    temporal_validation_passed: bool | None = None
    leakage_tests_passed: bool | None = None
    evidence_ref: str | None = None  # repo-relative path of the validation report that backs status and metrics
    evidence_sha256: str | None = None
    random_seed: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PredictionModelRegistry:
    """In-memory model registry for football match prediction models. Statuses come from evidence."""

    def __init__(self, evidence_root: Path | None = None) -> None:
        self._root = (evidence_root or _REPO_ROOT).resolve()
        self._models: dict[str, ModelMetadata] = {}
        self._active_model_id: str | None = None
        self._register_declared_specifications()

    def _register_declared_specifications(self) -> None:
        """Registers the algorithms this code implements as UNVALIDATED specifications.

        There is no fitted artifact, no dataset manifest and no recorded evaluation for any of them, so no metric,
        count, period, calibration or validation flag is claimed. (The previous version typed in MODEL_VALIDATED,
        log-loss 0.9418, 1,520/388/400 matches, 2026-08..09 periods and passed validation flags.)
        """
        self.register(ModelMetadata(
            model_id="baseline_class_frequency_v1",
            model_version="1.0.0",
            feature_version="match_prediction_v1",
            algorithm="Fixed class prior (typical top-flight outcome frequencies, not derived from ingested data)",
            hyperparameters={"p_home": 0.442, "p_draw": 0.260, "p_away": 0.298},
        ))
        self.register(ModelMetadata(
            model_id="baseline_elo_deterministic_v1",
            model_version="1.0.0",
            feature_version="match_prediction_v1",
            algorithm="Deterministic Elo differential",
            hyperparameters={"k_factor": 20.0, "home_advantage": 65.0},
        ))
        self.register(ModelMetadata(
            model_id="calibrated_multinomial_logit_v1",
            model_version="1.2.0",
            feature_version="match_prediction_v1",
            algorithm="Multinomial logit ensemble with hand-set weights (not fitted to a dataset; temperature is not fitted calibration)",
            hyperparameters={
                "w_home": 0.38, "w_elo": 0.85, "w_points": 0.65, "w_matchup": 0.50, "w_rest": 0.15,
                "temperature": 1.06, "goal_model": "bivariate_poisson_dixon_coles",
            },
        ), set_active=True)

    def evidence_problem(self, model: ModelMetadata) -> str | None:
        """Why this record may NOT claim MODEL_VALIDATED, or None when its evidence verifies."""
        if not model.evidence_ref or not model.evidence_sha256:
            return "no evidence_ref / evidence_sha256"
        path = (self._root / model.evidence_ref).resolve()
        if self._root not in path.parents:
            return "evidence_ref escapes the evidence root"
        if not path.is_file():
            return "evidence file not found"
        if _sha256(path) != model.evidence_sha256.lower():
            return "evidence hash mismatch"
        if not model.metrics:
            return "no metrics recorded"
        if model.temporal_validation_passed is not True or model.leakage_tests_passed is not True:
            return "temporal and leakage validation not established"
        return None

    def register(self, model: ModelMetadata, set_active: bool = False) -> None:
        """Registers a model record. MODEL_VALIDATED is refused unless its evidence verifies."""
        if model.status == "MODEL_VALIDATED":
            problem = self.evidence_problem(model)
            if problem:
                raise ValueError(f"MODEL_VALIDATED requires verifiable evidence: {problem}")
        self._models[model.model_id] = model
        if set_active:
            self._active_model_id = model.model_id

    def verify_evidence(self, model_id: str) -> bool:
        """Re-checks a registered record's evidence now (it may have been altered after registration)."""
        model = self._models.get(model_id)
        return model is not None and self.evidence_problem(model) is None

    def get_model(self, model_id: str) -> ModelMetadata | None:
        """Retrieves a model by its ID."""
        return self._models.get(model_id)

    def get_active_model(self) -> ModelMetadata:
        """Retrieves the active model designated for production predictions."""
        if not self._active_model_id or self._active_model_id not in self._models:
            raise RuntimeError("No active model designated in PredictionModelRegistry")
        return self._models[self._active_model_id]

    def list_models(self) -> list[ModelMetadata]:
        """Lists all registered models."""
        return list(self._models.values())

    def get_status_response(self) -> ModelStatusResponse:
        """Public status contract for the active model; whatever evidence is missing is None, never 0."""
        active = self.get_active_model()
        return ModelStatusResponse(
            active_model_id=active.model_id,
            model_version=active.model_version,
            feature_version=active.feature_version,
            algorithm=active.algorithm,
            training_matches_count=active.training_matches_count,
            validation_matches_count=active.validation_matches_count,
            log_loss=active.metrics.get("log_loss"),
            brier_score=active.metrics.get("brier_score"),
            accuracy=active.metrics.get("accuracy"),
            macro_f1=active.metrics.get("macro_f1"),
            expected_calibration_error=active.metrics.get("ece"),
            calibration_method=active.calibration_method,
            status=active.status,
            temporal_validation_passed=active.temporal_validation_passed,
            leakage_tests_passed=active.leakage_tests_passed,
            registered_at=active.created_at,
        )


# Global singleton instance
model_registry = PredictionModelRegistry()
