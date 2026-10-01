"""Ingestion runner (architecture doc §17/§18) — the IngestionRun table
existed in Slice 1 but nothing drove it. This is what drives it:
QUEUED -> RUNNING -> (fetch -> snapshot -> validate) -> SUCCESS/FAILED.

The provider does NOT own the database lifecycle (§18) — it only knows how
to fetch bytes. Everything about runs/snapshots/status lives here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun, IngestionStatus
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.snapshot_store import SnapshotStore
from app.providers.registry import ProviderRegistry
from app.validation.validate import validate_snapshot


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        provider_registry: ProviderRegistry,
        snapshot_store: SnapshotStore,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self._session = session
        self._providers = provider_registry
        self._store = snapshot_store
        self._capabilities = capability_registry

    async def _get_or_create_data_source(self, name: str) -> DataSource:
        row = (
            await self._session.execute(select(DataSource).where(DataSource.name == name))
        ).scalar_one_or_none()
        if row is None:
            row = DataSource(name=name)
            self._session.add(row)
            await self._session.flush()
        return row

    async def run(self, provider_name: str, resource: str, **params: Any) -> IngestionRun:
        data_source = await self._get_or_create_data_source(provider_name)

        run = IngestionRun(
            data_source_id=data_source.id,
            endpoint=resource,
            parameters=params,
            status=IngestionStatus.QUEUED,
        )
        self._session.add(run)
        await self._session.flush()

        run.status = IngestionStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        # Commit RUNNING before the network call so a worker that dies
        # mid-request leaves a visible, reapable run instead of nothing.
        await self._session.commit()

        if self._capabilities is not None:
            supported = await self._capabilities.supports(provider_name, resource)
            if not supported:
                run.status = IngestionStatus.FAILED
                run.error = f"capability registry: '{provider_name}' does not support resource '{resource}'"
                run.finished_at = datetime.now(timezone.utc)
                await self._session.commit()
                return run

        try:
            provider = self._providers.get(provider_name)
        except KeyError as exc:
            run.status = IngestionStatus.FAILED
            run.error = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            await self._session.commit()
            return run

        try:
            raw = await provider.fetch(resource, **params)
        except Exception as exc:  # noqa: BLE001 — any provider/network failure lands the run as FAILED, not a crash
            run.status = IngestionStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            await self._session.commit()
            return run
        finally:
            await provider.close()

        try:
            sha256, storage_location = await self._store.save(provider_name, resource, raw)
        except Exception as exc:  # noqa: BLE001 — storage outage must land as FAILED, never leave the run RUNNING
            run.status = IngestionStatus.FAILED
            run.error = f"SnapshotStoreError: {type(exc).__name__}: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            await self._session.commit()
            return run
        validation_status, validation_errors = validate_snapshot(provider_name, resource, raw.content)

        snapshot = DataSnapshot(
            ingestion_run_id=run.id,
            sha256=sha256,
            storage_location=storage_location,
            validation_status=validation_status,
            validation_errors=validation_errors,
            size_bytes=len(raw.content),
            provider_retrieved_at=raw.retrieved_at,
            http_status=raw.status_code,
            content_type=raw.content_type,
            source_url=raw.source_url,
        )
        self._session.add(snapshot)

        run.status = IngestionStatus.SUCCESS
        run.record_count = 1
        run.finished_at = datetime.now(timezone.utc)

        if self._capabilities is not None:
            await self._capabilities.mark_verified(provider_name, resource)

        await self._session.commit()

        return run
