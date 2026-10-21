"""operational state: durable collections and an append-only, hash-chained ledger

Phase 10/16 operational state (projects, watchlists, scenarios, alerts, jobs) lived in module-level dicts and was lost on
every restart. This migration adds the two tables the persistence layer (app/persistence) writes through to:

* operational_records: one row per domain object, with indexed ownership columns (owner_id, organization_id) so tenant
  isolation can be enforced in SQL, and the object itself as a JSONB payload with a version counter.
* ledger_entries: append-only evidence (decision records and audit events). Each entry carries prev_hash/entry_hash, so
  rewriting or removing history is detectable, and a trigger rejects UPDATE and DELETE at the database level.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_records",
        sa.Column("collection", sa.String(32), primary_key=True),
        sa.Column("record_id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_operational_records_collection_org", "operational_records", ["collection", "organization_id"])
    op.create_index("ix_operational_records_collection_owner", "operational_records", ["collection", "owner_id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ledger_key", sa.String(160), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("entry_kind", sa.String(32), nullable=False),
        sa.Column("entry_id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("ledger_key", "seq", name="uq_ledger_entries_key_seq"),
        sa.UniqueConstraint("entry_kind", "entry_id", name="uq_ledger_entries_kind_id"),
    )
    op.create_index("ix_ledger_entries_organization_id", "ledger_entries", ["organization_id"])
    op.execute(
        "CREATE OR REPLACE FUNCTION ledger_entries_forbid_mutation() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'ledger_entries is append-only'; END; $$ LANGUAGE plpgsql"
    )
    op.execute(
        "CREATE TRIGGER ledger_entries_append_only BEFORE UPDATE OR DELETE ON ledger_entries "
        "FOR EACH ROW EXECUTE FUNCTION ledger_entries_forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_append_only ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS ledger_entries_forbid_mutation()")
    op.drop_index("ix_ledger_entries_organization_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("ix_operational_records_collection_owner", table_name="operational_records")
    op.drop_index("ix_operational_records_collection_org", table_name="operational_records")
    op.drop_table("operational_records")
