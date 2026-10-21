"""Durable ingestion checkpoints (Phase 4).

A checkpoint is the persisted answer to "what is the state of this exact provider
scope?". The scope key is derived from the provider parameters *minus* the page
number, so a checkpoint can never be reused for a different league, season or team.

Checkpoints make three guarantees:

* **Resumable** — a run that stops (quota, network, crash) continues from the last
  committed page instead of restarting the scope.
* **Bounded** — a scope is only COMPLETE when the provider's own declared total was
  reached. A partial scope stays PARTIAL and is reported as such.
* **Auditable** — every scope records what was seen, what was written, the provider's
  declared total and the last error.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.expansion import IngestionCheckpoint

# Checkpoint status vocabulary (mirrors the coverage vocabulary).
PENDING = "PENDING"
RUNNING = "RUNNING"
COMPLETE = "COMPLETE_FOR_DECLARED_SCOPE"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED_BY_PLAN"
FAILED = "FAILED"
UNKNOWN = "UNKNOWN_SCOPE"


def scope_key(params: dict[str, Any]) -> str:
    """Canonical, order-independent key for a provider scope (page excluded)."""
    filtered = {key: value for key, value in (params or {}).items() if key != "page"}
    return json.dumps(filtered, sort_keys=True, default=str)


@dataclass
class CheckpointState:
    provider: str
    entity_type: str
    scope_key: str
    page: int | None
    status: str
    records_seen: int
    records_written: int
    declared_total_pages: int | None
    last_error: str | None
    last_success_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "entity_type": self.entity_type,
            "scope_key": self.scope_key,
            "page": self.page,
            "status": self.status,
            "records_seen": self.records_seen,
            "records_written": self.records_written,
            "declared_total_pages": self.declared_total_pages,
            "last_error": self.last_error,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
        }


class CheckpointStore:
    """Read/write access to `ingestion_checkpoints`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, provider: str, entity_type: str, params: dict[str, Any]
    ) -> IngestionCheckpoint | None:
        key = scope_key(params)
        return (
            await self._session.execute(
                select(IngestionCheckpoint).where(
                    IngestionCheckpoint.provider == provider,
                    IngestionCheckpoint.entity_type == entity_type,
                    IngestionCheckpoint.scope_key == key,
                )
            )
        ).scalar_one_or_none()

    async def record(
        self,
        *,
        provider: str,
        entity_type: str,
        params: dict[str, Any],
        status: str,
        page: int | None = None,
        records_seen: int = 0,
        records_written: int = 0,
        declared_total_pages: int | None = None,
        last_error: str | None = None,
        last_run_id: Any = None,
        competition: str | None = None,
        season: str | None = None,
    ) -> IngestionCheckpoint:
        key = scope_key(params)
        row = (
            await self._session.execute(
                select(IngestionCheckpoint).where(
                    IngestionCheckpoint.provider == provider,
                    IngestionCheckpoint.entity_type == entity_type,
                    IngestionCheckpoint.scope_key == key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = IngestionCheckpoint(
                provider=provider,
                entity_type=entity_type,
                scope_key=key,
                competition=competition,
                season=season,
            )
            self._session.add(row)

        row.status = status
        if page is not None:
            row.page = page
        row.records_seen = records_seen
        row.records_written = records_written
        if declared_total_pages is not None:
            row.declared_total_pages = declared_total_pages
        row.last_error = last_error
        if last_run_id is not None:
            row.last_run_id = last_run_id
        if status in (COMPLETE, PARTIAL):
            row.last_success_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        return row

    async def state(
        self, provider: str, entity_type: str, params: dict[str, Any]
    ) -> CheckpointState | None:
        row = await self.get(provider, entity_type, params)
        if row is None:
            return None
        return CheckpointState(
            provider=row.provider,
            entity_type=row.entity_type,
            scope_key=row.scope_key,
            page=row.page,
            status=row.status,
            records_seen=row.records_seen,
            records_written=row.records_written,
            declared_total_pages=row.declared_total_pages,
            last_error=row.last_error,
            last_success_at=row.last_success_at,
        )

    async def all_for(self, provider: str | None = None) -> list[CheckpointState]:
        stmt = select(IngestionCheckpoint)
        if provider:
            stmt = stmt.where(IngestionCheckpoint.provider == provider)
        rows = (await self._session.execute(stmt.order_by(IngestionCheckpoint.id))).scalars().all()
        return [
            CheckpointState(
                provider=row.provider,
                entity_type=row.entity_type,
                scope_key=row.scope_key,
                page=row.page,
                status=row.status,
                records_seen=row.records_seen,
                records_written=row.records_written,
                declared_total_pages=row.declared_total_pages,
                last_error=row.last_error,
                last_success_at=row.last_success_at,
            )
            for row in rows
        ]
