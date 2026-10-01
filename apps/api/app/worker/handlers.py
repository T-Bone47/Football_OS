"""Worker job handlers (Phase 18, R13).

Each handler calls an existing operation and returns what it measured. A
handler raises on failure (the queue retries with backoff); it never
returns a success it did not observe. Handlers whose inputs are absent
return an explicit status (NOTHING_TO_DO, BLOCKED) as their output.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.canonical import Match
from app.db.models.operations import (
    FreshnessRecord,
    OperationalMetric,
    Project,
    Watchlist,
    WatchlistItem,
    WorkerTask,
)

Handler = Callable[[AsyncSession, dict[str, Any], Settings], Awaitable[dict[str, Any]]]


async def provider_probe(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    from app.phase17.provider_probe import run_probes

    results = await run_probes(session, settings)
    return {"probes": [{"provider": r.provider, "resource": r.resource, "state": r.state,
                        "http_status": r.http_status, "latency_ms": r.latency_ms} for r in results]}


async def scheduled_ingestion(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """One ScheduleSpec job. LIVE-class jobs run only for a provider whose
    latest probe is AVAILABLE; otherwise the task records BLOCKED."""
    from app.ingestion.factory import build_snapshot_store
    from app.phase17 import ScheduleClass
    from app.phase17.live_ingestion import SCHEDULES, LiveIngestionRunner
    from app.phase17.provider_probe import latest_probe_states

    spec = next((s for s in SCHEDULES if s.job_name == params["job_name"]), None)
    if spec is None:
        raise ValueError(f"unknown schedule {params['job_name']!r}")
    if spec.schedule_class == ScheduleClass.LIVE:
        probes = await latest_probe_states(session)
        if not any(p == spec.provider and r.state == "AVAILABLE" for (p, _), r in probes.items()):
            return {"status": "BLOCKED", "reason": f"no AVAILABLE probe for {spec.provider}"}
    res = await LiveIngestionRunner(session, build_snapshot_store(settings)).run_job(
        spec.provider, spec.resource, params.get("params", {}), spec.job_name, spec.schedule_class)
    if res.status == "RATE_LIMIT_DEFERRED":
        raise RuntimeError(f"ingestion {spec.job_name} deferred by the rate governor; retried with backoff")
    if res.status != "SUCCESS":
        raise RuntimeError(f"ingestion {spec.job_name} ended {res.status}: {'; '.join(res.errors[:2])}")
    return {"job_id": res.job_id, "status": res.status, "snapshot_sha256": res.snapshot_sha256, "records": res.records}


async def normalization(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Re-normalize one Bronze snapshot (integrity-checked) into Silver."""
    from app.phase17.live_ingestion import replay_snapshot

    return await replay_snapshot(session, uuid.UUID(params["snapshot_id"]))


async def _competition_seasons(session: AsyncSession, params: dict[str, Any]) -> list[uuid.UUID]:
    if params.get("competition_season_id"):
        return [uuid.UUID(params["competition_season_id"])]
    return list((await session.execute(select(Match.competition_season_id).distinct())).scalars().all())


