"""Production model serving for Phase 16 - serves ONLY real, hash-verified artifacts, else refuses.

History: the previous engine seeded two fictional model profiles ("valuation_ml_v1:1.2.0" and a
shadow "valuation_ml_v2_spline:2.0.0-rc1", neither of which had an artifact) and answered every
request with ``base_metric * 1.05``. Nothing here fabricates a number. A request is either served
by the registry's active artifact (SHA-256 verified before unpickling, feature schema checked,
sufficiency/OOD gated) or refused with a machine-readable reason.

Fail-closed conditions: no artifact, hash mismatch/unpinned, model not MODEL_VALIDATED, competition
not declared supported, feature-schema mismatch, insufficient/out-of-distribution data.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import Counter, deque
from datetime import date, datetime, timezone
from typing import Any, Mapping

import numpy as np
from pydantic import BaseModel, Field

from app.market.ml.artifact_integrity import (
    ArtifactIntegrityError,
    artifact_path,
    validate_feature_mapping,
    verify_artifact,
)
from app.phase16 import DeploymentState

SUPPORTED_DOMAINS = ("valuation",)  # the only domain with a trained artifact in this repository


class ModelUnavailableError(Exception):
    """The request cannot be served truthfully; `code` is stable and machine-readable."""

    def __init__(self, code: str, detail: str, http_status: int = 503) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.http_status = http_status


class ModelServingProfile(BaseModel):
    model_id: str
    model_version: str
    feature_set_version: str
    dataset_version: str
    calculation_version: str = "calc_v16.0"
    training_window: dict[str, str]
    validation_window: dict[str, str]
    supported_competitions: list[str] | None = None  # None = never declared => serving blocked
    supported_positions: list[str] = Field(default_factory=list)
    calibration_state: str  # CALIBRATED | CALIBRATION_FAILED | NOT_EVALUATED
    ood_policy: str = "BLOCK_INFERENCE"
    deployment_state: DeploymentState
    canary_weight_percent: float = 0.0
    release_status: str
    integrity_status: str  # VERIFIED or an ArtifactIntegrityError code
    artifact_sha256: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


class PredictionServingResponse(BaseModel):
    prediction_id: str
    model_id: str
    model_version: str
    feature_version: str
    dataset_version: str
    calculation_version: str
    deployment_mode: str
    input_digest: str
    predicted_value: float
    confidence_interval: tuple[float, float]
    is_ood: bool
    data_status: str
    artifact_sha256: str
    model_release_status: str
    missing_feature_count: int
    served_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InferenceTelemetry:
    """Process-local counters. Honest about scope: lost on restart, not shared across workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._since = datetime.now(timezone.utc).isoformat()
        self._served = 0
        self._refusals: Counter[str] = Counter()
        self._latencies_ms: deque[float] = deque(maxlen=1000)

    def record_served(self, latency_ms: float) -> None:
        with self._lock:
            self._served += 1
            self._latencies_ms.append(latency_ms)

    def record_refusal(self, code: str) -> None:
        with self._lock:
            self._refusals[code] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            lat = sorted(self._latencies_ms)
            refusals = dict(self._refusals)
            served = self._served
        total = served + sum(refusals.values())
        return {
            "scope": "PROCESS_LOCAL_SINCE_START",
            "since": self._since,
            "requests": total,
            "served": served,
            "refused": sum(refusals.values()),
            "refusals_by_reason": refusals,
            "failure_rate": (sum(refusals.values()) / total) if total else None,
            "latency_ms_p50": lat[len(lat) // 2] if lat else None,
            "latency_ms_p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None,
        }


def _calibration_state(evaluation: Mapping[str, str]) -> str:
    coverage = [evaluation.get("interval_coverage_overall"), evaluation.get("interval_coverage_by_group")]
    if "FAIL" in coverage:
        return "CALIBRATION_FAILED"
    return "CALIBRATED" if all(c == "PASS" for c in coverage) else "NOT_EVALUATED"


def _digest(features: Mapping[str, Any]) -> str:
    canonical = {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in sorted(features.items())}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class ModelServingEngine:
    def __init__(self, registry: Any | None = None) -> None:
        self._registry = registry
        self.telemetry = InferenceTelemetry()

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from app.market.ml.registry import get_valuation_registry  # lazy: imports the ML stack

            self._registry = get_valuation_registry()
        return self._registry

    # ---- inventory (derived from the registry, never seeded) ---------------------------------
    def list_models(self) -> list[ModelServingProfile]:
        manifest = self.registry._load_manifest()
        active_id = manifest.get("active_model_id")
        profiles: list[ModelServingProfile] = []
        for model_id, entry in manifest.get("models", {}).items():
            try:
                sha = verify_artifact(artifact_path(self.registry.base_dir, model_id), entry.get("artifact_sha256"))
                integrity = "VERIFIED"
            except ArtifactIntegrityError as exc:
                sha, integrity = entry.get("artifact_sha256"), exc.code
            status = entry.get("status", "UNKNOWN")
            evaluation = entry.get("release_gate_evaluation", {})
            serving = model_id == active_id and integrity == "VERIFIED" and status == "MODEL_VALIDATED"
            tr, va = entry.get("training_period", ["", ""]), entry.get("validation_period", ["", ""])
            profiles.append(
                ModelServingProfile(
                    model_id=model_id,
                    model_version=entry.get("model_version", "UNKNOWN"),
                    feature_set_version=entry.get("feature_set_version", "UNKNOWN"),
                    dataset_version=entry.get("dataset_version", "UNKNOWN"),
                    training_window={"start": tr[0], "end": tr[1]},
                    validation_window={"start": va[0], "end": va[1]},
                    supported_competitions=entry.get("supported_competitions"),
                    calibration_state=_calibration_state(evaluation),
                    deployment_state=DeploymentState.ACTIVE if serving else DeploymentState.REGISTERED,
                    release_status=status,
                    integrity_status=integrity,
                    artifact_sha256=sha,
                    blocking_reasons=list(entry.get("blocking_reasons", [])),
                )
            )
        return profiles

    def get_model(self, model_key: str) -> ModelServingProfile:
        for profile in self.list_models():
            if profile.model_id == model_key:
                return profile
        raise KeyError(f"Model profile '{model_key}' not found.")

    def promote(self, domain: str, model_id: str) -> ModelServingProfile:
        """Human-governed promotion (caller must hold model:promote). Never promotes an unvalidated model."""
        if domain not in SUPPORTED_DOMAINS:
            raise ModelUnavailableError("NO_MODEL_FOR_DOMAIN", f"no models exist for domain '{domain}'", 404)
        try:
            self.registry.set_active_model(model_id)
        except ArtifactIntegrityError as exc:
            status = 404 if exc.code == "MODEL_NOT_REGISTERED" else 409
            raise ModelUnavailableError(exc.code, exc.detail, status) from exc
        return self.get_model(model_id)

    # ---- inference ----------------------------------------------------------------------------
    def serve_inference(
        self,
        domain: str,
        features: Mapping[str, Any],
        competition: str,
        position: str | None = None,
        as_of: str | None = None,
    ) -> PredictionServingResponse:
        started = time.perf_counter()
        try:
            response = self._serve(domain, features, competition, position, as_of)
        except ModelUnavailableError as exc:
            self.telemetry.record_refusal(exc.code)
            raise
        self.telemetry.record_served((time.perf_counter() - started) * 1000.0)
        return response

    def _serve(self, domain, features, competition, position, as_of) -> PredictionServingResponse:
        if domain not in SUPPORTED_DOMAINS:
            raise ModelUnavailableError("NO_MODEL_FOR_DOMAIN", f"no model artifact exists for domain '{domain}'", 404)
        try:
            entry = self.registry.active_manifest_entry()
        except ArtifactIntegrityError as exc:
            raise ModelUnavailableError(exc.code, exc.detail, 503) from exc

        status = entry.get("status")
        if status != "MODEL_VALIDATED":
            reasons = "; ".join(entry.get("blocking_reasons", [])) or "release gate not passed"
            raise ModelUnavailableError("MODEL_NOT_VALIDATED", f"active model status is {status}: {reasons}", 409)

        supported = entry.get("supported_competitions")
        if not supported or competition not in supported:
            raise ModelUnavailableError(
                "COMPETITION_NOT_SUPPORTED",
                f"competition '{competition}' is not declared supported by the active model",
                422,
            )

        try:
            bundle = self.registry.load_active_or_raise()  # hash-verified before unpickling
            values, missing = validate_feature_mapping(features, bundle.feature_names)
        except ArtifactIntegrityError as exc:
            http = 422 if exc.code == "FEATURE_SCHEMA_MISMATCH" else 503
            raise ModelUnavailableError(exc.code, exc.detail, http) from exc

        digest = _digest(features)
        as_of_text = as_of or date.today().isoformat()
        result = bundle.predict_player(
            player_id=f"request_{digest[:12]}",
            features=np.array(values, dtype=np.float32),
            as_of=as_of_text,
            minutes_played=features.get("observed_minutes_as_of"),
            age=features.get("age_at_transfer"),
            position_group=position,
            null_count=len(missing),
        )
        if not result.gate_decision.can_predict:
            raise ModelUnavailableError(
                result.data_status.value, "; ".join(result.gate_decision.reasons) or "sufficiency gate refused", 422
            )

        meta = bundle.metadata
        return PredictionServingResponse(
            prediction_id=f"pred_{meta.model_id}_{digest[:8]}",
            model_id=meta.model_id,
            model_version=meta.model_version,
            feature_version=meta.feature_set_version,
            dataset_version=meta.dataset_version,
            calculation_version="calc_v16.0",
            deployment_mode="ACTIVE_CHAMPION",
            input_digest=digest,
            predicted_value=result.estimated_value_eur,
            confidence_interval=(result.lower_bound_eur, result.upper_bound_eur),
            is_ood=False,
            data_status=result.data_status.value,
            artifact_sha256=entry["artifact_sha256"],
            model_release_status=status,
            missing_feature_count=len(missing),
        )


_GLOBAL_MODEL_SERVING_ENGINE: ModelServingEngine | None = None


def get_model_serving_engine() -> ModelServingEngine:
    global _GLOBAL_MODEL_SERVING_ENGINE
    if _GLOBAL_MODEL_SERVING_ENGINE is None:
        _GLOBAL_MODEL_SERVING_ENGINE = ModelServingEngine()
    return _GLOBAL_MODEL_SERVING_ENGINE
