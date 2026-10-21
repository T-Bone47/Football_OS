"""Real-Postgres test for the capability registry (needs fios_test —
skips cleanly if unreachable, same pattern as test_provenance_models.py).

Isolation: this file used to create the schema with `create_all` and drop it
with `drop_all` in teardown, which removed the migrated tables from the shared
disposable test database and broke the suites that ran afterwards. It now uses
the shared transaction-rollback fixture and states its precondition explicitly.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models.capability import ProviderCapability
from app.ingestion.capability_registry import CapabilityRegistry


@pytest_asyncio.fixture
async def session(integration_session):
    """The shared transaction-rollback session (no create_all / drop_all)."""
    yield integration_session


async def test_unknown_capability_is_not_supported(session):
    registry = CapabilityRegistry(session)
    assert await registry.supports("statsbomb", "nonexistent-resource") is False


async def test_mark_verified_then_supports(session):
    registry = CapabilityRegistry(session)
    # Deterministic precondition: this scope must not be marked verified by
    # whatever a previous test left in the shared database.
    await session.execute(
        delete(ProviderCapability).where(
            ProviderCapability.provider == "statsbomb",
            ProviderCapability.resource == "competitions",
        )
    )
    await session.flush()
    assert await registry.supports("statsbomb", "competitions") is False

    await registry.mark_verified("statsbomb", "competitions")

    assert await registry.supports("statsbomb", "competitions") is True
