"""provenance foundation: data_sources, ingestion_runs, data_snapshots

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("base_url", sa.String(512)),
        sa.Column("license", sa.String(256)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("data_source_id", sa.Integer(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("endpoint", sa.String(256), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="QUEUED"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column("record_count", sa.Integer()),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCESS','PARTIAL','FAILED')",
            name="ck_ingestion_runs_status",
        ),
    )
    op.create_index("ix_ingestion_runs_data_source_status", "ingestion_runs", ["data_source_id", "status"])

    op.create_table(
        "data_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_location", sa.String(1024), nullable=False),
        sa.Column("schema_version", sa.String(32)),
        sa.Column("validation_status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("validation_errors", sa.Text()),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "validation_status IN ('PENDING','VALID','INVALID')",
            name="ck_data_snapshots_validation_status",
        ),
        sa.UniqueConstraint("ingestion_run_id", "sha256", name="uq_snapshot_run_sha"),
    )


def downgrade() -> None:
    op.drop_table("data_snapshots")
    op.drop_index("ix_ingestion_runs_data_source_status", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("data_sources")
