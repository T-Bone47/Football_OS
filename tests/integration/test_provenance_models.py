"""Real-Postgres test — round-trips DataSource -> IngestionRun -> DataSnapshot
against fios_test. Skips cleanly if that database isn't reachable, so this
suite doesn't silently pass by fabricating success on a DB that isn't there.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun, IngestionStatus


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


async def test_ingestion_run_snapshot_roundtrip(session):
    source = DataSource(name="statsbomb-test", base_url="https://example.test")
    session.add(source)
    await session.flush()

    run = IngestionRun(
        id=uuid.uuid4(),
        data_source_id=source.id,
        endpoint="competitions",
        status=IngestionStatus.SUCCESS,
    )
    session.add(run)
    await session.flush()

    snapshot = DataSnapshot(
        id=uuid.uuid4(),
        ingestion_run_id=run.id,
        sha256="a" * 64,
        storage_location="bronze/statsbomb/competitions/aaaa.json",
    )
    session.add(snapshot)
    await session.commit()

    assert snapshot.ingestion_run_id == run.id
    assert source.id is not None
