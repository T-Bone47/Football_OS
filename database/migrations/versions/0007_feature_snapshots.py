"""feature snapshots canonical model

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "match_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("feature_set", sa.String(64), nullable=False),
        sa.Column("calculation_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "season_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "competition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("features", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provenance", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "feature_set",
            "calculation_version",
            "as_of",
            name="uq_feature_snapshot",
        ),
    )
    op.create_index("ix_feature_snapshots_entity", "feature_snapshots", ["entity_type", "entity_id"])
    op.create_index("ix_feature_snapshots_match_id", "feature_snapshots", ["match_id"])
    op.create_index("ix_feature_snapshots_as_of", "feature_snapshots", ["as_of"])
    op.create_index("ix_feature_snapshots_season_id", "feature_snapshots", ["season_id"])
    op.create_index("ix_feature_snapshots_competition_id", "feature_snapshots", ["competition_id"])


def downgrade() -> None:
    op.drop_table("feature_snapshots")
