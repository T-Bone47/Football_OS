"""canonical transfers and market foundation (Phase 4.1C)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_club_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clubs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_club_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clubs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("transfer_date", sa.Date(), nullable=True),
        sa.Column(
            "season_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("competition_context", sa.String(128), nullable=True),
        sa.Column("transfer_type", sa.String(32), nullable=False, server_default="PERMANENT"),
        sa.Column("fee_value", sa.Float(), nullable=True),
        sa.Column("fee_currency", sa.String(8), nullable=True),
        sa.Column("fee_status", sa.String(32), nullable=False, server_default="UNKNOWN_FEE"),
        sa.Column("fee_eur_normalized", sa.Float(), nullable=True),
        sa.Column("fee_min", sa.Float(), nullable=True),
        sa.Column("fee_max", sa.Float(), nullable=True),
        sa.Column("is_loan", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_permanent", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("option_type", sa.String(32), nullable=False, server_default="NONE"),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("data_sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_provider", sa.String(64), nullable=False, server_default="api-football"),
        sa.Column("source_record_id", sa.String(128), nullable=True),
        sa.Column(
            "source_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ingestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("normalization_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("data_quality_status", sa.String(32), nullable=False, server_default="HIGH"),
        sa.Column("quality_reasons", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("raw_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "source_provider", "source_record_id",
            name="uq_transfer_source_record",
        ),
    )

    op.create_index("ix_transfers_player_id", "transfers", ["player_id"])
    op.create_index("ix_transfers_transfer_date", "transfers", ["transfer_date"])
    op.create_index("ix_transfers_fee_status", "transfers", ["fee_status"])
    op.create_index("ix_transfers_from_club_id", "transfers", ["from_club_id"])
    op.create_index("ix_transfers_to_club_id", "transfers", ["to_club_id"])
    op.create_index("ix_transfers_data_quality_status", "transfers", ["data_quality_status"])


def downgrade() -> None:
    op.drop_table("transfers")
