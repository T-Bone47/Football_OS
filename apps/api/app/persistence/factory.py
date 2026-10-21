"""Backend selection for operational state.

OPERATIONAL_STATE_BACKEND = memory (default) | postgres. `memory` loses everything on restart, so ENVIRONMENT=production
refuses it unless ALLOW_EPHEMERAL_STATE=1 is set deliberately. `postgres` needs migration 0015 (`alembic upgrade head`).
"""
from __future__ import annotations

import os
from functools import lru_cache

from app.persistence.stores import CollectionStore, LedgerStore, MemoryCollectionStore, MemoryLedgerStore


def build_stores() -> tuple[CollectionStore, LedgerStore]:
    backend = os.environ.get("OPERATIONAL_STATE_BACKEND", "memory").strip().lower()
    if backend == "memory":
        if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production" and os.environ.get("ALLOW_EPHEMERAL_STATE") != "1":
            raise RuntimeError(
                "OPERATIONAL_STATE_BACKEND=memory is refused in production: operational state would be lost on every restart. "
                "Use OPERATIONAL_STATE_BACKEND=postgres (after `alembic upgrade head`), or set ALLOW_EPHEMERAL_STATE=1 deliberately."
            )
        return MemoryCollectionStore(), MemoryLedgerStore()
    if backend == "postgres":
        from app.config import get_settings
        from app.persistence.postgres import PostgresCollectionStore, PostgresLedgerStore, make_engine

        engine = make_engine(get_settings().database_url)
        return PostgresCollectionStore(engine), PostgresLedgerStore(engine)
    raise ValueError(f"unknown OPERATIONAL_STATE_BACKEND {backend!r} (expected 'memory' or 'postgres')")


@lru_cache(maxsize=1)
def get_stores() -> tuple[CollectionStore, LedgerStore]:
    """Process-wide stores shared by every manager (so they see the same durable state)."""
    return build_stores()
