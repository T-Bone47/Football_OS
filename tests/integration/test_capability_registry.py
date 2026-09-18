"""Real-Postgres test for the capability registry (needs fios_test —
skips cleanly if unreachable, same pattern as test_provenance_models.py)."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.ingestion.capability_registry import CapabilityRegistry


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


async def test_unknown_capability_is_not_supported(session):
    registry = CapabilityRegistry(session)
    assert await registry.supports("statsbomb", "nonexistent-resource") is False


async def test_mark_verified_then_supports(session):
    registry = CapabilityRegistry(session)
    assert await registry.supports("statsbomb", "competitions") is False

    await registry.mark_verified("statsbomb", "competitions")

    assert await registry.supports("statsbomb", "competitions") is True
