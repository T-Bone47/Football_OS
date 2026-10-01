"""Measured health (Phase 18, R5/R6, N2/N4).

Three questions, answered separately, each from a measurement:

1. LIVENESS  (/health, /health/live): is this process running? Process facts
   only; it says nothing about data or models.
2. READINESS (/health/ready, /readiness): can this process serve? The
   database answers, and its migration version equals the head of the
   migration scripts shipped with this code.
3. DATA and MODEL state (/data-status, /model-status): counts, provenance
   coverage, snapshot age and registry contents, read from PostgreSQL.

Nothing here is declared. A value that was not measured is reported as
NOT_MEASURED, never as a plausible default.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a declared dependency
    psutil = None
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

NOT_MEASURED = "NOT_MEASURED"

# Silver tables whose rows carry a link to the Bronze snapshot they came from.
LINEAGE_TABLES = {
    "matches": "snapshot_id",
    "match_lineups": "snapshot_id",
    "match_events": "snapshot_id",
    "match_statistics": "snapshot_id",
    "player_match_stats": "snapshot_id",
    "player_season_stats": "snapshot_id",
    "transfers": "source_snapshot_id",
    "canonical_actions": "source_snapshot_id",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache
def expected_migration_head() -> str | None:
    """Head revision of the migration scripts deployed with this code, or None
    when the scripts are not present (then readiness cannot confirm schema)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError:  # pragma: no cover
        return None
    for parent in Path(__file__).resolve().parents:
        ini = parent / "alembic.ini"
        if ini.is_file():
            cfg = Config(str(ini))
            cfg.set_main_option("script_location", str(parent / "database" / "migrations"))
            return ScriptDirectory.from_config(cfg).get_current_head()
    return None


async def check_application_health() -> dict[str, Any]:
    """Liveness: facts about this process, measured now."""
    out: dict[str, Any] = {"status": "ALIVE", "service": "Football Intelligence OS", "pid": os.getpid(),
                           "checked_at": _now()}
    if psutil is None:
        out.update(memory_rss_mb=NOT_MEASURED, cpu_percent=NOT_MEASURED, open_threads=NOT_MEASURED,
                   uptime_s=NOT_MEASURED)
        return out
    proc = psutil.Process(os.getpid())
    out.update(
        memory_rss_mb=round(proc.memory_info().rss / (1024 * 1024), 2),
        cpu_percent=proc.cpu_percent(interval=None),
        open_threads=proc.num_threads(),
        uptime_s=round(time.time() - proc.create_time(), 1),
    )
    return out


async def check_readiness(session: AsyncSession | None = None) -> dict[str, Any]:
    """Readiness: the database answers and is migrated to this code's head."""
    reasons: list[str] = []
    db: dict[str, Any] = {"status": NOT_MEASURED, "latency_ms": None, "migration_version": None}
    expected = expected_migration_head()
    if session is None:
        reasons.append("no database session")
    else:
        t0 = time.perf_counter()
        try:
            await session.execute(text("SELECT 1"))
            db["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            db["migration_version"] = (await session.execute(
                text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
            db["status"] = "REACHABLE"
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            db["status"] = "UNREACHABLE"
            db["error"] = type(exc).__name__
            reasons.append(f"database unreachable ({type(exc).__name__})")
    if db["status"] == "REACHABLE":
        if expected is None:
            reasons.append("migration scripts not found; schema version cannot be confirmed")
        elif db["migration_version"] != expected:
            reasons.append(f"database at migration {db['migration_version']}, code expects {expected}")
    return {
        "status": "READY" if not reasons else "NOT_READY",
        "reasons": reasons,
        "database": db,
        "expected_migration_head": expected,
        "checked_at": _now(),
    }


async def check_model_health(session: AsyncSession | None = None) -> dict[str, Any]:
    """Model state from the authoritative registry (ops_model_registry)."""
    if session is None:
        return {"status": NOT_MEASURED, "reason": "no database session", "models": [], "checked_at": _now()}
    rows = (await session.execute(text(
        "SELECT model_id, model_version, domain, deployment_state, artifact_sha256, supported_competitions, "
        "validation_metrics, registered_at FROM ops_model_registry ORDER BY registered_at"
    ))).mappings().all()
    models = [
        {
            "model_id": r["model_id"], "model_version": r["model_version"], "domain": r["domain"],
            "status": r["deployment_state"], "artifact_sha256": r["artifact_sha256"],
            "supported_competitions": r["supported_competitions"] or [],
            "has_validation_evidence": bool(r["validation_metrics"]),
            "registered_at": r["registered_at"].isoformat() if r["registered_at"] else None,
        }
        for r in rows
    ]
    servable = [m for m in models if m["status"] in ("PRODUCTION", "CANARY", "SHADOW") and m["supported_competitions"]]
    if not models:
        status = "NO_MODELS_REGISTERED"
    elif not servable:
        status = "NO_SERVABLE_MODEL"
    else:
        status = "SERVABLE_MODELS_PRESENT"
    return {"status": status, "registry": "ops_model_registry", "models": models,
            "servable_models": len(servable), "checked_at": _now()}


async def check_data_health(session: AsyncSession | None = None) -> dict[str, Any]:
    """Data state measured from PostgreSQL: counts, provenance coverage, age."""
    if session is None:
        return {"status": NOT_MEASURED, "reason": "no database session", "checked_at": _now()}

    async def scalar(sql: str) -> Any:
        return (await session.execute(text(sql))).scalar()

    counts = {t: await scalar(f"SELECT count(*) FROM {t}") for t in ("players", "clubs", "matches", "transfers")}
    lineage: dict[str, Any] = {}
    gaps = []
    for table, col in LINEAGE_TABLES.items():
        total = await scalar(f"SELECT count(*) FROM {table}")
        linked = await scalar(f"SELECT count(*) FROM {table} WHERE {col} IS NOT NULL")
        lineage[table] = {"rows": total, "rows_with_snapshot": linked,
                          "coverage": round(linked / total, 4) if total else NOT_MEASURED}
        if total and linked < total:
            gaps.append(table)
    latest = (await session.execute(text(
        "SELECT max(retrieved_at) AS stored, max(provider_retrieved_at) AS provider FROM data_snapshots"
    ))).mappings().one()
    newest = latest["provider"] or latest["stored"]
    age_h = round((datetime.now(timezone.utc) - newest).total_seconds() / 3600, 2) if newest else None
    schema_version = await scalar("SELECT version_num FROM alembic_version")

    if sum(counts.values()) == 0:
        status = "NO_DATA"
    elif gaps:
        status = "PROVENANCE_GAPS"
    else:
        status = "DATA_AVAILABLE"
    return {
        "status": status,
        "counts": counts,
        "provenance_coverage": lineage,
        "tables_with_provenance_gaps": gaps,
        "latest_snapshot_retrieved_at": newest.isoformat() if newest else None,
        "latest_snapshot_age_hours": age_h if age_h is not None else NOT_MEASURED,
        # Freshness is judged per competition and provider schedule, not here:
        "freshness": "see /api/v1/ops/freshness/{competition_season_id}",
        "schema_version": schema_version,
        "expected_schema_version": expected_migration_head(),
        "checked_at": _now(),
    }
