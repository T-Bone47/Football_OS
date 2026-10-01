"""Controlled live ingestion (§5-§9, §39).

One job = one provider request:

    budget check -> IngestionService (fetch -> Bronze -> validate)
    -> contract check -> payload quality -> Silver -> Silver quality

Outcomes recorded on ops_job_runs:
- SUCCESS            Bronze captured, contract OK/WARN, quality not FAIL, Silver written
- INGESTION_BLOCKED  Bronze captured, contract drift: Silver untouched
- QUALITY_BLOCKED    Bronze captured, payload quality FAIL: Silver untouched
- RATE_LIMIT_DEFERRED no request sent: budget exhausted
- FAILED             provider/network/storage failure (IngestionRun says why)

There is no path that returns SUCCESS without a provider response.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Club, CompetitionSeason, Match, MatchEvent, MatchLineup, Player
from app.db.models.operations import JobRun
from app.db.models.provenance import DataSnapshot, DataSource, IngestionStatus
from app.ingestion.service import IngestionService
from app.ingestion.snapshot_store import SnapshotStore
from app.normalization.service import NormalizationService
from app.phase17 import ScheduleClass
from app.phase17.alerts import raise_operational_alert
from app.phase17.audit import append_event
from app.phase17.contract_drift import ContractStatus, check_contract, get_registered_types, register_contract
from app.phase17.data_quality import assess_payload, assess_silver
from app.phase17.rate_governor import RateGovernor, get_rate_governor, instrumented_client
from app.providers.registry import ProviderRegistry
from app.providers.statsbomb import StatsBombProvider

PROVIDER_LICENSES = {
    "statsbomb": ("https://github.com/statsbomb/open-data", "CC BY-NC-SA 4.0 (StatsBomb Open Data; attribution required)"),
    "api-football": ("https://v3.football.api-sports.io", "Commercial (API-Sports terms of service)"),
    "football-data-org": ("https://api.football-data.org/v4", "football-data.org terms of service"),
}


@dataclass(frozen=True)
class ScheduleSpec:
    """§7: frequency follows what the provider can actually deliver."""

    job_name: str
    provider: str
    resource: str
    schedule_class: ScheduleClass
    rationale: str


SCHEDULES: tuple[ScheduleSpec, ...] = (
    ScheduleSpec("statsbomb_competitions_index", "statsbomb", "competitions", ScheduleClass.WEEKLY,
                 "Open Data is an archive updated irregularly (competitions.json carries match_updated); "
                 "weekly detects additions without polling an unchanging file."),
    ScheduleSpec("statsbomb_season_matches", "statsbomb", "matches", ScheduleClass.SEASONAL,
                 "Archived seasons are complete; refresh only when the competitions index shows a newer match_updated."),
    ScheduleSpec("statsbomb_match_lineups", "statsbomb", "lineups", ScheduleClass.ON_DEMAND,
                 "Per-match files; fetched when a match enters scope."),
    ScheduleSpec("statsbomb_match_events", "statsbomb", "events", ScheduleClass.ON_DEMAND,
                 "3-4 MB per match; fetched for matches a workflow needs, never bulk-polled."),
    ScheduleSpec("api_football_fixtures", "api-football", "fixtures", ScheduleClass.LIVE,
                 "Would support near-live polling within plan quota. BLOCKED here: host unreachable, no key."),
    ScheduleSpec("api_football_transfers", "api-football", "transfers", ScheduleClass.DAILY,
                 "Transfer records change at most daily. BLOCKED here: host unreachable, no key."),
)


@dataclass
class JobResult:
    job_id: str
    status: str
    provider: str
    resource: str
    params: dict[str, Any]
    ingestion_run_id: str | None = None
    snapshot_id: str | None = None
    snapshot_sha256: str | None = None
    storage_location: str | None = None
    contract: dict[str, Any] | None = None
    payload_quality: dict[str, Any] | None = None
    silver_quality: dict[str, Any] | None = None
    silver: dict[str, Any] | None = None
    records: int | None = None
    errors: list[str] = field(default_factory=list)
    latency_ms: float | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


async def silver_counts(session: AsyncSession) -> dict[str, int]:
    out = {}
    for name, model in (("matches", Match), ("clubs", Club), ("players", Player),
                        ("match_lineups", MatchLineup), ("match_events", MatchEvent),
                        ("competition_seasons", CompetitionSeason)):
        out[name] = (await session.execute(select(func.count()).select_from(model))).scalar_one()
    return out


class SnapshotIntegrityError(RuntimeError):
    """Stored Bronze bytes no longer hash to the recorded SHA-256."""


def read_verified_snapshot(storage_location: str, expected_sha256: str) -> bytes:
    if storage_location.startswith("s3://"):
        raise NotImplementedError("Silver promotion reads Bronze from the local store only (see PHASE_17_LIVE_DATA_OPERATIONS.md)")
    data = Path(storage_location).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise SnapshotIntegrityError(f"Bronze snapshot {expected_sha256} now hashes to {actual}")
    return data


async def replay_snapshot(session: AsyncSession, snapshot_id: uuid.UUID) -> dict[str, Any]:
    """§40: deterministic replay starts at a captured Bronze snapshot. The
    bytes are re-verified, then normalized with the same code path as live
    ingestion. No provider request is made."""
    snapshot = await session.get(DataSnapshot, snapshot_id)
    if snapshot is None:
        raise LookupError(f"snapshot {snapshot_id} not found")
    read_verified_snapshot(snapshot.storage_location, snapshot.sha256)
    return await NormalizationService(session).normalize_snapshot(snapshot_id)


async def _ensure_data_source_metadata(session: AsyncSession, provider: str) -> None:
    row = (await session.execute(select(DataSource).where(DataSource.name == provider))).scalar_one_or_none()
    if row is not None and provider in PROVIDER_LICENSES and not row.license:
        row.base_url, row.license = PROVIDER_LICENSES[provider]


class LiveIngestionRunner:
    def __init__(
        self,
        session: AsyncSession,
        snapshot_store: SnapshotStore,
        governor: RateGovernor | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self._session = session
        self._store = snapshot_store
        self._governor = governor or get_rate_governor()
        self._transport = transport
        self._registry = provider_registry

    def _registry_for(self, provider: str) -> tuple[ProviderRegistry, httpx.AsyncClient | None]:
        if self._registry is not None:
            return self._registry, None
        registry = ProviderRegistry()
        client = instrumented_client(self._governor, provider, transport=self._transport)
        if provider == "statsbomb":
            registry.register("statsbomb", lambda: StatsBombProvider(client=client))
        else:
            from app.providers.registry import default_registry  # API-Football etc. need credentials
            return default_registry, client
        return registry, client

    async def run_job(
        self,
        provider: str,
        resource: str,
        params: dict[str, Any] | None = None,
        job_name: str | None = None,
        schedule_class: ScheduleClass = ScheduleClass.ON_DEMAND,
        normalize: bool = True,
    ) -> JobResult:
        params = params or {}
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        job = JobRun(job_name=job_name or f"{provider}:{resource}", schedule_class=schedule_class.value,
                     provider=provider, resource=resource, parameters=params, status="RUNNING",
                     started_at=started)
        self._session.add(job)
        await self._session.commit()  # visible while running; see reap_stale_jobs
        result = JobResult(job_id=str(job.id), status="RUNNING", provider=provider, resource=resource,
                           params=params, started_at=started.isoformat())

        if not self._governor.headroom(provider):
            self._governor.record_deferral(provider)
            return await self._finish(job, result, "RATE_LIMIT_DEFERRED", t0,
                                      [f"budget exhausted: {self._governor.window_counts(provider)} "
                                       f"(min, hour) vs {self._governor.budget(provider)}"])

        registry, client = self._registry_for(provider)
        try:
            service = IngestionService(self._session, registry, self._store)
            run = await service.run(provider, resource, **params)
            self._governor.record_fetch(provider)
        finally:
            if client is not None:
                await client.aclose()

        result.ingestion_run_id = str(run.id)
        job.ingestion_run_id = run.id
        await _ensure_data_source_metadata(self._session, provider)
        if run.status != IngestionStatus.SUCCESS:
            if run.error and ("Network" in run.error or "Timeout" in run.error or "Connect" in run.error):
                self._governor.record_request(provider, None, None)
            if run.error and "ProviderRateLimitError" in run.error:
                self._governor.record_rate_limited(provider)
            return await self._finish(job, result, "FAILED", t0, [run.error or "ingestion failed"])

        snapshot = (await self._session.execute(
            select(DataSnapshot).where(DataSnapshot.ingestion_run_id == run.id))).scalar_one()
        result.snapshot_id = str(snapshot.id)
        result.snapshot_sha256 = snapshot.sha256
        result.storage_location = snapshot.storage_location
        job.snapshot_sha256 = snapshot.sha256

        try:
            payload = json.loads(read_verified_snapshot(snapshot.storage_location, snapshot.sha256))
        except SnapshotIntegrityError as exc:
            return await self._finish(job, result, "FAILED", t0, [f"BRONZE_INTEGRITY_FAILED: {exc}"])
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return await self._finish(job, result, "QUALITY_BLOCKED", t0, [f"Bronze payload is not JSON: {exc}"])

        registered = await get_registered_types(self._session, provider, resource)
        contract = check_contract(provider, resource, payload, registered)
        if registered is None and contract.status in (ContractStatus.CONTRACT_OK, ContractStatus.CONTRACT_WARN):
            await register_contract(self._session, provider, resource, payload, snapshot.sha256)
        snapshot.schema_version = contract.observed_fingerprint[:32] if contract.observed_fingerprint else None
        result.contract = contract.to_dict()
        result.records = len(payload) if isinstance(payload, list) else 1
        job.records = result.records

        quality = assess_payload(provider, resource, payload, params, contract, snapshot.sha256)
        await quality.persist(self._session)
        result.payload_quality = quality.to_dict()

        if contract.status == ContractStatus.INGESTION_BLOCKED:
            await append_event(self._session, "INGESTION_BLOCKED", "system:live_ingestion",
                               f"{provider}/{resource}", {"snapshot": snapshot.sha256, "findings": contract.findings})
            return await self._finish(job, result, "INGESTION_BLOCKED", t0,
                                      [f"contract drift: {f}" for f in contract.findings if f["severity"] == "BLOCK"])
        if quality.overall.value == "FAIL":
            return await self._finish(job, result, "QUALITY_BLOCKED", t0,
                                      [f"{c.name}: {c.detail} ({c.affected_records})" for c in quality.checks
                                       if c.status.value == "FAIL"])

        if normalize and resource in ("matches", "lineups", "events"):
            # Persist Bronze-side evidence (contract, quality report) before
            # touching Silver, so a Silver rollback cannot erase it.
            await self._session.commit()
            before = await silver_counts(self._session)
            snapshot_id = snapshot.id
            try:
                norm = await NormalizationService(self._session).normalize_snapshot(snapshot_id)
            except Exception as exc:  # noqa: BLE001 — a Silver failure rolls back; Bronze and the run are kept
                await self._session.rollback()
                job = await self._session.get(JobRun, uuid.UUID(result.job_id))
                return await self._finish(job, result, "FAILED", t0,
                                          [f"SILVER_NORMALIZATION_FAILED: {type(exc).__name__}: {str(exc)[:300]}"])
            after = await silver_counts(self._session)
            result.silver = {"normalization": norm, "before": before, "after": after,
                             "delta": {k: after[k] - before[k] for k in after}}
            if resource == "matches" and isinstance(payload, list) and payload:
                cs_id = (await self._session.execute(
                    select(Match.competition_season_id).where(
                        Match.provider == provider, Match.provider_fixture_id == str(payload[0]["match_id"])))).scalar_one_or_none()
                if cs_id is not None:
                    silver_report = await assess_silver(self._session, provider, cs_id)
                    await silver_report.persist(self._session)
                    result.silver_quality = silver_report.to_dict()

        return await self._finish(job, result, "SUCCESS", t0, [])

    async def _finish(self, job: JobRun, result: JobResult, status: str, t0: float, errors: list[str]) -> JobResult:
        finished = datetime.now(timezone.utc)
        job.status = status
        job.finished_at = finished
        job.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        job.errors = errors
        result.status = status
        result.errors = errors
        result.latency_ms = job.latency_ms
        result.finished_at = finished.isoformat()
        if status in ("FAILED", "INGESTION_BLOCKED", "QUALITY_BLOCKED"):
            error_class = (errors[0].split(":", 1)[0] if errors else status)[:48]
            await raise_operational_alert(
                self._session, category=f"INGESTION_{status}", severity="HIGH",
                title=f"{job.provider}/{job.resource} ingestion {status}: {error_class}",
                evidence=[{"job_id": result.job_id, "ingestion_run_id": result.ingestion_run_id,
                           "snapshot_sha256": result.snapshot_sha256, "params": result.params, "errors": errors[:3]}],
                source="live_ingestion", dedup_scope=f"{job.provider}:{job.resource}:{error_class}")
        await self._session.commit()
        return result


async def reap_stale_jobs(session: AsyncSession, older_than_s: float = 3600.0) -> list[str]:
    """Marks RUNNING jobs whose worker has gone (started more than
    `older_than_s` ago, never finished) as FAILED: WORKER_LOST. Silver is
    unaffected: normalization commits once per payload, so a lost worker
    leaves either the full payload or none of it."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_s)
    rows = (await session.execute(select(JobRun).where(JobRun.status == "RUNNING", JobRun.started_at < cutoff))).scalars().all()
    for job in rows:
        job.status = "FAILED"
        job.finished_at = datetime.now(timezone.utc)
        job.errors = list(job.errors or []) + ["WORKER_LOST: job never finished; marked failed by reaper"]
        await append_event(session, "JOB_REAPED", "system:reaper", str(job.id), {"job": job.job_name})
    await session.commit()
    return [str(j.id) for j in rows]
