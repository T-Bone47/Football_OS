"""End-to-end ingestion lifecycle against real Postgres. The StatsBomb path
is genuinely live (network + real data); API-Football/football-data.org
paths use a mocked provider registry, since those two domains aren't
reachable from wherever this suite runs without real keys (see
docs/DEVELOPMENT_STATUS.md) — LIVE_PROVIDER_TESTS gates the real versions.
"""
import os

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.provenance import IngestionStatus
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.service import IngestionService
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.providers.registry import ProviderRegistry
from app.providers.statsbomb import StatsBombProvider


@pytest_asyncio.fixture
async def session(postgres_url):
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"fios_test not reachable: {exc}")
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_statsbomb_run_reaches_success(session, tmp_path):
    registry = ProviderRegistry()
    registry.register("statsbomb", StatsBombProvider)
    # No capability_registry here on purpose: this test proves the
    # fetch -> snapshot -> validate -> SUCCESS path. The capability gate
    # (which would correctly block this in a fresh, unseeded schema) has
    # its own test right below.
    service = IngestionService(
        session=session,
        provider_registry=registry,
        snapshot_store=LocalFilesystemSnapshotStore(tmp_path),
        capability_registry=None,
    )

    run = await service.run("statsbomb", "competitions")

    assert run.status == IngestionStatus.SUCCESS
    assert run.record_count == 1
    assert run.error is None


async def test_capability_check_blocks_unsupported_resource(session, tmp_path):
    registry = ProviderRegistry()
    registry.register("statsbomb", StatsBombProvider)
    capabilities = CapabilityRegistry(session)
    # Nothing seeded in this throwaway schema, so everything is unsupported
    # until mark_verified has run once — this proves the gate actually gates.
    service = IngestionService(
        session=session,
        provider_registry=registry,
        snapshot_store=LocalFilesystemSnapshotStore(tmp_path),
        capability_registry=capabilities,
    )

    run = await service.run("statsbomb", "competitions")

    assert run.status == IngestionStatus.FAILED
    assert "does not support" in run.error


async def test_provider_failure_marks_run_failed_not_a_crash(session, tmp_path):
    class AlwaysFailsProvider:
        name = "flaky"

        async def fetch(self, resource, **params):
            raise httpx.ConnectError("simulated network failure")

        async def close(self):
            pass

    registry = ProviderRegistry()
    registry.register("flaky", AlwaysFailsProvider)
    service = IngestionService(
        session=session,
        provider_registry=registry,
        snapshot_store=LocalFilesystemSnapshotStore(tmp_path),
        capability_registry=None,  # no gate — testing the fetch-failure path specifically
    )

    run = await service.run("flaky", "anything")

    assert run.status == IngestionStatus.FAILED
    assert "ConnectError" in run.error


@pytest.mark.skipif(
    not (os.environ.get("LIVE_PROVIDER_TESTS") and os.environ.get("API_FOOTBALL_KEY")),
    reason="set LIVE_PROVIDER_TESTS=1 and API_FOOTBALL_KEY to run against the real API-Football API",
)
async def test_api_football_live(session, tmp_path):
    from app.providers.api_football import ApiFootballProvider

    registry = ProviderRegistry()
    registry.register("api-football", ApiFootballProvider)
    capabilities = CapabilityRegistry(session)
    await capabilities.mark_verified("api-football", "status")
    service = IngestionService(
        session=session,
        provider_registry=registry,
        snapshot_store=LocalFilesystemSnapshotStore(tmp_path),
        capability_registry=capabilities,
    )
    run = await service.run("api-football", "status")
    assert run.status == IngestionStatus.SUCCESS
