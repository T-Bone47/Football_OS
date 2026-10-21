"""Ingestion runner (architecture doc §17/§18) — the IngestionRun table
existed in Slice 1 but nothing drove it. This is what drives it:
QUEUED -> RUNNING -> (fetch -> snapshot -> validate) -> SUCCESS/FAILED.

The provider does NOT own the database lifecycle (§18) — it only knows how
to fetch bytes. Everything about runs/snapshots/status lives here.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun, IngestionStatus
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.snapshot_store import SnapshotStore
from app.providers.registry import ProviderRegistry
from app.validation.validate import validate_snapshot


@dataclass
class PaginatedIngestionResult:
    """Page-level truth for a provider endpoint that paginates.

    `status` is only COMPLETE when the provider's declared total page count
    was reached; a successful first page is never enough.
    """

    provider: str
    resource: str
    parameters: dict[str, Any]
    first_page: int
    last_page: int
    pages_requested: int = 0
    pages_succeeded: int = 0
    records_fetched: int = 0
    total_pages: int | None = None
    status: str = "UNKNOWN"
    stop_reason: str = "NOT_STARTED"
    errors: list[str] = field(default_factory=list)
    plan_page_max: int | None = None
    plan_limit_message: str | None = None
    resumed_from_page: int | None = None
    runs: list[Any] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "resource": self.resource,
            "parameters": self.parameters,
            "first_page": self.first_page,
            "last_page": self.last_page,
            "pages_requested": self.pages_requested,
            "pages_succeeded": self.pages_succeeded,
            "records_fetched": self.records_fetched,
            "total_pages": self.total_pages,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "errors": self.errors,
            "plan_page_max": self.plan_page_max,
            "plan_limit_message": self.plan_limit_message,
            "resumed_from_page": self.resumed_from_page,
        }


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status))


def _payload_paging(content: bytes) -> tuple[int | None, int | None, int | None, int]:
    """Return (paging.current, paging.total, results, response_length).

    Missing or malformed metadata stays None — the caller must not assume
    completeness from a single successful response.
    """
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        return None, None, None, 0
    if isinstance(payload, list):
        # Non-enveloped provider payloads (for example a StatsBomb list) still
        # have a measurable record count.
        return None, None, len(payload), len(payload)
    if not isinstance(payload, dict):
        return None, None, None, 0
    response = payload.get("response")
    response_len = len(response) if isinstance(response, list) else 0
    results = payload.get("results")
    if not isinstance(results, int):
        results = None
        if response_len:
            results = response_len
        else:
            for key in (
                "competitions",
                "matches",
                "teams",
                "players",
                "fixtures",
                "events",
            ):
                if isinstance(payload.get(key), list):
                    results = len(payload[key])
                    break
            if results is None:
                list_values = [v for v in payload.values() if isinstance(v, list)]
                if len(list_values) == 1:
                    results = len(list_values[0])
    paging = payload.get("paging")
    current = total = None
    if isinstance(paging, dict):
        if isinstance(paging.get("current"), int):
            current = paging["current"]
        if isinstance(paging.get("total"), int):
            total = paging["total"]
    return current, total, results, response_len


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
        await self._session.flush()

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

        sha256, storage_location = await self._store.save(provider_name, resource, raw)
        validation_status, validation_errors = validate_snapshot(provider_name, resource, raw.content)

        snapshot = DataSnapshot(
            ingestion_run_id=run.id,
            sha256=sha256,
            storage_location=storage_location,
            validation_status=validation_status,
            validation_errors=validation_errors,
            size_bytes=len(raw.content),
        )
        self._session.add(snapshot)

        # Bytes are always kept (validation never gates storage, only what we record about them), but
        # the run is SUCCESS only when the snapshot is not known-invalid, and capability evidence is
        # only recorded for payloads that did not fail validation. record_count is measured from the
        # provider envelope (`results`, falling back to the length of `response`) or stays NULL.
        invalid = str(getattr(validation_status, "value", validation_status)) == "INVALID"
        run.status = IngestionStatus.PARTIAL if invalid else IngestionStatus.SUCCESS
        if invalid:
            run.error = "snapshot failed schema validation; see data_snapshots.validation_errors"
        current_page, total_pages, measured_results, response_len = _payload_paging(
            raw.content
        )
        run.record_count = measured_results
        # Transient (not persisted): lets run_paginated decide the next page
        # without re-reading the Bronze file in the same process.
        run._paging_metadata = {
            "current": current_page,
            "total": total_pages,
            "response_len": response_len,
        }
        run.finished_at = datetime.now(timezone.utc)

        if self._capabilities is not None and not invalid:
            await self._capabilities.mark_verified(provider_name, resource)

        await self._session.commit()

        return run

    async def run_paginated(
        self,
        provider_name: str,
        resource: str,
        *,
        start_page: int = 1,
        max_pages: int | None = None,
        request_interval_seconds: float | None = None,
        resume: bool = False,
        **params: Any,
    ) -> PaginatedIngestionResult:
        """Fetch every page the provider declares, one snapshot/run per page.

        Each page is committed before the next request, so an interrupted run
        leaves completed pages durable and resumable. The provider's own
        `paging.total` is the only completeness signal accepted.
        """
        if start_page < 1:
            raise ValueError("start_page must be >= 1")
        settings = get_settings()
        if max_pages is None:
            max_pages = (
                settings.api_football_max_pages_per_run
                if provider_name == "api-football"
                else 200
            )
        if request_interval_seconds is None:
            request_interval_seconds = (
                settings.api_football_page_delay_seconds
                if provider_name == "api-football"
                else 0.0
            )

        result = PaginatedIngestionResult(
            provider=provider_name,
            resource=resource,
            parameters=dict(params),
            first_page=start_page,
            last_page=start_page - 1,
        )

        if resume:
            last_page, known_total = await self.last_completed_state(
                provider_name, resource, **params
            )
            if last_page:
                result.resumed_from_page = last_page
            if known_total is not None and last_page >= known_total:
                result.first_page = last_page
                result.last_page = last_page
                result.total_pages = known_total
                result.status = "COMPLETE"
                result.stop_reason = "ALREADY_COMPLETE"
                return result
            if last_page >= start_page:
                result.first_page = last_page + 1
                result.last_page = last_page

        had_prior_pages = (result.resumed_from_page or 0) > 0
        page = result.first_page
        while result.pages_requested < max_pages:
            run = await self.run(provider_name, resource, page=page, **params)
            result.runs.append(run)
            result.pages_requested += 1
            result.last_page = page

            if _status_value(run.status) == "FAILED":
                error = run.error or f"page {page} failed"
                result.errors.append(error)
                plan_match = re.search(
                    r"maximum value of (\d+) for the Page parameter",
                    error,
                    flags=re.IGNORECASE,
                )
                if plan_match:
                    result.plan_page_max = int(plan_match.group(1))
                    result.plan_limit_message = error
                    result.stop_reason = "PROVIDER_PLAN_LIMIT"
                else:
                    result.stop_reason = "PROVIDER_FAILURE"
                break

            result.pages_succeeded += 1
            if run.record_count:
                result.records_fetched += run.record_count

            metadata = getattr(run, "_paging_metadata", {}) or {}
            current = metadata.get("current")
            total = metadata.get("total")
            response_len = metadata.get("response_len", 0)
            if total is not None:
                result.total_pages = total

            if response_len == 0:
                result.stop_reason = "EMPTY_PAGE"
                break
            if total is None:
                # No declared page count: a successful response proves one
                # page, never the whole dataset.
                result.stop_reason = "PAGING_TOTAL_UNKNOWN"
                break
            if (current is not None and current >= total) or page >= total:
                result.stop_reason = "PROVIDER_REPORTED_LAST_PAGE"
                break

            page += 1
            if request_interval_seconds > 0:
                await asyncio.sleep(request_interval_seconds)
        else:
            result.stop_reason = "MAX_PAGES_REACHED"

        if result.stop_reason == "PROVIDER_PLAN_LIMIT":
            result.status = "BLOCKED_BY_PLAN"
        elif result.pages_succeeded == 0 and not had_prior_pages:
            result.status = "FAILED"
        elif result.total_pages is None:
            result.status = "UNKNOWN"
        elif result.last_page >= result.total_pages:
            result.status = "COMPLETE"
        else:
            result.status = "PARTIAL"

        return result

    @staticmethod
    def _same_scope(parameters: dict[str, Any], expected: dict[str, Any]) -> bool:
        actual = {
            key: str(value) for key, value in (parameters or {}).items() if key != "page"
        }
        wanted = {key: str(value) for key, value in expected.items()}
        return actual == wanted

    async def last_completed_state(
        self, provider_name: str, resource: str, **params: Any
    ) -> tuple[int, int | None]:
        """Return (last successfully completed page, provider's declared total).

        Used by `resume=True`. Only runs with the same non-page parameters
        count, so a different league/season never resumes the wrong scope.
        """
        rows = (
            await self._session.execute(
                select(IngestionRun)
                .join(DataSource, DataSource.id == IngestionRun.data_source_id)
                .where(
                    DataSource.name == provider_name,
                    IngestionRun.endpoint == resource,
                )
                .order_by(IngestionRun.started_at.asc())
            )
        ).scalars().all()

        last_page = 0
        last_run_id = None
        for run in rows:
            parameters = dict(run.parameters or {})
            page = parameters.get("page")
            if not isinstance(page, int) or not self._same_scope(parameters, params):
                continue
            if _status_value(run.status) in ("SUCCESS", "PARTIAL"):
                if page >= last_page:
                    last_page = page
                    last_run_id = run.id

        declared_total: int | None = None
        if last_run_id is not None:
            snapshot = (
                await self._session.execute(
                    select(DataSnapshot)
                    .where(DataSnapshot.ingestion_run_id == last_run_id)
                    .order_by(DataSnapshot.retrieved_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snapshot is not None:
                try:
                    _, declared_total, _, _ = _payload_paging(
                        Path(snapshot.storage_location).read_bytes()
                    )
                except OSError:
                    declared_total = None

        return last_page, declared_total
