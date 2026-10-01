"""Transfer provenance status (Phase 18, R21).

Revision ID: 0020
Revises: 0019

Every transfer row states where its facts come from. Existing rows are
classified from their own lineage and never upgraded without evidence:
VERIFIED_SOURCE only for api-football rows with a Bronze snapshot that has a
recorded provider response; everything else is SOURCE_UNVERIFIED.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transfers", sa.Column("provenance_status", sa.String(32), nullable=True))
    op.execute("""
        UPDATE transfers t SET provenance_status = CASE
            WHEN t.source_provider = 'api-football' AND t.source_snapshot_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM data_snapshots s WHERE s.id = t.source_snapshot_id) THEN 'VERIFIED_SOURCE'
            ELSE 'SOURCE_UNVERIFIED' END
    """)
    op.alter_column("transfers", "provenance_status", nullable=False, existing_type=sa.String(32))


def downgrade() -> None:
    op.drop_column("transfers", "provenance_status")
