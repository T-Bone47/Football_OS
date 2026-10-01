"""Worker evidence: real processes, real database, a killed worker.

    DATABASE_URL=postgresql+asyncpg://.../fios_p17_live python scripts/evidence/worker_evidence.py

1. `python -m app.worker --once` (process A) installs the default schedules,
   enqueues what is due and runs it (probes and ingestion talk to the real
   providers; a blocked provider is recorded as such).
2. Kill drill: process B claims a task with a short lease and dies with
   os._exit(137) before completing it.
3. `python -m app.worker --once` (process C) reclaims the expired lease and
   completes the task; process B's completion can no longer land.
4. System health reports the worker from heartbeats.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from common import ROOT, write_evidence

API = ROOT / "apps" / "api"
KILLED_WORKER = """
import asyncio, os, sys
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.worker import queue

async def go():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await queue.enqueue(s, "metrics_flush", {"window_seconds": 900}, idempotency_key=sys.argv[1])
        task = await queue.claim(s, "killed-worker", lease_seconds=3, job_types=["metrics_flush"])
        print(task.id, flush=True)
    os._exit(137)  # SIGKILL-equivalent: no complete(), no fail(), no cleanup

asyncio.run(go())
"""


def run_worker_once(env: dict) -> dict:
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-m", "app.worker", "--once"], cwd=API, env=env, capture_output=True,
                       text=True, timeout=900)
    tick = [ln for ln in p.stderr.splitlines() if " tick: " in ln]
    return {"returncode": p.returncode, "elapsed_s": round(time.perf_counter() - t0, 1),
            "tick_log": tick[-1].split(" tick: ", 1)[1] if tick else None}


async def snapshot(url: str, since) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.models.operations import WorkerHeartbeat, WorkerTask
    from app.phase17.system_health import worker_status

    engine = create_async_engine(url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        tasks = (await s.execute(select(WorkerTask).where(WorkerTask.created_at >= since)
                                 .order_by(WorkerTask.created_at))).scalars().all()
        beats = (await s.execute(select(WorkerHeartbeat).where(WorkerHeartbeat.last_seen_at >= since))).scalars().all()
        from datetime import datetime, timezone

        health = await worker_status(s, datetime.now(timezone.utc))
    await engine.dispose()
    return {
        "tasks": [{"id": str(t.id), "job_type": t.job_type, "status": t.status, "attempts": t.attempts,
                   "worker_id": t.worker_id, "error": (t.error or "")[:200] or None,
                   "output_keys": sorted((t.output_snapshot or {}).keys())} for t in tasks],
        "heartbeats": [{"worker_id": b.worker_id, "tasks_completed": b.tasks_completed,
                        "tasks_failed": b.tasks_failed, "code_version": b.code_version} for b in beats],
        "worker_health": {k: health.get(k) for k in ("status", "alive_workers", "known_workers", "due_backlog",
                                                      "dead_tasks")},
    }


def main() -> int:
    from datetime import datetime, timezone

    url = os.environ["DATABASE_URL"]
    env = {**os.environ, "PYTHONPATH": str(API)}
    started = datetime.now(timezone.utc)
    out: dict = {"process_a": run_worker_once(env)}

    key = f"kill-drill-{int(time.time())}"
    b = subprocess.run([sys.executable, "-c", KILLED_WORKER, key], cwd=API, env=env, capture_output=True, text=True,
                       timeout=120)
    killed_task = b.stdout.strip()
    out["process_b_killed"] = {"returncode": b.returncode, "claimed_task": killed_task}
    time.sleep(4)  # the 3 s lease expires
    out["process_c"] = run_worker_once(env)
    snap = asyncio.run(snapshot(url, started))
    out.update(snap)
    drill = next((t for t in snap["tasks"] if t["id"] == killed_task), None)
    out["kill_drill"] = {"task": drill, "recovered": bool(drill and drill["status"] == "SUCCESS"
                                                          and drill["attempts"] == 2
                                                          and drill["worker_id"] != "killed-worker")}
    ok = (out["process_a"]["returncode"] == 0 and out["process_c"]["returncode"] == 0
          and b.returncode == 137 and out["kill_drill"]["recovered"]
          and snap["worker_health"]["status"] in ("HEALTHY", "DEGRADED"))
    write_evidence("worker_evidence", " ".join(sys.argv),
                   inputs={"database": url.rsplit("/", 1)[-1]}, outputs=out, status="VERIFIED" if ok else "FAILED")
    print({k: out[k] for k in ("process_a", "process_b_killed", "process_c", "kill_drill")})
    print("health", snap["worker_health"])
    print("tasks", [(t["job_type"], t["status"], t["attempts"]) for t in snap["tasks"]])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
