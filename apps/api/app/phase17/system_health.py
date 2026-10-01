"""Real system health (§27, §36). Every component is probed; nothing is
assumed. Replaces the hardcoded Phase 16 health payloads (reconnaissance R5).
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings
from app.db.models.operations import JobRun, ModelRegistryEntry
from app.phase17 import ComponentHealth as H
from app.phase17.environments import audit_environment
from app.phase17.provider_probe import latest_probe_states, provider_rollup

PROBE_STALE_AFTER = timedelta(hours=24)


async def probe_database(engine: AsyncEngine) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            version = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
        return {"status": H.HEALTHY.value, "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "migration_head": version}
    except Exception as exc:  # noqa: BLE001
        return {"status": H.UNAVAILABLE.value, "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "error": type(exc).__name__}


def probe_redis(settings: Settings) -> dict[str, Any]:
    if not settings.redis_url:
        return {"status": H.NOT_CONFIGURED.value}
    t0 = time.perf_counter()
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
        client.ping()
        info = client.info("stats")
        return {"status": H.HEALTHY.value, "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "keyspace_hits": info.get("keyspace_hits"), "keyspace_misses": info.get("keyspace_misses"),
                "used_by": "per-user API rate limit (falls back to process-local window when down)"}
    except Exception as exc:  # noqa: BLE001
        return {"status": H.UNAVAILABLE.value, "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
                "error": type(exc).__name__, "degraded_mode": "rate limiting uses a process-local window"}


def probe_storage(settings: Settings) -> dict[str, Any]:
    t0 = time.perf_counter()
    if settings.snapshot_storage_backend == "s3":
        try:
            import boto3

            client = boto3.client("s3", endpoint_url=settings.s3_endpoint, aws_access_key_id=settings.s3_access_key,
                                  aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region)
            client.head_bucket(Bucket=settings.s3_bucket)
            return {"status": H.HEALTHY.value, "backend": "s3", "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        except Exception as exc:  # noqa: BLE001
            return {"status": H.UNAVAILABLE.value, "backend": "s3", "error": type(exc).__name__}
    root = Path(settings.snapshot_storage_path)
    probe = root / f".health-{uuid.uuid4().hex}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"ok")
        probe.unlink()
        files = sum(1 for _ in root.rglob("*.json"))
        return {"status": H.HEALTHY.value, "backend": "local", "path": str(root), "snapshot_files": files,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "durability": "single local disk (not durable)"}
    except Exception as exc:  # noqa: BLE001
        return {"status": H.UNAVAILABLE.value, "backend": "local", "error": type(exc).__name__,
                "degraded_mode": "ingestion runs fail with SnapshotStoreError; Silver is not touched"}


async def system_status(session: AsyncSession, engine: AsyncEngine, settings: Settings) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    db = await probe_database(engine)
    components: dict[str, Any] = {"database": db, "redis": probe_redis(settings), "object_storage": probe_storage(settings)}
    if db["status"] == H.HEALTHY.value:
        try:
            latest = await latest_probe_states(session)
            rollup = provider_rollup(latest)
            providers = {}
            for p, state in rollup.items():
                newest = max(r.probed_at for (pp, _), r in latest.items() if pp == p)
                stale = now - newest > PROBE_STALE_AFTER
                providers[p] = {"status": "UNKNOWN" if stale else state, "last_probe": newest.isoformat(),
                                "probe_stale": stale}
            components["providers"] = providers or {"status": "UNKNOWN", "reason": "no probe has run"}
            stuck = (await session.execute(select(func.count()).select_from(JobRun).where(
                JobRun.status == "RUNNING", JobRun.started_at < now - timedelta(hours=1)))).scalar_one()
            last_job = (await session.execute(select(func.max(JobRun.started_at)))).scalar_one()
            components["jobs"] = {"status": H.DEGRADED.value if stuck else H.HEALTHY.value, "stuck_running": stuck,
                                  "last_job_started": last_job.isoformat() if last_job else None}
            servable = (await session.execute(select(ModelRegistryEntry.model_id, ModelRegistryEntry.deployment_state)
                                              .where(ModelRegistryEntry.deployment_state.in_(["PRODUCTION", "CANARY", "SHADOW"])))).all()
            components["model_serving"] = {
                "status": H.HEALTHY.value if any(s == "PRODUCTION" for _, s in servable) else
                (H.DEGRADED.value if servable else H.UNAVAILABLE.value),
                "models": [{"model_id": m, "deployment_state": s} for m, s in servable],
                "note": None if any(s == "PRODUCTION" for _, s in servable) else "no PRODUCTION model; SHADOW/CANARY models serve labelled predictions only",
            }
        except Exception as exc:  # noqa: BLE001
            components["providers"] = {"status": "UNKNOWN", "error": type(exc).__name__}
    else:
        components["providers"] = {"status": "UNKNOWN", "reason": "database unavailable; probe history unreadable"}
        components["jobs"] = {"status": "UNKNOWN"}
        components["model_serving"] = {"status": "UNKNOWN"}
    components["scheduler_worker"] = {"status": H.NOT_CONFIGURED.value,
                                      "detail": "no long-running worker process exists (apps/worker absent); jobs run on demand or via tools/phase17_scheduler.py"}

    statuses = [c.get("status") for c in components.values() if isinstance(c, dict)]
    provider_states = [v.get("status") for v in components["providers"].values() if isinstance(v, dict)]
    if "status" in components["providers"] or any(s != "AVAILABLE" for s in provider_states):
        statuses.append(H.DEGRADED.value)
    if db["status"] != H.HEALTHY.value or components["object_storage"]["status"] != H.HEALTHY.value:
        overall = H.UNAVAILABLE.value if db["status"] != H.HEALTHY.value else H.DEGRADED.value
    elif any(s in (H.UNAVAILABLE.value, H.DEGRADED.value) for s in statuses):
        overall = H.DEGRADED.value
    else:
        overall = H.HEALTHY.value
    env = audit_environment(settings)
    return {"status": overall, "checked_at": now.isoformat(), "environment": env.environment.value,
            "environment_audit": env.to_dict(), "components": components}
