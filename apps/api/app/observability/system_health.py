"""System Health & Operations Diagnostic Engine (Phase 8 Section 14) - measured, or UNKNOWN.

Distinguishes:
1. LIVENESS  (the process answers; says nothing about data or models)
2. READINESS (required infrastructure - the database - is reachable)
3. DATA HEALTH (row counts, schema version and last successful ingestion, as measured)
4. MODEL HEALTH (registered artifacts, hash integrity, release status)

Every value here is measured or reported as None/UNKNOWN. Nothing is hard-coded to "HEALTHY"
(R5/R6); a healthy API does NOT imply healthy data or validated models.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.observability.model_governance import governance_registry
from app.observability.status import DEGRADED, NOT_CONFIGURED, OK, UNAVAILABLE, UNKNOWN, aggregate_status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _scalar(session: AsyncSession, sql: str) -> Any:
    """One scalar query; None (after rollback) when it cannot be answered."""
    try:
        return (await session.execute(text(sql))).scalar()
    except Exception:
        await session.rollback()
        return None


async def check_application_health() -> dict[str, Any]:
    """Liveness: the process is up and the event loop answered. Resource figures are None if unmeasured."""
    mem_rss_mb: float | None = None
    cpu_percent: float | None = None
    if psutil is not None:
        try:
            process = psutil.Process(os.getpid())
            mem_rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)
            cpu_percent = process.cpu_percent(interval=None)
        except Exception:
            pass
    return {
        "status": "ALIVE",
        "service": "Football Intelligence OS",
        "timestamp": _now(),
        "pid": os.getpid(),
        "memory_rss_mb": mem_rss_mb,
        "cpu_percent": cpu_percent,
        "open_threads": threading.active_count(),
    }


def _storage_component() -> dict[str, Any]:
    settings = get_settings()
    if settings.snapshot_storage_backend != "local":
        return {"status": UNKNOWN, "backend": settings.snapshot_storage_backend, "detail": "remote storage is not probed"}
    path = Path(settings.snapshot_storage_path)
    if path.is_dir():
        writable = os.access(path, os.W_OK)
        return {"status": OK if writable else UNAVAILABLE, "backend": "local", "writable": writable}
    return {"status": UNKNOWN, "backend": "local", "detail": "snapshot directory does not exist yet (created on first write)"}


async def check_readiness(session: AsyncSession | None = None) -> dict[str, Any]:
    """Required dependency = the database. Without a session the answer is UNKNOWN, never READY."""
    db: dict[str, Any] = {"status": UNKNOWN, "latency_ms": None}
    if session is not None:
        started = datetime.now(timezone.utc)
        try:
            await session.execute(text("SELECT 1"))
            db = {"status": OK, "latency_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000.0, 2)}
        except Exception as exc:
            await session.rollback()
            db = {"status": UNAVAILABLE, "latency_ms": None, "error": type(exc).__name__}  # no message: it can embed the DSN
    storage = _storage_component()
    overall = {"database": db["status"]}
    return {
        "status": {OK: "READY", UNAVAILABLE: "NOT_READY"}.get(aggregate_status(overall), "UNKNOWN"),
        "database": db,
        "snapshot_storage": storage,
        "checked_at": _now(),
    }


def _valuation_artifacts() -> tuple[list[dict[str, Any]], str | None]:
    """Hash-verified view of the registered valuation artifacts."""
    try:
        from app.market.ml.artifact_integrity import ArtifactIntegrityError, artifact_path, verify_artifact
        from app.market.ml.registry import get_valuation_registry

        registry = get_valuation_registry()
        manifest = registry._load_manifest()
        rows = []
        for model_id, entry in manifest.get("models", {}).items():
            try:
                verify_artifact(artifact_path(registry.base_dir, model_id), entry.get("artifact_sha256"))
                integrity = "VERIFIED"
            except ArtifactIntegrityError as exc:
                integrity = exc.code
            status = entry.get("status", "UNKNOWN")
            rows.append({
                "model_id": model_id,
                "domain": "valuation",
                "active": model_id == manifest.get("active_model_id"),
                "release_status": status,
                "integrity": integrity,
                "serving_allowed": integrity == "VERIFIED" and status == "MODEL_VALIDATED",
                "blocking_reasons": list(entry.get("blocking_reasons", [])),
            })
        return rows, None
    except Exception as exc:  # registry unreadable / ML dependency missing
        return [], type(exc).__name__


async def check_model_health() -> dict[str, Any]:
    """Registered artifacts + integrity + release status. 'HEALTHY' is never asserted without evidence."""
    artifacts, error = _valuation_artifacts()
    if error is not None:
        status = UNKNOWN
    elif not artifacts:
        status = UNAVAILABLE
    else:
        status = OK if all(a["serving_allowed"] for a in artifacts) else DEGRADED
    records = governance_registry.list_all_models()
    return {
        "status": status,
        "artifacts": artifacts,
        "artifact_registry_error": error,
        "governance_records": records,
        "governance_records_validated": sum(1 for r in records if r.get("status") == "MODEL_VALIDATED"),
        "note": "Only the valuation domain has a trained artifact; other domains have no validated model.",
        "checked_at": _now(),
    }


async def check_data_health(session: AsyncSession | None = None) -> dict[str, Any]:
    """Measured row counts, schema version and last successful ingestion; None when unmeasurable."""
    metrics: dict[str, Any] = {
        "canonical_players_count": None,
        "canonical_matches_count": None,
        "canonical_transfers_count": None,
        "last_successful_ingestion_at": None,
        "last_successful_ingestion_age_hours": None,
        "provenance_coverage_rate": None,  # not measured here
    }
    schema_version: str | None = None
    if session is None:
        return {"status": UNKNOWN, "metrics": metrics, "schema_version": None, "checked_at": _now()}

    metrics["canonical_players_count"] = await _scalar(session, "SELECT COUNT(*) FROM players")
    metrics["canonical_matches_count"] = await _scalar(session, "SELECT COUNT(*) FROM matches")
    metrics["canonical_transfers_count"] = await _scalar(session, "SELECT COUNT(*) FROM transfers")
    schema_version = await _scalar(session, "SELECT version_num FROM alembic_version")
    last_ok = await _scalar(session, "SELECT MAX(finished_at) FROM ingestion_runs WHERE status = 'SUCCESS'")
    if last_ok is not None:
        if last_ok.tzinfo is None:
            last_ok = last_ok.replace(tzinfo=timezone.utc)
        metrics["last_successful_ingestion_at"] = last_ok.isoformat()
        metrics["last_successful_ingestion_age_hours"] = round((datetime.now(timezone.utc) - last_ok).total_seconds() / 3600.0, 2)

    counts = [metrics["canonical_players_count"], metrics["canonical_matches_count"], metrics["canonical_transfers_count"]]
    if all(c is None for c in counts):
        status = UNAVAILABLE
    elif any(c is None for c in counts):
        status = DEGRADED
    elif sum(counts) == 0:
        status = DEGRADED  # reachable but empty
    else:
        status = OK if metrics["last_successful_ingestion_at"] is not None else UNKNOWN
    return {"status": status, "metrics": metrics, "schema_version": schema_version, "checked_at": _now()}
