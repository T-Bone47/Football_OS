"""Shared contract for the operational-state stores. The in-memory implementation always runs; the PostgreSQL one runs
when TEST_DATABASE_URL is set and SQLAlchemy is installed (CI), against a database migrated with `alembic upgrade head`.
A "restart" opens a NEW engine/connection on the same data, so durability is checked, not assumed."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.persistence.stores import LedgerConflict, LedgerRow, MemoryCollectionStore, MemoryLedgerStore, verify_links

try:  # pragma: no cover - environment dependent
    from app.persistence.postgres import PostgresCollectionStore, PostgresLedgerStore, make_engine

    _HAVE_PG = bool(os.environ.get("TEST_DATABASE_URL"))
except ImportError:
    _HAVE_PG = False


@pytest.fixture(scope="session")
def _ensure_ledger_trigger():
    """Ensure the ledger_entries append-only trigger exists for postgres tests.
    This is created by migration 0015 but may be missing if earlier tests ran drop_all/create_all.
    """
    if not _HAVE_PG:
        return
    engine = create_engine(os.environ["TEST_DATABASE_URL"].replace("+asyncpg", "+psycopg2"))
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION ledger_entries_forbid_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'ledger_entries is append-only'; END; $$ LANGUAGE plpgsql;
            DROP TRIGGER IF EXISTS ledger_entries_append_only ON ledger_entries;
            CREATE TRIGGER ledger_entries_append_only BEFORE UPDATE OR DELETE ON ledger_entries
            FOR EACH ROW EXECUTE FUNCTION ledger_entries_forbid_mutation();
        """))


@pytest.fixture
def pg_backend(_ensure_ledger_trigger):
    """Postgres backend with ledger trigger ensured."""
    return "postgres"


_MEMORY = (MemoryCollectionStore(), MemoryLedgerStore())




def open_backend(name: str):
    """(collection store, ledger store). Postgres: a fresh engine each call = a process restart."""
    if name == "memory":
        return _MEMORY
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    return PostgresCollectionStore(engine), PostgresLedgerStore(engine)


def _uid() -> str:
    return uuid.uuid4().hex[:12]


@pytest.mark.parametrize("backend", ["memory", "postgres"])
@pytest.mark.usefixtures("_ensure_ledger_trigger")
def test_put_get_roundtrip_versions_and_isolates_payload_copies(backend):
    store, _ = open_backend(backend)
    coll, rid = f"c_{_uid()}"[:32], _uid()
    first = store.put(coll, rid, "alice", "org_a", {"name": "x", "tags": ["a"]})
    assert (first.version, first.owner_id, first.organization_id, first.payload) == (1, "alice", "org_a", {"name": "x", "tags": ["a"]})
    second = store.put(coll, rid, "alice", "org_a", {"name": "y"})
    assert second.version == 2 and second.created_at == first.created_at
    got = store.get(coll, rid)
    got.payload["name"] = "mutated"
    assert store.get(coll, rid).payload == {"name": "y"}
    assert store.get(coll, "missing") is None


@pytest.mark.parametrize("backend", ["memory", "postgres"])
@pytest.mark.usefixtures("_ensure_ledger_trigger")
def test_the_owner_and_organisation_of_a_record_cannot_be_reassigned(backend):
    store, _ = open_backend(backend)
    coll, rid = f"c_{_uid()}"[:32], _uid()
    store.put(coll, rid, "alice", "org_a", {})
    for owner, org in (("mallory", "org_a"), ("alice", "org_b"), ("alice", None)):
        with pytest.raises(PermissionError):
            store.put(coll, rid, owner, org, {"hijack": True})
    assert store.get(coll, rid).owner_id == "alice"


@pytest.mark.parametrize("backend", ["memory", "postgres"])
@pytest.mark.usefixtures("_ensure_ledger_trigger")
def test_visibility_isolates_users_and_organisations(backend):
    store, _ = open_backend(backend)
    coll = f"c_{_uid()}"[:32]
    store.put(coll, "a1", "alice", "org_a", {"n": 1})
    store.put(coll, "b1", "bob", "org_b", {"n": 2})
    store.put(coll, "s1", "solo", None, {"n": 3})

    def ids(user, org, shared):
        return sorted(r.record_id for r in store.list_visible(coll, user, org, shared))

    assert ids("amy", "org_a", True) == ["a1"]       # organisation-shared collection: colleagues see it
    assert ids("amy", "org_a", False) == []          # owner-private collection: colleagues do not
    assert ids("alice", "org_a", False) == ["a1"]
    assert ids("bob", "org_b", True) == ["b1"]       # another tenant never sees org_a's record
    assert ids("solo", None, True) == ["s1"]         # no organisation: own records only
    assert ids("amy", None, True) == []
    assert store.get_visible(coll, "a1", "bob", "org_b", True) is None
    assert store.get_visible(coll, "a1", "amy", "org_a", True).record_id == "a1"
    assert store.get_visible(coll, "a1", "amy", "org_a", False) is None


