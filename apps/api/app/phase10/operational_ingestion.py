"""Phase 10 ingestion cycle VIEW over real ingestion runs (handoff R4).

History: this module used to *execute* a "cycle". With no payload it invented an Arsenal 2-1
Chelsea fixture stamped with the current time, wrote it to data/bronze/ as if a provider had
returned it, and then marked eight stages complete that never ran (identity resolution, feature
refresh, model readiness, decision impact...). It also accepted a caller-supplied "provider
response" and stored it as Bronze.

Ingestion now goes through app.ingestion.service.IngestionService (capability gate -> provider
fetch -> content-addressed snapshot -> schema validation). This module only translates that
persisted result into the Phase 10 cycle shape and reports, per stage, what actually happened:
COMPLETED, FAILED or NOT_EXECUTED. It performs no I/O and creates no data.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

COMPLETED = "COMPLETED"
FAILED = "FAILED"
NOT_EXECUTED = "NOT_EXECUTED"

INGESTION_STAGES = ("capability_check", "provider_fetch", "bronze_snapshot_persisted", "schema_validation")
# Not run by an ingestion trigger. They stay NOT_EXECUTED until a real implementation reports them.
DOWNSTREAM_STAGES = (
    "silver_normalization",
    "identity_resolution",
    "feature_refresh",
    "model_readiness_check",
    "decision_impact_evaluation",
)
ALL_STAGES = INGESTION_STAGES + DOWNSTREAM_STAGES

_PARAM_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def sha256_from_location(storage_location: str | None) -> str | None:
    """Snapshots are content-addressed: the file name is <sha256>.<ext> (local path or s3:// key).
    The hash is not a column of data_snapshots, so it is read back from the stored location."""
    if not storage_location:
        return None
    stem = storage_location.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    return stem if _SHA256.fullmatch(stem) else None


def validate_provider_params(params: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    """Scalar-only provider parameters (they are interpolated into provider URL templates)."""
    clean: dict[str, str | int | float | bool] = {}
    for key, value in params.items():
        if not _PARAM_KEY.fullmatch(str(key)):
            raise ValueError(f"invalid parameter name: {key!r}")
        if isinstance(value, bool) or isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", value) and ".." not in value:
            clean[key] = value
        else:
            raise ValueError(f"invalid value for parameter {key!r}")
    return clean


def stage_results(*, run_status: str, error: str | None, has_snapshot: bool, validation_status: str | None) -> dict[str, str]:
    """Per-stage truth derived only from the recorded run/snapshot."""
    stages = {name: NOT_EXECUTED for name in ALL_STAGES}
    if run_status in ("QUEUED", "RUNNING"):
        return stages
    if error and error.startswith("capability registry:"):
        stages["capability_check"] = FAILED
        return stages
    stages["capability_check"] = COMPLETED
    if not has_snapshot:
        stages["provider_fetch"] = FAILED if run_status == "FAILED" else NOT_EXECUTED
        return stages
    stages["provider_fetch"] = COMPLETED
    stages["bronze_snapshot_persisted"] = COMPLETED
    if validation_status == "VALID":
        stages["schema_validation"] = COMPLETED
    elif validation_status == "INVALID":
        stages["schema_validation"] = FAILED
    return stages  # PENDING / unknown => no validator ran => NOT_EXECUTED


def cycle_status(run_status: str, stages: Mapping[str, str]) -> str:
    if run_status in ("QUEUED", "RUNNING", "FAILED"):
        return run_status
    if run_status == "PARTIAL" or any(v != COMPLETED for v in stages.values()):
        return "PARTIAL"
    return "SUCCESS"


def _iso(value: datetime | str | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def cycle_view(
    *,
    run_id: str,
    provider: str,
    resource: str,
    run_status: str,
    error: str | None,
    started_at: datetime | str | None,
    finished_at: datetime | str | None,
    record_count: int | None,
    snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    stages = stage_results(
        run_status=run_status,
        error=error,
        has_snapshot=snapshot is not None,
        validation_status=None if snapshot is None else snapshot.get("validation_status"),
    )
    return {
        "run_id": run_id,
        "provider": provider,
        "resource": resource,
        "status": cycle_status(run_status, stages),
        "ingestion_run_status": run_status,
        "started_at": _iso(started_at),
        "finished_at": _iso(finished_at),
        "stage_results": stages,
        "stages_completed": [name for name in ALL_STAGES if stages[name] == COMPLETED],
        "stages_not_executed": [name for name in ALL_STAGES if stages[name] == NOT_EXECUTED],
        "snapshot": dict(snapshot) if snapshot is not None else None,
        "record_count": record_count,
        "error": error,
        "note": "An ingestion trigger captures and validates Bronze data only; downstream stages are reported NOT_EXECUTED.",
    }
