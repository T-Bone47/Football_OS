"""Worker process: scheduler, heartbeat and task loop (Phase 18, R13).

    python -m app.worker            # run until SIGTERM/SIGINT
    python -m app.worker --once     # one scheduler tick + drain due tasks, then exit

State lives only in PostgreSQL, so a restart loses nothing:
- Scheduled jobs (ops_scheduled_jobs) are enqueued with the idempotency key
  sched:<name>:<interval bucket>; any number of workers enqueue each run once.
- Tasks are claimed with a lease (queue.claim); a killed worker's task is
  reclaimed after the lease expires.
- Each worker upserts its heartbeat (ops_worker_heartbeats); system health
  reports the worker from those rows.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.models.operations import ScheduledJob, WorkerHeartbeat
from app.worker import queue
from app.worker.handlers import HANDLERS

log = logging.getLogger("app.worker")

HEARTBEAT_INTERVAL_S = 15.0
LEASE_SECONDS = 600.0

# Default recurring jobs. Operational configuration, not data: each run
# measures real state. Ingestion schedules follow app.phase17.live_ingestion
# SCHEDULES (ON_DEMAND jobs are never scheduled).
DEFAULT_SCHEDULES: list[dict[str, Any]] = [
    {"name": "provider_probe", "job_type": "provider_probe", "parameters": {}, "interval_seconds": 900},
    {"name": "freshness_refresh", "job_type": "freshness_refresh", "parameters": {}, "interval_seconds": 3600},
    {"name": "model_health", "job_type": "model_health", "parameters": {"window_hours": 24}, "interval_seconds": 3600},
    {"name": "drift_monitoring", "job_type": "drift_monitoring", "parameters": {"evidence_mode": "LIVE"},
     "interval_seconds": 86400},
    {"name": "alert_evaluation", "job_type": "alert_evaluation", "parameters": {}, "interval_seconds": 600},
    {"name": "metrics_flush", "job_type": "metrics_flush", "parameters": {"window_seconds": 300}, "interval_seconds": 300},
    {"name": "feature_refresh", "job_type": "feature_refresh", "parameters": {}, "interval_seconds": 86400},
    {"name": "statsbomb_competitions_index", "job_type": "scheduled_ingestion",
     "parameters": {"job_name": "statsbomb_competitions_index", "params": {}}, "interval_seconds": 7 * 86400},
    {"name": "api_football_fixtures", "job_type": "scheduled_ingestion",
     "parameters": {"job_name": "api_football_fixtures", "params": {"league": 39, "season": 2025}},
     "interval_seconds": 600},
]


def code_version() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).resolve().parents[3],
                              capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return os.environ.get("GIT_COMMIT")


async def ensure_default_schedules(session: AsyncSession) -> int:
    """Inserts the default schedule rows that do not exist yet (never
    overwrites an operator's change to interval or enabled)."""
    created = 0
    for d in DEFAULT_SCHEDULES:
        res = await session.execute(insert(ScheduledJob).values(
            id=uuid.uuid4(), name=d["name"], job_type=d["job_type"], parameters=d["parameters"],
            interval_seconds=d["interval_seconds"], max_attempts=d.get("max_attempts", 3), enabled=True,
        ).on_conflict_do_nothing(index_elements=["name"]))
        created += res.rowcount or 0
    await session.commit()
    return created


async def schedule_due(session: AsyncSession, now: datetime | None = None) -> list[str]:
    """Enqueues each enabled schedule once per interval bucket."""
    now = now or datetime.now(timezone.utc)
    enqueued = []
    jobs = (await session.execute(select(ScheduledJob).where(ScheduledJob.enabled.is_(True)))).scalars().all()
    for j in jobs:
        if j.job_type not in HANDLERS:
            log.warning("schedule %s has unknown job_type %s", j.name, j.job_type)
            continue
        bucket = int(now.timestamp() // max(60, j.interval_seconds))
        _, created = await queue.enqueue(session, j.job_type, j.parameters, idempotency_key=f"sched:{j.name}:{bucket}",
                                         max_attempts=j.max_attempts, correlation_id=f"sched-{j.name}-{bucket}",
                                         commit=False)
        if created:
            enqueued.append(j.name)
    await session.commit()
    return enqueued


class Worker:
    def __init__(self, sessionmaker: async_sessionmaker, settings: Settings | None = None,
                 worker_id: str | None = None, lease_seconds: float = LEASE_SECONDS,
                 job_types: list[str] | None = None) -> None:
        self.Session = sessionmaker
        self.settings = settings or get_settings()
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.lease_seconds = lease_seconds
        self.job_types = job_types
        self.started_at = datetime.now(timezone.utc)
        self.completed = 0
        self.failed = 0
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def heartbeat(self) -> None:
        now = datetime.now(timezone.utc)
        async with self.Session() as s:
            await s.execute(insert(WorkerHeartbeat).values(
                worker_id=self.worker_id, started_at=self.started_at, last_seen_at=now,
                tasks_completed=self.completed, tasks_failed=self.failed, hostname=socket.gethostname(),
                code_version=code_version(),
            ).on_conflict_do_update(index_elements=["worker_id"], set_={
                "last_seen_at": now, "tasks_completed": self.completed, "tasks_failed": self.failed}))
            await s.commit()

    async def run_task(self) -> dict[str, Any] | None:
        """Claims and runs one due task. None when nothing is due."""
        async with self.Session() as s:
            task = await queue.claim(s, self.worker_id, self.lease_seconds, self.job_types)
            if task is None:
                return None
            handler = HANDLERS.get(task.job_type)
            info = {"task_id": str(task.id), "job_type": task.job_type, "attempt": task.attempts}
            try:
                if handler is None:
                    raise LookupError(f"no handler for job_type {task.job_type!r}")
                output = await handler(s, {**task.parameters, "_task_id": str(task.id)}, self.settings)
            except Exception as exc:  # noqa: BLE001 - every failure is recorded on the task
                await s.rollback()
                info["status"] = await queue.fail(s, task, f"{type(exc).__name__}: {exc}", self.worker_id)
                self.failed += 1
                log.warning("task %s %s failed: %s", task.job_type, task.id, exc)
                return info
            final = queue.BLOCKED if output.get("status") == "BLOCKED" else queue.SUCCESS
            ok = await queue.complete(s, task, output, self.worker_id, status=final)
            info["status"] = final if ok else "LEASE_LOST"
            self.completed += ok
            return info

    async def tick(self, max_tasks: int = 50) -> dict[str, Any]:
        """One scheduler pass, lease reclamation, then drain up to max_tasks."""
        await self.heartbeat()
        async with self.Session() as s:
            reclaimed = await queue.reclaim_expired_leases(s)
            scheduled = await schedule_due(s)
        ran = []
        for _ in range(max_tasks):
            if self._stop.is_set():
                break
            r = await self.run_task()
            if r is None:
                break
            ran.append(r)
        await self.heartbeat()
        return {"worker_id": self.worker_id, "reclaimed": reclaimed, "scheduled": scheduled, "ran": ran}

    async def run_forever(self, poll_seconds: float = 5.0) -> None:
        async with self.Session() as s:
            await ensure_default_schedules(s)
        while not self._stop.is_set():
            result = await self.tick(max_tasks=10)  # tick writes the heartbeat
            if not result["ran"]:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
        await self.heartbeat()


async def main(argv: list[str] | None = None) -> int:
    import argparse

    from sqlalchemy.ext.asyncio import create_async_engine

    ap = argparse.ArgumentParser(description="Football OS worker")
    ap.add_argument("--once", action="store_true", help="one tick, then exit")
    ap.add_argument("--poll-seconds", type=float, default=5.0)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    worker = Worker(async_sessionmaker(engine, expire_on_commit=False), settings)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:  # pragma: no cover - non-POSIX
            pass
    try:
        if args.once:
            async with worker.Session() as s:
                await ensure_default_schedules(s)
            result = await worker.tick()
            log.info("tick: scheduled=%s ran=%s", result["scheduled"], [(r["job_type"], r["status"]) for r in result["ran"]])
        else:
            log.info("worker %s starting", worker.worker_id)
            await worker.run_forever(args.poll_seconds)
    finally:
        await engine.dispose()
    return 0
