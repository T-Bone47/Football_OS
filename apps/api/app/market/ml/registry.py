"""Phase 4.2: Transfer Valuation ML Engine — Model Registry & Lifecycle Manager.

Manages serialized model artifacts, training/validation/test lineage, hyperparameter
provenance, release gate verification, and production inference execution.

Release Gate Policy:
--------------------
A model artifact cannot transition to 'MODEL_VALIDATED' or become ACTIVE unless:
1. Chronological test set evaluation beats all baseline benchmarks.
2. Prediction intervals achieve >=70% empirical coverage on unseen test split.
3. Feature leakage tests pass without error.
4. Reproducibility test produces bit-for-bit identical predictions.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np

from app.market.ml.artifact_integrity import ArtifactIntegrityError, artifact_path, sha256_file, verify_artifact
from app.market.ml.explainability import ValuationExplainer, ValuationExplanation
from app.market.ml.features import VALUATION_FEATURE_SET_V1, get_valuation_feature_names
from app.market.ml.gating import SufficiencyGateDecision, ValuationDataStatus, ValuationSufficiencyGate
from app.market.ml.target import SupervisedValuationTarget
from app.market.ml.uncertainty import ConformalIntervalEstimator, PredictionInterval


logger = logging.getLogger(__name__)

# Default location for valuation model artifacts
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[5] / "data" / "models" / "valuation"


@dataclass
class ModelRegistryMetadata:
    """Complete metadata and provenance manifest for a valuation model version."""
    model_id: str
    model_version: str
    dataset_version: str
    feature_set_version: str
    algorithm: str
    training_period: Tuple[str, str]
    validation_period: Tuple[str, str]
    test_period: Tuple[str, str]
    hyperparameters: Dict[str, Any]
    train_metrics: Dict[str, float]
    val_metrics: Dict[str, float]
    test_metrics: Dict[str, float]
    artifact_location: str
    created_at: str
    code_version: str = "v4.2.0"
    random_seed: int = 42
    status: str = "MODEL_CANDIDATE_ONLY"  # MODEL_CANDIDATE_ONLY | MODEL_VALIDATED | MODEL_RELEASE_BLOCKED
    release_gate_checklist: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "dataset_version": self.dataset_version,
            "feature_set_version": self.feature_set_version,
            "algorithm": self.algorithm,
            "training_period": list(self.training_period),
            "validation_period": list(self.validation_period),
            "test_period": list(self.test_period),
            "hyperparameters": self.hyperparameters,
            "train_metrics": {k: round(v, 4) for k, v in self.train_metrics.items()},
            "val_metrics": {k: round(v, 4) for k, v in self.val_metrics.items()},
            "test_metrics": {k: round(v, 4) for k, v in self.test_metrics.items()},
            "artifact_location": self.artifact_location,
            "created_at": self.created_at,
            "code_version": self.code_version,
            "random_seed": self.random_seed,
            "status": self.status,
            "release_gate_checklist": self.release_gate_checklist,
        }


@dataclass
class ValuationInferenceResult:
    """Full inference payload returned by the active valuation engine."""
    player_id: str
    as_of: str
    estimated_value_eur: float
    lower_bound_eur: float
    upper_bound_eur: float
    uncertainty_eur: float
    data_status: ValuationDataStatus
    model_version: str
    feature_version: str
    explanation: ValuationExplanation
    gate_decision: SufficiencyGateDecision

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self.player_id,
            "as_of": self.as_of,
            "estimated_value_eur": round(self.estimated_value_eur, 2),
            "lower_bound_eur": round(self.lower_bound_eur, 2),
            "upper_bound_eur": round(self.upper_bound_eur, 2),
            "uncertainty_eur": round(self.uncertainty_eur, 2),
            "data_status": self.data_status.value,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "explanation": self.explanation.to_dict(),
            "gate_decision": self.gate_decision.to_dict(),
        }


class ValuationModelBundle:
    """Self-contained, reproducible production model artifact bundle."""

    def __init__(
        self,
        model: Any,
        target_transformer: SupervisedValuationTarget,
        uncertainty_estimator: ConformalIntervalEstimator,
        sufficiency_gate: ValuationSufficiencyGate,
        explainer: ValuationExplainer,
        metadata: ModelRegistryMetadata,
        feature_names: Optional[List[str]] = None,
    ) -> None:
        self.model = model
        self.target_transformer = target_transformer
        self.uncertainty_estimator = uncertainty_estimator
        self.sufficiency_gate = sufficiency_gate
        self.explainer = explainer
        self.metadata = metadata
        self.feature_names = feature_names or get_valuation_feature_names()

    def predict_player(
        self,
        player_id: str,
        features: np.ndarray,
        as_of: str,
        minutes_played: Optional[float] = None,
        age: Optional[float] = None,
        position_group: Optional[str] = None,
        null_count: int = 0,
    ) -> ValuationInferenceResult:
        """Executes full leakage-safe inference pipeline with sufficiency gating and uncertainty."""
        if features.ndim == 1:
            feat_2d = features.reshape(1, -1)
        else:
            feat_2d = features

        # 1. Evaluate inference sufficiency & OOD
        gate = self.sufficiency_gate.evaluate(
            features=feat_2d[0],
            minutes_played=minutes_played,
            null_count=null_count,
            age=age,
        )

        if not gate.can_predict:
            # Cannot provide an ungrounded prediction
            empty_exp = ValuationExplanation(
                player_id=player_id,
                model_version=self.metadata.model_version,
                feature_version=self.metadata.feature_set_version,
                base_value_log=0.0,
                prediction_log=0.0,
                top_positive_contributors=[],
                top_negative_contributors=[],
                method="INSUFFICIENT_DATA_BYPASS",
            )
            return ValuationInferenceResult(
                player_id=player_id,
                as_of=as_of,
                estimated_value_eur=0.0,
                lower_bound_eur=0.0,
                upper_bound_eur=0.0,
                uncertainty_eur=0.0,
                data_status=gate.status,
                model_version=self.metadata.model_version,
                feature_version=self.metadata.feature_set_version,
                explanation=empty_exp,
                gate_decision=gate,
            )

        # 2. Point Prediction in log space
        pred_log = float(self.model.predict(feat_2d)[0])

        # 3. Inverse transform with smearing factor
        pred_eur = float(self.target_transformer.inverse_transform(np.array([pred_log]))[0])

        # 4. Uncertainty prediction interval
        interval = self.uncertainty_estimator.predict_interval(
            pred_log=pred_log,
            pred_eur=pred_eur,
            position_group=position_group,
        )

        # 5. Deterministic explainability
        explanation = self.explainer.explain_instance(
            player_id=player_id,
            features=feat_2d[0],
        )

        return ValuationInferenceResult(
            player_id=player_id,
            as_of=as_of,
            estimated_value_eur=interval.estimated_value_eur,
            lower_bound_eur=interval.lower_bound_eur,
            upper_bound_eur=interval.upper_bound_eur,
            uncertainty_eur=interval.uncertainty_eur,
            data_status=gate.status,
            model_version=self.metadata.model_version,
            feature_version=self.metadata.feature_set_version,
            explanation=explanation,
            gate_decision=gate,
        )


class ValuationModelRegistry:
    """Manages persistence, retrieval, and active assignment of valuation models.

    The manifest is the governance record (status, release-gate evaluation, pinned SHA-256); the
    pickled bundle is an immutable training-time artifact. A bundle is only unpickled after its
    bytes match the pinned hash, because unpickling executes code.
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or DEFAULT_MODEL_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.base_dir / "registry_manifest.json"
        self._active_bundle: Optional[ValuationModelBundle] = None
        self.last_load_error: Optional[str] = None

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"active_model_id": None, "models": {}}
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("valuation registry manifest is unreadable")
            return {"active_model_id": None, "models": {}}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def register_model(
        self,
        bundle: ValuationModelBundle,
        set_active: bool = False,
    ) -> Path:
        """Serializes the bundle, pins its SHA-256 in the manifest, and records it.

        A model is auto-activated only when nothing is active yet AND it is MODEL_VALIDATED;
        an unvalidated candidate never becomes active implicitly.
        """
        meta = bundle.metadata
        filename = f"{meta.model_id}.joblib"
        artifact_path = self.base_dir / filename
        meta.artifact_location = filename  # relative to the registry directory (portable)

        joblib.dump(bundle, artifact_path, compress=3)

        manifest = self._load_manifest()
        entry = meta.to_dict()
        entry["artifact_sha256"] = sha256_file(artifact_path)
        manifest["models"][meta.model_id] = entry

        auto_activate = manifest.get("active_model_id") is None and meta.status == "MODEL_VALIDATED"
        if set_active or auto_activate:
            manifest["active_model_id"] = meta.model_id
            self._active_bundle = bundle

        self._save_manifest(manifest)
        return artifact_path

    def active_manifest_entry(self) -> Dict[str, Any]:
        manifest = self._load_manifest()
        active_id = manifest.get("active_model_id")
        entry = manifest.get("models", {}).get(active_id) if active_id else None
        if not entry:
            raise ArtifactIntegrityError("NO_ACTIVE_MODEL", "no valuation model is registered as active")
        return entry

    def load_active_or_raise(self) -> ValuationModelBundle:
        """Hash-verified load of the active bundle. Raises ArtifactIntegrityError (fail closed)."""
        if self._active_bundle is not None:
            return self._active_bundle
        entry = self.active_manifest_entry()
        path = artifact_path(self.base_dir, entry["model_id"])
        verify_artifact(path, entry.get("artifact_sha256"))  # BEFORE joblib.load
        try:
            bundle: ValuationModelBundle = joblib.load(path)
        except Exception as exc:  # noqa: BLE001 - missing optional dep, version skew, corrupt pickle
            raise ArtifactIntegrityError("ARTIFACT_UNLOADABLE", type(exc).__name__) from exc
        bundle.metadata.status = entry.get("status", bundle.metadata.status)
        bundle.metadata.release_gate_checklist = dict(entry.get("release_gate_checklist", {}))
        self._active_bundle = bundle
        return bundle

    def set_active_model(self, model_id: str) -> Dict[str, Any]:
        """Human-governed promotion: only a registered, MODEL_VALIDATED, hash-verified model."""
        entry = self._load_manifest().get("models", {}).get(model_id)
        if not entry:
            raise ArtifactIntegrityError("MODEL_NOT_REGISTERED", f"'{model_id}' is not in the registry")
        if entry.get("status") != "MODEL_VALIDATED":
            raise ArtifactIntegrityError("MODEL_NOT_VALIDATED", f"status is {entry.get('status')}")
        verify_artifact(artifact_path(self.base_dir, model_id), entry.get("artifact_sha256"))
        manifest = self._load_manifest()
        manifest["active_model_id"] = model_id
        self._save_manifest(manifest)
        self._active_bundle = None
        return entry

    def get_active_model(self) -> Optional[ValuationModelBundle]:
        """Active bundle, or None (with last_load_error set) when it cannot be served safely."""
        try:
            bundle = self.load_active_or_raise()
            self.last_load_error = None
            return bundle
        except ArtifactIntegrityError as exc:
            self.last_load_error = exc.code
            if exc.code != "NO_ACTIVE_MODEL":
                logger.error("valuation model unavailable: %s", exc)
            return None

    def get_model_status(self) -> Dict[str, Any]:
        """Returns metadata status of current active model."""
        active = self.get_active_model()
        if active is None:
            code = self.last_load_error or "NO_ACTIVE_MODEL"
            return {
                "active": False,
                "status": "NO_ACTIVE_MODEL" if code == "NO_ACTIVE_MODEL" else "ARTIFACT_UNAVAILABLE",
                "reason": code,
                "message": (
                    "No valuation ML model has been registered or activated."
                    if code == "NO_ACTIVE_MODEL"
                    else f"The active valuation model cannot be served safely ({code})."
                ),
            }
        meta = active.metadata
        entry = self.active_manifest_entry()
        return {
            "active": True,
            "status": meta.status,
            "model_id": meta.model_id,
            "model_version": meta.model_version,
            "dataset_version": meta.dataset_version,
            "feature_set_version": meta.feature_set_version,
            "algorithm": meta.algorithm,
            "created_at": meta.created_at,
            "test_metrics": meta.test_metrics,
            "release_gate_checklist": meta.release_gate_checklist,
            "release_gate_evaluation": entry.get("release_gate_evaluation", {}),
            "blocking_reasons": entry.get("blocking_reasons", []),
            "artifact_sha256": entry.get("artifact_sha256"),
        }


# Global registry singleton
_GLOBAL_REGISTRY: Optional[ValuationModelRegistry] = None

def get_valuation_registry() -> ValuationModelRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ValuationModelRegistry()
    return _GLOBAL_REGISTRY
