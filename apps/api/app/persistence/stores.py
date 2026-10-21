"""Durable operational-state stores: contracts + in-memory implementations (the PostgreSQL ones are in postgres.py).

Two shapes cover the state that used to live in module-level dicts:

* CollectionStore - mutable domain objects (projects, watchlists, scenarios, alerts, jobs). Every record carries an owner
  and an organisation; visibility is decided in the store (list_visible / get_visible) so isolation is provable in SQL.
* LedgerStore     - append-only evidence (decision records, audit events) in hash-chained ledgers. There is no update and
  no delete; verify_links() proves the chain is unbroken.

The in-memory stores are real implementations (the default backend and the reference for the shared contract tests in
tests/unit/test_persistence_contract.py), not mocks.
"""
from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


class LedgerConflict(Exception):
    """The (ledger_key, seq) or (kind, id) already exists: someone else appended first."""


@dataclass(frozen=True)
class StoredRecord:
    collection: str
    record_id: str
    owner_id: str
    organization_id: str | None
    payload: dict[str, Any]
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LedgerRow:
    ledger_key: str
    seq: int
    entry_kind: str
    entry_id: str
    organization_id: str | None
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str


def visible(owner_id: str, organization_id: str | None, user_id: str, org_id: str | None, org_shared: bool) -> bool:
    """Owner always; organisation members only when the collection is organisation-shared."""
    if owner_id == user_id:
        return True
    return org_shared and org_id is not None and organization_id == org_id


class CollectionStore(Protocol):
    def put(self, collection: str, record_id: str, owner_id: str, organization_id: str | None, payload: dict[str, Any]) -> StoredRecord: ...
    def get(self, collection: str, record_id: str) -> StoredRecord | None: ...
    def list(self, collection: str) -> list[StoredRecord]: ...
    def get_visible(self, collection: str, record_id: str, user_id: str, org_id: str | None, org_shared: bool) -> StoredRecord | None: ...
    def list_visible(self, collection: str, user_id: str, org_id: str | None, org_shared: bool) -> list[StoredRecord]: ...
    def delete(self, collection: str, record_id: str) -> bool: ...


class LedgerStore(Protocol):
    def append(self, row: LedgerRow) -> None: ...
    def read(self, ledger_key: str) -> list[LedgerRow]: ...
    def ledger_keys(self, entry_kind: str) -> list[str]: ...


def verify_links(rows: list[LedgerRow]) -> tuple[bool, str]:
    """Chain linkage only: seq is 1..n and each prev_hash is the previous entry_hash. (Content hashes are domain-specific.)"""
    previous = ""
    for expected_seq, row in enumerate(rows, start=1):
        if row.seq != expected_seq:
            return False, f"entry {row.entry_id}: sequence gap (expected {expected_seq}, found {row.seq})"
        if row.prev_hash != previous:
            return False, f"entry {row.entry_id}: broken link to the previous entry"
        previous = row.entry_hash
    return True, f"links intact ({len(rows)} entries)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_record(record: StoredRecord) -> StoredRecord:
    """Callers get copies: mutating a returned payload must never change stored state (only put() does)."""
    return StoredRecord(**{**record.__dict__, "payload": copy.deepcopy(record.payload)})


def _copy_row(row: LedgerRow) -> LedgerRow:
    return LedgerRow(**{**row.__dict__, "payload": copy.deepcopy(row.payload)})


class MemoryCollectionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[tuple[str, str], StoredRecord] = {}

    def put(self, collection: str, record_id: str, owner_id: str, organization_id: str | None, payload: dict[str, Any]) -> StoredRecord:
        with self._lock:
            existing = self._rows.get((collection, record_id))
            if existing is not None and (existing.owner_id != owner_id or existing.organization_id != organization_id):
                raise PermissionError("owner and organisation of an existing record cannot change")
            now = _now()
            record = StoredRecord(
                collection, record_id, owner_id, organization_id, copy.deepcopy(payload),
                1 if existing is None else existing.version + 1, now if existing is None else existing.created_at, now,
            )
            self._rows[(collection, record_id)] = record
            return _copy_record(record)

    def get(self, collection: str, record_id: str) -> StoredRecord | None:
        with self._lock:
            record = self._rows.get((collection, record_id))
            return None if record is None else _copy_record(record)

    def list(self, collection: str) -> list[StoredRecord]:
        with self._lock:
            return [_copy_record(r) for (c, _), r in self._rows.items() if c == collection]

    def get_visible(self, collection: str, record_id: str, user_id: str, org_id: str | None, org_shared: bool) -> StoredRecord | None:
        record = self.get(collection, record_id)
        return record if record and visible(record.owner_id, record.organization_id, user_id, org_id, org_shared) else None

    def list_visible(self, collection: str, user_id: str, org_id: str | None, org_shared: bool) -> list[StoredRecord]:
        return [r for r in self.list(collection) if visible(r.owner_id, r.organization_id, user_id, org_id, org_shared)]

    def delete(self, collection: str, record_id: str) -> bool:
        with self._lock:
            return self._rows.pop((collection, record_id), None) is not None


class MemoryLedgerStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, list[LedgerRow]] = {}

    def append(self, row: LedgerRow) -> None:
        with self._lock:
            ledger = self._rows.setdefault(row.ledger_key, [])
            if any(r.seq == row.seq for r in ledger) or any(
                r.entry_kind == row.entry_kind and r.entry_id == row.entry_id for rows in self._rows.values() for r in rows
            ):
                raise LedgerConflict(f"{row.ledger_key}#{row.seq} / {row.entry_kind}:{row.entry_id} already exists")
            ledger.append(_copy_row(row))
            ledger.sort(key=lambda r: r.seq)

    def read(self, ledger_key: str) -> list[LedgerRow]:
        with self._lock:
            return [_copy_row(r) for r in self._rows.get(ledger_key, [])]

    def ledger_keys(self, entry_kind: str) -> list[str]:
        with self._lock:
            return [k for k, rows in self._rows.items() if rows and rows[0].entry_kind == entry_kind]
