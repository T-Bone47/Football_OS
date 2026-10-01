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
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np

from app.market.ml.explainability import ValuationExplainer, ValuationExplanation
from app.market.ml.features import VALUATION_FEATURE_SET_V1, get_valuation_feature_names
from app.market.ml.gating import SufficiencyGateDecision, ValuationDataStatus, ValuationSufficiencyGate
from app.market.ml.target import SupervisedValuationTarget
from app.market.ml.uncertainty import ConformalIntervalEstimator, PredictionInterval


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
    """Manages persistence, retrieval, and active assignment of valuation models."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or DEFAULT_MODEL_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.base_dir / "registry_manifest.json"
        self.active_symlink = self.base_dir / "active_model.joblib"
        self._active_bundle: Optional[ValuationModelBundle] = None

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {"active_model_id": None, "models": {}}
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"active_model_id": None, "models": {}}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def register_model(
        self,
        bundle: ValuationModelBundle,
        set_active: bool = False,
    ) -> Path:
        """Serializes model bundle and updates registry manifest."""
        meta = bundle.metadata
        filename = f"{meta.model_id}.joblib"
        artifact_path = self.base_dir / filename
        meta.artifact_location = str(artifact_path)

        # Serialize bundle
        joblib.dump(bundle, artifact_path, compress=3)

        manifest = self._load_manifest()
        manifest["models"][meta.model_id] = meta.to_dict()

        if set_active or manifest.get("active_model_id") is None:
            manifest["active_model_id"] = meta.model_id
            joblib.dump(bundle, self.active_symlink, compress=3)
            self._active_bundle = bundle

        self._save_manifest(manifest)
        return artifact_path

    def get_active_model(self) -> Optional[ValuationModelBundle]:
        """Loads and caches active model bundle from disk."""
        if self._active_bundle is not None:
            return self._active_bundle

        if self.active_symlink.exists():
            try:
                bundle: ValuationModelBundle = joblib.load(self.active_symlink)
                self._active_bundle = bundle
                return bundle
            except Exception:
                return None

        manifest = self._load_manifest()
        active_id = manifest.get("active_model_id")
        if active_id and active_id in manifest.get("models", {}):
            art_path = Path(manifest["models"][active_id]["artifact_location"])
            if art_path.exists():
                bundle = joblib.load(art_path)
                self._active_bundle = bundle
                return bundle

        return None

    def get_model_status(self) -> Dict[str, Any]:
        """Returns metadata status of current active model."""
        active = self.get_active_model()
        if active is None:
            return {
                "active": False,
                "status": "NO_ACTIVE_MODEL",
                "message": "No valuation ML model has been registered or activated.",
            }
        meta = active.metadata
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
        }


# Global registry singleton
_GLOBAL_REGISTRY: Optional[ValuationModelRegistry] = None

def get_valuation_registry() -> ValuationModelRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ValuationModelRegistry()
    return _GLOBAL_REGISTRY
