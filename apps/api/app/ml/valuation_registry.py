"""Valuation model in the authoritative registry (Phase 18, R18 / R20 / R21 / N6).

The valuation model on disk (data/models/valuation) was registered in its
own JSON manifest as MODEL_VALIDATED. In this repository:
- its training dataset (open-transfers) is not present, and that dataset's
  provenance is self-asserted (R21), so lineage is SOURCE_UNVERIFIED;
- the record-path dataset builder gave every training row invented minutes,
  rating, contribution and intelligence values (fixed in Phase 18, N12);
- its own declared test R^2 is -0.09.
Its metrics cannot be reproduced, so the registry holds it as UNVERIFIED and
serving refuses it. The declared metrics are kept, labelled METRICS_UNVERIFIED.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import ModelRegistryEntry
from app.ml.serving import artifact_root

VALUATION_DOMAIN = "player_valuation"
SERVABLE = ("PRODUCTION", "CANARY", "SHADOW")
STATE_STATUS = {"UNVERIFIED": "MODEL_UNVERIFIED", "BLOCKED": "MODEL_BLOCKED"}


class ModelNotServable(Exception):
    def __init__(self, status: str, reasons: list[str], model_id: str | None = None) -> None:
        super().__init__("; ".join(reasons))
        self.status, self.reasons, self.model_id = status, reasons, model_id

    def body(self, **extra: Any) -> dict[str, Any]:
        return {"status": self.status, "reasons": self.reasons, "model_id": self.model_id,
                "modality": "NOT_AVAILABLE", **extra}


def _file_sha(path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


async def register_valuation_model(session: AsyncSession) -> ModelRegistryEntry | None:
    """Records the on-disk valuation model in ops_model_registry as UNVERIFIED.
    Idempotent. Returns None when no valuation manifest exists."""
    manifest_path = artifact_root() / "valuation" / "registry_manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text())
    model_id = manifest.get("active_model_id")
    meta = (manifest.get("models") or {}).get(model_id) or {}
    if not model_id:
        return None
    row = (await session.execute(select(ModelRegistryEntry).where(
        ModelRegistryEntry.domain == VALUATION_DOMAIN, ModelRegistryEntry.model_id == model_id))).scalar_one_or_none()
    artifact_uri = f"valuation/{model_id}.joblib"
    sha = _file_sha(artifact_root() / artifact_uri)
    reasons = [
        "training dataset (open-transfers) is not in the repository: metrics cannot be reproduced (REPRODUCTION_BLOCKED)",
        "open-transfers provenance is self-asserted (R21): lineage SOURCE_UNVERIFIED",
        "the record-path dataset builder assigned identical invented player features to every row (N12)",
        f"declared test R^2 {((meta.get('test_metrics') or {}).get('r2'))}: no better than predicting the mean",
    ]
    fields = dict(
        feature_version=str(meta.get("feature_set_version", "UNKNOWN")),
        dataset_version=str(meta.get("dataset_version", "UNKNOWN")), artifact_uri=artifact_uri, artifact_sha256=sha,
        dataset_sha256=None, supported_competitions=[], supported_horizons=["AS_OF_DATE"],
        windows={"train": meta.get("training_period"), "validation": meta.get("validation_period"),
                 "test": meta.get("test_period")},
        validation_metrics={"metrics_status": "METRICS_UNVERIFIED",
                            "declared": {k: meta.get(k) for k in ("train_metrics", "val_metrics", "test_metrics")},
                            "declared_status_in_manifest": meta.get("status")},
        lineage_status="SOURCE_UNVERIFIED",
        reproduction={"status": "REPRODUCTION_BLOCKED", "reason": reasons[0]},
        status_reason=" | ".join(reasons), deployment_state="UNVERIFIED", min_history_matches=0,
    )
    if row is None:
        row = ModelRegistryEntry(domain=VALUATION_DOMAIN, model_id=model_id,
                                 model_version=str(meta.get("model_version", "UNKNOWN")), **fields)
        session.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
    await session.flush()
    return row


async def valuation_gate(session: AsyncSession, model_id: str | None) -> ModelRegistryEntry:
    """Raises ModelNotServable unless `model_id` is registered in a serving
    state and its artifact bytes match the registry."""
    if not model_id:
        raise ModelNotServable("MODEL_UNAVAILABLE", ["no valuation model artifact is present"])
    row = (await session.execute(select(ModelRegistryEntry).where(
        ModelRegistryEntry.domain == VALUATION_DOMAIN, ModelRegistryEntry.model_id == model_id))).scalar_one_or_none()
    if row is None:
        raise ModelNotServable("MODEL_UNVERIFIED",
                               [f"{model_id} is not in the authoritative registry (ops_model_registry)"], model_id)
    if row.deployment_state not in SERVABLE:
        raise ModelNotServable(STATE_STATUS.get(row.deployment_state, "MODEL_UNAVAILABLE"),
                               [f"registry state {row.deployment_state}"] + (row.status_reason or "").split(" | "),
                               model_id)
    if _file_sha(artifact_root() / (row.artifact_uri or "")) != row.artifact_sha256:
        raise ModelNotServable("MODEL_ARTIFACT_MISMATCH", ["artifact bytes do not match the registry SHA-256"], model_id)
    return row