async def feature_refresh(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    from app.phase17.feature_refresh import refresh_competition_season

    out = {}
    for cs in await _competition_seasons(session, params):
        outcomes = await refresh_competition_season(session, cs)
        out[str(cs)] = {"clubs": len(outcomes), "computed": sum(1 for o in outcomes if o.computed),
                        "statuses": sorted({o.status.value for o in outcomes})}
    await session.commit()
    return {"competition_seasons": out} if out else {"status": "NOTHING_TO_DO", "reason": "no matches stored"}


async def model_health(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    from app.phase17.model_ops import model_health_snapshot

    since = datetime.now(timezone.utc) - timedelta(hours=float(params.get("window_hours", 24)))
    return await model_health_snapshot(session, since=since)


async def drift_monitoring(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    from app.phase17.alerts import raise_operational_alert
    from app.phase17.model_ops import drift_report

    report = await drift_report(session, params.get("evidence_mode", "LIVE"))
    if report.get("status") in ("DRIFT", "CRITICAL_DRIFT"):
        await raise_operational_alert(session, category="MODEL_DRIFT", severity="HIGH",
                                      title="Prediction drift detected (PSI)", evidence=[report],
                                      source="worker.drift_monitoring", dedup_scope=params.get("evidence_mode", "LIVE"))
        await session.commit()
    return report


async def freshness_refresh(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Measures the freshness chain per competition season and stores one
    row per layer (timestamps from snapshots and tables, never asserted)."""
    from app.phase17.readiness import freshness_chain

    now = datetime.now(timezone.utc)
    task_id = params.get("_task_id")
    written = 0
    for cs in await _competition_seasons(session, params):
        chain = await freshness_chain(session, cs, now=now)
        for layer in chain.get("layers", []):
            ts = layer.get("timestamp")
            observed = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
            if observed is not None and observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            session.add(FreshnessRecord(competition_season_id=cs, layer=layer["layer"], observed_at=observed,
                                        age_hours=layer.get("age_hours"), status=layer["state"],
                                        basis=str(layer.get("basis"))[:128], computed_at=now,
                                        task_id=uuid.UUID(task_id) if task_id else None))
            written += 1
    await session.commit()
    return {"records_written": written} if written else {"status": "NOTHING_TO_DO", "reason": "no matches stored"}


async def alert_evaluation(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Evaluates every watchlist condition against stored match evidence."""
    from app.phase17.alerts import evaluate_item

    rows = (await session.execute(select(WatchlistItem, Project.organization_id)
                                  .join(Watchlist, Watchlist.id == WatchlistItem.watchlist_id)
                                  .join(Project, Project.id == Watchlist.project_id))).all()
    results = []
    for item, org_id in rows:
        results.append(await evaluate_item(session, item, settings, org_id))
    await session.commit()
    alerts = [r["alert"] for r in results if r.get("alert") and not r["alert"].get("deduplicated")]
    return {"items_evaluated": len(results), "alerts_triggered": len(alerts),
            "insufficient_data": sum(1 for r in results if r.get("condition_met") is None)} if results else {
        "status": "NOTHING_TO_DO", "reason": "no watchlist items"}


async def metrics_flush(session: AsyncSession, params: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Worker throughput and task latency per job type over the last window,
    measured from ops_worker_tasks. Nothing is written for an empty window."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(seconds=float(params.get("window_seconds", 300)))
    rows = (await session.execute(
        select(WorkerTask.job_type, WorkerTask.status, func.count(),
               func.percentile_cont(0.5).within_group(
                   func.extract("epoch", WorkerTask.completed_at - WorkerTask.started_at)),
               func.percentile_cont(0.95).within_group(
                   func.extract("epoch", WorkerTask.completed_at - WorkerTask.started_at)))
        .where(WorkerTask.completed_at >= start, WorkerTask.completed_at < end, WorkerTask.started_at.is_not(None))
        .group_by(WorkerTask.job_type, WorkerTask.status))).all()
    for job_type, status, n, p50, p95 in rows:
        labels = {"job_type": job_type, "status": status}
        session.add(OperationalMetric(metric="worker_tasks_completed", labels=labels, value=float(n), unit="count",
                                      sample_count=n, window_start=start, window_end=end, source="ops_worker_tasks"))
        for name, v in (("worker_task_duration_p50", p50), ("worker_task_duration_p95", p95)):
            if v is not None:
                session.add(OperationalMetric(metric=name, labels=labels, value=float(v), unit="seconds",
                                              sample_count=n, window_start=start, window_end=end,
                                              source="ops_worker_tasks"))
    await session.commit()
    return {"window_start": start.isoformat(), "window_end": end.isoformat(), "groups": len(rows)}


HANDLERS: dict[str, Handler] = {
    "provider_probe": provider_probe,
    "scheduled_ingestion": scheduled_ingestion,
    "normalization": normalization,
    "feature_refresh": feature_refresh,
    "model_health": model_health,
    "drift_monitoring": drift_monitoring,
    "freshness_refresh": freshness_refresh,
    "alert_evaluation": alert_evaluation,
    "metrics_flush": metrics_flush,
}
