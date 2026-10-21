"""Shared integration test fixtures using transaction rollback for isolation.

This replaces the drop_all/create_all pattern with transaction rollback,
preserving migration-created tables (operational_records, ledger_entries, etc.).
"""
import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app


@pytest_asyncio.fixture
async def integration_db(postgres_url):
    """Create a fresh database engine and ensure tables exist via migrations.

    Tables are created once per session via migrations. Each test gets
    a transaction that gets rolled back for isolation.
    """
    engine = create_async_engine(postgres_url)

    # Verify tables exist (migrations should have run)
    from sqlalchemy import inspect
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda conn: inspect(conn).get_table_names())
        if "club_identities" not in tables:
            pytest.skip("Migration tables not found - run alembic upgrade head first")

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def integration_session(integration_db):
    """Create a session with transaction rollback for test isolation.

    Each test runs in a transaction that gets rolled back after completion,
    preserving migration-created tables and data.
    """
    async with integration_db.connect() as conn:
        transaction = await conn.begin()
        try:
            Session = async_sessionmaker(bind=conn, expire_on_commit=False)

            async def override_get_session():
                async with Session() as s:
                    yield s

            app.dependency_overrides[get_session] = override_get_session

            async with Session() as session:
                yield session

        finally:
            app.dependency_overrides.clear()
            await transaction.rollback()

    await integration_db.dispose()


@pytest_asyncio.fixture
async def integration_client(integration_session):
    """HTTP client using the integration session."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client