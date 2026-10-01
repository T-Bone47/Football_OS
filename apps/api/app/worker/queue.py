"""Durable task queue on PostgreSQL (ops_worker_tasks), Phase 18 (R13).

- enqueue: idempotent by key (INSERT ... ON CONFLICT DO NOTHING).
- claim: one task at a time with FOR UPDATE SKIP LOCKED, so concurrent
  workers never take the same task; the claim sets a lease.
- A worker that dies keeps its task RUNNING only until the lease expires;
  reclaim_expired_leases then makes it claimable again (or DEAD when its
  attempts are spent).
- fail: exponential backoff (RETRY_SCHEDULED, not_before in the future)
  until max_attempts, then DEAD with an operational alert.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operations import WorkerTask

QUEUED, RUNNING, SUCCESS, RETRY, DEAD = "QUEUED", "RUNNING", "SUCCESS", "RETRY_SCHEDULED", "DEAD"
# Terminal: the handler ran and refused by policy (e.g. a provider without an
# AVAILABLE probe). Not a success, not retried; the next schedule tries again.
BLOCKED = "BLOCKED"
BACKOFF_BASE_S = 30.0
BACKOFF_CAP_S = 3600.0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def backoff_seconds(attempts: int, base: float = BACKOFF_BASE_S, cap: float = BACKOFF_CAP_S) -> float:
    """Delay before the next attempt after `attempts` failures: base * 2^(n-1), capped."""
    return min(cap, base * (2 ** max(0, attempts - 1)))


async def enqueue(session: AsyncSession, job_type: str, parameters: dict[str, Any], *,
                  idempotency_key: str | None = None, max_attempts: int = 3, not_before: datetime | None = None,
                  correlation_id: str | None = None, commit: bool = True) -> tuple[WorkerTask, bool]:
    """Returns (task, created). Enqueueing an existing key returns the
    existing task unchanged."""
    key = idempotency_key or f"{job_type}:{uuid.uuid4()}"
    stmt = insert(WorkerTask).values(
        id=uuid.uuid4(), job_type=job_type, parameters=parameters, status=QUEUED, attempts=0,
        max_attempts=max_attempts, not_before=not_before or now_utc(), idempotency_key=key,
        correlation_id=correlation_id or uuid.uuid4().hex, input_snapshot={"job_type": job_type, "parameters": parameters},
    ).on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(WorkerTask.id)
    created_id = (await session.execute(stmt)).scalar_one_or_none()
    task = (await session.execute(select(WorkerTask).where(WorkerTask.idempotency_key == key)
                                  .execution_options(populate_existing=True))).scalar_one()
    if commit:
        await session.commit()
    return task, created_id is not None


async def reclaim_expired_leases(session: AsyncSession, now: datetime | None = None) -> dict[str, list[str]]:
    """RUNNING tasks whose lease expired belonged to a worker that stopped.
    They become claimable again, or DEAD if no attempt is left."""
    now = now or now_utc()
    expired = (await session.execute(select(WorkerTask).where(
        WorkerTask.status == RUNNING, WorkerTask.lease_expires_at < now).with_for_update(skip_locked=True))).scalars().all()
    out: dict[str, list[str]] = {"requeued": [], "dead": []}
    for t in expired:
        note = f"lease expired at {t.lease_expires_at.isoformat()} (worker {t.worker_id})"
        if t.attempts >= t.max_attempts:
            t.status, t.error, t.completed_at = DEAD, note, now
            out["dead"].append(str(t.id))
        else:
            t.status, t.error, t.not_before = RETRY, note, now
            out["requeued"].append(str(t.id))
        t.worker_id, t.lease_expires_at = None, None
    await session.commit()
    return out


async def claim(session: AsyncSession, worker_id: str, lease_seconds: float = 300.0,
                job_types: list[str] | None = None, now: datetime | None = None) -> WorkerTask | None:
    now = now or now_utc()
    pick = (select(WorkerTask.id).where(WorkerTask.status.in_([QUEUED, RETRY]), WorkerTask.not_before <= now)
            .order_by(WorkerTask.not_before, WorkerTask.created_at).limit(1).with_for_update(skip_locked=True))
    if job_types:
        pick = pick.where(WorkerTask.job_type.in_(job_types))
    task_id = (await session.execute(pick)).scalar_one_or_none()
    if task_id is None:
        await session.rollback()
        return None
    await session.execute(update(WorkerTask).where(WorkerTask.id == task_id).values(
        status=RUNNING, attempts=WorkerTask.attempts + 1, worker_id=worker_id, started_at=now,
        lease_expires_at=now + timedelta(seconds=lease_seconds), error=None))
    task = (await session.execute(select(WorkerTask).where(WorkerTask.id == task_id)
                                  .execution_options(populate_existing=True))).scalar_one()
    await session.commit()
    return task


async def complete(session: AsyncSession, task: WorkerTask, output: dict[str, Any], worker_id: str,
                   status: str = SUCCESS) -> bool:
    """False when the lease was lost (another worker reclaimed the task)."""
    res = await session.execute(update(WorkerTask).where(
        WorkerTask.id == task.id, WorkerTask.status == RUNNING, WorkerTask.worker_id == worker_id).values(
        status=status, output_snapshot=output, completed_at=now_utc(), lease_expires_at=None))
    await session.commit()
    return res.rowcount == 1


async def fail(session: AsyncSession, task: WorkerTask, error: str, worker_id: str) -> str:
    """RETRY_SCHEDULED with backoff, or DEAD once attempts are spent. Returns the new status."""
    row = (await session.execute(select(WorkerTask).where(
        WorkerTask.id == task.id, WorkerTask.status == RUNNING, WorkerTask.worker_id == worker_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None:
        await session.rollback()
        return "LEASE_LOST"
    now = now_utc()
    row.error, row.lease_expires_at, row.worker_id = error[:4000], None, None
    if row.attempts >= row.max_attempts:
        row.status, row.completed_at = DEAD, now
    else:
        row.status, row.not_before = RETRY, now + timedelta(seconds=backoff_seconds(row.attempts))
    await session.commit()
    if row.status == DEAD:
        from app.phase17.alerts import raise_operational_alert

        await raise_operational_alert(
            session, category="WORKER_TASK_DEAD", severity="HIGH",
            title=f"Task {row.job_type} is DEAD after {row.attempts} attempts",
            evidence=[{"task_id": str(row.id), "job_type": row.job_type, "error": row.error[:500],
                       "correlation_id": row.correlation_id}],
            source="worker", dedup_scope=f"{row.job_type}:{row.idempotency_key}")
        await session.commit()
    return row.status


def pending_filter():
    return or_(WorkerTask.status == QUEUED, WorkerTask.status == RETRY)