@pytest.mark.parametrize("backend", ["memory", "postgres"])
@pytest.mark.usefixtures("_ensure_ledger_trigger")
def test_records_survive_a_restart_and_deletion_is_real(backend):
    coll, rid = f"c_{_uid()}"[:32], _uid()
    open_backend(backend)[0].put(coll, rid, "alice", "org_a", {"survives": True})
    reopened, _ = open_backend(backend)  # fresh connections: the process "restarted"
    assert reopened.get(coll, rid).payload == {"survives": True}
    assert reopened.delete(coll, rid) is True and reopened.delete(coll, rid) is False
    assert open_backend(backend)[0].get(coll, rid) is None


def _chain(key: str, kind: str, n: int, org: str | None = "org_a") -> list[LedgerRow]:
    rows, prev = [], ""
    for seq in range(1, n + 1):
        entry_hash = f"{seq:02d}".ljust(64, "f")
        rows.append(LedgerRow(key, seq, kind, f"{key}-{seq}", org, {"n": seq}, prev, entry_hash))
        prev = entry_hash
    return rows


@pytest.mark.parametrize("backend", ["memory", "postgres"])
@pytest.mark.usefixtures("_ensure_ledger_trigger")
def test_ledger_appends_in_order_survives_restart_and_links_verify(backend):
    key = f"k_{_uid()}"
    _, ledger = open_backend(backend)
    for row in _chain(key, "DECISION", 3):
        ledger.append(row)
    rows = open_backend(backend)[1].read(key)  # after a "restart"
    assert [r.seq for r in rows] == [1, 2, 3] and rows[1].payload == {"n": 2}
    assert verify_links(rows) == (True, "links intact (3 entries)")
    assert key in open_backend(backend)[1].ledger_keys("DECISION") and key not in open_backend(backend)[1].ledger_keys("AUDIT")


@pytest.mark.parametrize("backend", ["memory", "postgres"])
@pytest.mark.usefixtures("_ensure_ledger_trigger")
def test_ledger_rejects_a_concurrent_or_replayed_append(backend):
    key = f"k_{_uid()}"
    _, ledger = open_backend(backend)
    rows = _chain(key, "DECISION", 2)
    for row in rows:
        ledger.append(row)
    with pytest.raises(LedgerConflict):
        ledger.append(LedgerRow(key, 2, "DECISION", "another-id", "org_a", {}, rows[0].entry_hash, "e" * 64))  # same seq
    with pytest.raises(LedgerConflict):
        ledger.append(LedgerRow(key, 3, "DECISION", rows[0].entry_id, "org_a", {}, rows[1].entry_hash, "e" * 64))  # same id


def test_link_verification_detects_gaps_and_broken_links():
    rows = _chain("k", "DECISION", 3)
    assert verify_links(rows[:1] + rows[2:])[0] is False  # entry 2 removed
    tampered = [rows[0], LedgerRow(**{**rows[1].__dict__, "prev_hash": "0" * 64}), rows[2]]
    assert verify_links(tampered)[0] is False


def test_the_ledger_interface_has_no_way_to_update_or_delete():
    for store in (MemoryLedgerStore(),):
        assert not any(hasattr(store, name) for name in ("update", "delete", "remove", "put"))


@pytest.mark.skipif(not _HAVE_PG, reason="needs TEST_DATABASE_URL + SQLAlchemy (CI)")
def test_postgres_rejects_update_and_delete_on_the_ledger_at_the_database_level():
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    key = f"k_{_uid()}"
    _, ledger = open_backend("postgres")
    ledger.append(_chain(key, "DECISION", 1)[0])
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    for sql in ("UPDATE ledger_entries SET payload = '{}' WHERE ledger_key = :k", "DELETE FROM ledger_entries WHERE ledger_key = :k"):
        with pytest.raises(DBAPIError):
            with engine.begin() as conn:
                conn.execute(text(sql), {"k": key})
