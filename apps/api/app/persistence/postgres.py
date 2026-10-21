"""PostgreSQL implementations of the operational-state stores (synchronous SQLAlchemy Core over psycopg2).

Synchronous on purpose: the Phase 10/16 managers and their routes are synchronous (run in FastAPI's threadpool), so a
sync engine plugs in without async plumbing. Tables are created by migration 0015.

UNVERIFIED in the audit sandbox (no PostgreSQL, no SQLAlchemy): verified by tests/unit/test_persistence_contract.py,
which runs this class against a real database when TEST_DATABASE_URL is set (CI does).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.db.urls import to_sync_url
from app.persistence.stores import LedgerConflict, LedgerRow, StoredRecord

_COLS = "collection, record_id, owner_id, organization_id, payload, version, created_at, updated_at"


def make_engine(database_url: str) -> Engine:
    return create_engine(to_sync_url(database_url), pool_pre_ping=True, future=True)


def _record(row: Any) -> StoredRecord:
    m = row._mapping
    return StoredRecord(
        m["collection"], m["record_id"], m["owner_id"], m["organization_id"], m["payload"], m["version"],
        m["created_at"].isoformat(), m["updated_at"].isoformat(),
    )


class PostgresCollectionStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def put(self, collection: str, record_id: str, owner_id: str, organization_id: str | None, payload: dict[str, Any]) -> StoredRecord:
        params = {"c": collection, "r": record_id, "o": owner_id, "g": organization_id, "p": json.dumps(payload, default=str)}
        with self._engine.begin() as conn:
            existing = conn.execute(
                text("SELECT owner_id, organization_id FROM operational_records WHERE collection = :c AND record_id = :r FOR UPDATE"),
                params,
            ).first()
            if existing is not None and (existing.owner_id != owner_id or existing.organization_id != organization_id):
                raise PermissionError("owner and organisation of an existing record cannot change")
            row = conn.execute(
                text(
                    "INSERT INTO operational_records (collection, record_id, owner_id, organization_id, payload) "
                    "VALUES (:c, :r, :o, :g, CAST(:p AS JSONB)) "
                    "ON CONFLICT (collection, record_id) DO UPDATE "
                    "SET payload = EXCLUDED.payload, version = operational_records.version + 1, updated_at = now() "
                    f"RETURNING {_COLS}"
                ),
                params,
            ).one()
        return _record(row)

    def get(self, collection: str, record_id: str) -> StoredRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {_COLS} FROM operational_records WHERE collection = :c AND record_id = :r"), {"c": collection, "r": record_id}
            ).first()
        return None if row is None else _record(row)

    def list(self, collection: str) -> list[StoredRecord]:
        with self._engine.connect() as conn:
            rows = conn.execute(text(f"SELECT {_COLS} FROM operational_records WHERE collection = :c ORDER BY created_at, record_id"), {"c": collection}).all()
        return [_record(r) for r in rows]

    _VISIBLE = "(owner_id = :u OR (CAST(:s AS BOOLEAN) AND CAST(:g AS VARCHAR) IS NOT NULL AND organization_id = CAST(:g AS VARCHAR)))"

    def get_visible(self, collection: str, record_id: str, user_id: str, org_id: str | None, org_shared: bool) -> StoredRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {_COLS} FROM operational_records WHERE collection = :c AND record_id = :r AND {self._VISIBLE}"),
                {"c": collection, "r": record_id, "u": user_id, "g": org_id, "s": org_shared},
            ).first()
        return None if row is None else _record(row)

    def list_visible(self, collection: str, user_id: str, org_id: str | None, org_shared: bool) -> list[StoredRecord]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {_COLS} FROM operational_records WHERE collection = :c AND {self._VISIBLE} ORDER BY created_at, record_id"),
                {"c": collection, "u": user_id, "g": org_id, "s": org_shared},
            ).all()
        return [_record(r) for r in rows]

    def delete(self, collection: str, record_id: str) -> bool:
        with self._engine.begin() as conn:
            return conn.execute(text("DELETE FROM operational_records WHERE collection = :c AND record_id = :r"), {"c": collection, "r": record_id}).rowcount > 0


class PostgresLedgerStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, row: LedgerRow) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO ledger_entries (ledger_key, seq, entry_kind, entry_id, organization_id, payload, prev_hash, entry_hash) "
                        "VALUES (:k, :s, :kind, :id, :org, CAST(:p AS JSONB), :prev, :h)"
                    ),
                    {"k": row.ledger_key, "s": row.seq, "kind": row.entry_kind, "id": row.entry_id, "org": row.organization_id,
                     "p": json.dumps(row.payload, default=str), "prev": row.prev_hash, "h": row.entry_hash},
                )
        except IntegrityError as exc:
            raise LedgerConflict(str(exc.orig)) from exc

    def read(self, ledger_key: str) -> list[LedgerRow]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT ledger_key, seq, entry_kind, entry_id, organization_id, payload, prev_hash, entry_hash FROM ledger_entries WHERE ledger_key = :k ORDER BY seq"),
                {"k": ledger_key},
            ).all()
        return [LedgerRow(r.ledger_key, r.seq, r.entry_kind, r.entry_id, r.organization_id, r.payload, r.prev_hash, r.entry_hash) for r in rows]

    def ledger_keys(self, entry_kind: str) -> list[str]:
        with self._engine.connect() as conn:
            return [r[0] for r in conn.execute(text("SELECT DISTINCT ledger_key FROM ledger_entries WHERE entry_kind = :kind ORDER BY ledger_key"), {"kind": entry_kind})]
