"""Phase 18 (R13) — the worker's state survives restarts and every retry is accounted for.

Real PostgreSQL (fios_p17_test), real queue semantics (FOR UPDATE SKIP
LOCKED, leases), real handlers on ingested StatsBomb fixtures, and a real
`python -m app.worker --once` subprocess.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.operations import (
    Alert,
    FreshnessRecord,
    OperationalMetric,
    Project,
    ScheduledJob,
    Watchlist,
    WatchlistItem,
    WorkerHeartbeat,
    WorkerTask,
)
from app.phase17 import OpsRole
from app.phase17.auth import issue_user
from app.phase17.system_health import worker_status
from app.worker import handlers, queue
from app.worker.runner import Worker, ensure_default_schedules, schedule_due
from test_phase17_live_operations import final_match, ingest_all

ROOT = Path(__file__).resolve().parents[2]


async def _count(session, *where) -> int:
    return (await session.execute(select(func.count()).select_from(WorkerTask).where(*where))).scalar_one()


async def test_enqueue_is_idempotent_by_key(p17_session):
    a, created_a = await queue.enqueue(p17_session, "metrics_flush", {}, idempotency_key="k1")
    b, created_b = await queue.enqueue(p17_session, "metrics_flush", {"other": 1}, idempotency_key="k1")
    assert created_a and not created_b and a.id == b.id and b.parameters == {}
    assert await _count(p17_session) == 1


async def test_concurrent_claims_never_share_a_task(p17_session):
    for i in range(3):
        await queue.enqueue(p17_session, "metrics_flush", {}, idempotency_key=f"c{i}")
    Session = p17_session.test_sessionmaker

    async def claim(worker):
        async with Session() as s:
            t = await queue.claim(s, worker)
            return t.id if t else None

    got = await asyncio.gather(*(claim(f"w{i}") for i in range(5)))
    claimed = [g for g in got if g is not None]
    assert len(claimed) == 3 and len(set(claimed)) == 3  # 3 tasks, 5 workers: no task claimed twice


async def test_failures_back_off_then_go_dead_with_an_alert(p17_session, monkeypatch):
    async def boom(session, params, settings):
        raise RuntimeError("provider exploded")

    monkeypatch.setitem(handlers.HANDLERS, "provider_probe", boom)
    monkeypatch.setattr("app.worker.runner.HANDLERS", handlers.HANDLERS)
    task, _ = await queue.enqueue(p17_session, "provider_probe", {}, idempotency_key="boom", max_attempts=2)
    worker = Worker(p17_session.test_sessionmaker, worker_id="w-fail")

    first = await worker.run_task()
    assert first["status"] == queue.RETRY
    row = (await p17_session.execute(select(WorkerTask).where(WorkerTask.id == task.id)
                                     .execution_options(populate_existing=True))).scalar_one()
    delay = (row.not_before - datetime.now(timezone.utc)).total_seconds()
    assert row.attempts == 1 and 20 < delay <= queue.backoff_seconds(1) and "provider exploded" in row.error
    assert await worker.run_task() is None  # not due yet: backoff is respected

    await p17_session.execute(update(WorkerTask).where(WorkerTask.id == task.id)
                              .values(not_before=datetime.now(timezone.utc)))
    await p17_session.commit()
    second = await worker.run_task()
    assert second["status"] == queue.DEAD
    alert = (await p17_session.execute(select(Alert).where(Alert.category == "WORKER_TASK_DEAD"))).scalar_one()
    assert alert.evidence[0]["task_id"] == str(task.id)
    assert queue.backoff_seconds(2) == 2 * queue.backoff_seconds(1)


async def test_a_killed_workers_task_is_reclaimed_after_its_lease(p17_session):
    task, _ = await queue.enqueue(p17_session, "metrics_flush", {}, idempotency_key="lease")
    async with p17_session.test_sessionmaker() as s:
        claimed = await queue.claim(s, "worker-that-dies", lease_seconds=60)
    assert claimed.id == task.id
    # The worker process dies here: no complete(), no fail(). Its lease runs out.
    await p17_session.execute(update(WorkerTask).where(WorkerTask.id == task.id).values(
        lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await p17_session.commit()

    survivor = Worker(p17_session.test_sessionmaker, worker_id="worker-after-restart")
    result = await survivor.tick()
    assert str(task.id) in result["reclaimed"]["requeued"]
    done = [r for r in result["ran"] if r["task_id"] == str(task.id)]
    assert done and done[0]["status"] == queue.SUCCESS and done[0]["attempt"] == 2
    # The dead worker can no longer complete what it lost.
    async with p17_session.test_sessionmaker() as s:
        assert await queue.complete(s, claimed, {"late": True}, "worker-that-dies") is False


async def test_schedules_enqueue_once_per_bucket_and_survive_restart(p17_db_url, p17_session):
    assert await ensure_default_schedules(p17_session) > 0
    assert await ensure_default_schedules(p17_session) == 0  # never duplicated or overwritten
    await p17_session.execute(update(ScheduledJob).where(ScheduledJob.name != "metrics_flush").values(enabled=False))
    await p17_session.commit()
    now = datetime.now(timezone.utc)
    assert await schedule_due(p17_session, now) == ["metrics_flush"]
    assert await schedule_due(p17_session, now) == []  # same bucket: already enqueued

    # A brand-new process (new engine, new worker id) drains what the old one queued.
    engine = create_async_engine(p17_db_url)
    try:
        fresh = Worker(async_sessionmaker(engine, expire_on_commit=False), worker_id="fresh-process")
        result = await fresh.tick()
        assert [(r["job_type"], r["status"]) for r in result["ran"]] == [("metrics_flush", "SUCCESS")]
    finally:
        await engine.dispose()


async def test_real_handlers_on_ingested_data(p17_session, tmp_path):
    await ingest_all(p17_session, tmp_path)
    for i, job in enumerate(("freshness_refresh", "feature_refresh", "model_health", "alert_evaluation")):
        await queue.enqueue(p17_session, job, {}, idempotency_key=f"real-{i}")
    worker = Worker(p17_session.test_sessionmaker, worker_id="w-real")
    result = await worker.tick()
    statuses = {r["job_type"]: r["status"] for r in result["ran"]}
    assert statuses == {"freshness_refresh": "SUCCESS", "feature_refresh": "SUCCESS", "model_health": "SUCCESS",
                        "alert_evaluation": "SUCCESS"}
    layers = (await p17_session.execute(select(FreshnessRecord.layer, FreshnessRecord.status))).all()
    assert ("BRONZE", "CURRENT") in layers and ("SILVER", "CURRENT") in layers
    alert_task = (await p17_session.execute(select(WorkerTask).where(WorkerTask.job_type == "alert_evaluation"))).scalar_one()
    assert alert_task.output_snapshot == {"status": "NOTHING_TO_DO", "reason": "no watchlist items"}

    # A real condition on the ingested final: Argentina scored >= 1 in its last match.
    final = await final_match(p17_session)
    user, _ = await issue_user(p17_session, "Worker Org", "worker@example.com", "W", OpsRole.ANALYST)
    project = Project(organization_id=user.organization_id, owner_user_id=user.id, name="P")
    p17_session.add(project)
    await p17_session.flush()
    wl = Watchlist(project_id=project.id, owner_user_id=user.id, name="W")
    p17_session.add(wl)
    await p17_session.flush()
    p17_session.add(WatchlistItem(watchlist_id=wl.id, entity_type="CLUB", entity_id=str(final.home_club_id),
                                  entity_name="Home side", condition={"metric": "goals_for", "operator": ">=",
                                                                      "threshold": 1, "window_matches": 1}))
    await p17_session.commit()
    await queue.enqueue(p17_session, "alert_evaluation", {}, idempotency_key="real-alerts-2")
    ran = (await worker.tick())["ran"]
    assert [(r["job_type"], r["status"]) for r in ran] == [("alert_evaluation", "SUCCESS")]
    out = (await p17_session.execute(select(WorkerTask.output_snapshot).where(
        WorkerTask.idempotency_key == "real-alerts-2"))).scalar_one()
    assert out["items_evaluated"] == 1 and out["alerts_triggered"] == 1
    assert (await p17_session.execute(select(func.count()).select_from(Alert).where(
        Alert.category == "WATCHLIST_CONDITION"))).scalar_one() == 1

    await queue.enqueue(p17_session, "metrics_flush", {"window_seconds": 600}, idempotency_key="flush")
    await worker.tick()
    metrics = (await p17_session.execute(select(OperationalMetric).where(
        OperationalMetric.metric == "worker_tasks_completed"))).scalars().all()
    assert {m.labels["job_type"] for m in metrics} >= {"freshness_refresh", "feature_refresh"}
    assert all(m.source == "ops_worker_tasks" and m.sample_count >= 1 for m in metrics)


async def test_worker_health_comes_from_heartbeats(p17_session):
    now = datetime.now(timezone.utc)
    assert (await worker_status(p17_session, now))["status"] == "UNAVAILABLE"  # never started
    worker = Worker(p17_session.test_sessionmaker, worker_id="w-hb")
    await worker.heartbeat()
    assert (await worker_status(p17_session, datetime.now(timezone.utc)))["status"] == "HEALTHY"
    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    stale = await worker_status(p17_session, later)
    assert stale["status"] == "UNAVAILABLE" and stale["alive_workers"] == 0 and stale["known_workers"] == 1


async def test_worker_process_runs_and_records_its_heartbeat(p17_db_url, p17_session):
    await ensure_default_schedules(p17_session)
    # Keep the subprocess offline: only the jobs that read the database.
    await p17_session.execute(update(ScheduledJob).where(
        ScheduledJob.name.notin_(["metrics_flush", "model_health"])).values(enabled=False))
    await p17_session.commit()
    env = {**os.environ, "DATABASE_URL": p17_db_url, "PYTHONPATH": str(ROOT / "apps" / "api")}
    proc = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=ROOT / "apps" / "api", env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    beat = (await p17_session.execute(select(WorkerHeartbeat))).scalar_one()
    assert beat.tasks_completed == 2 and beat.tasks_failed == 0
    done = (await p17_session.execute(select(WorkerTask.job_type, WorkerTask.status))).all()
    assert sorted(done) == [("metrics_flush", "SUCCESS"), ("model_health", "SUCCESS")]


async def test_a_policy_refusal_is_blocked_not_success(p17_session):
    """A LIVE ingestion schedule without an AVAILABLE provider probe ends
    BLOCKED with its reason; it is not reported as a success or retried."""
    task, _ = await queue.enqueue(p17_session, "scheduled_ingestion",
                                  {"job_name": "api_football_fixtures", "params": {"league": 39, "season": 2025}},
                                  idempotency_key="blocked")
    result = await Worker(p17_session.test_sessionmaker, worker_id="w-blocked").run_task()
    assert result["status"] == queue.BLOCKED
    row = (await p17_session.execute(select(WorkerTask).where(WorkerTask.id == task.id)
                                     .execution_options(populate_existing=True))).scalar_one()
    assert row.status == "BLOCKED" and row.attempts == 1
    assert row.output_snapshot == {"status": "BLOCKED", "reason": "no AVAILABLE probe for api-football"}
