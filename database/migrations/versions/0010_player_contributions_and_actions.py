"""canonical actions and player contribution snapshots (Phase 3.1)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. canonical_actions table
    op.create_table(
        "canonical_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "match_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "club_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clubs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.Integer(), nullable=True),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("extra_minute", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("action_subtype", sa.String(length=64), nullable=False),
        sa.Column("action_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("outcome", sa.String(length=32), nullable=False, server_default="UNKNOWN"),
        sa.Column("x", sa.Float(), nullable=True),
        sa.Column("y", sa.Float(), nullable=True),
        sa.Column("end_x", sa.Float(), nullable=True),
        sa.Column("end_y", sa.Float(), nullable=True),
        sa.Column(
            "recipient_player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "related_player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="api-football"),
        sa.Column("provider_event_id", sa.String(length=128), nullable=True),
        sa.Column(
            "source_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("normalization_version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "match_id", "player_id", "minute", "action_type", "action_subtype", "outcome",
            name="uq_canonical_action_signature",
        ),
    )
    op.create_index("ix_canonical_actions_match_id", "canonical_actions", ["match_id"])
    op.create_index("ix_canonical_actions_player_id", "canonical_actions", ["player_id"])
    op.create_index("ix_canonical_actions_club_id", "canonical_actions", ["club_id"])
    op.create_index("ix_canonical_actions_action_type", "canonical_actions", ["action_type"])
    op.create_index("ix_canonical_actions_minute", "canonical_actions", ["minute"])

    # 2. player_contribution_snapshots table
    op.create_table(
        "player_contribution_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_set_version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("calculation_version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("position_group", sa.String(length=16), nullable=False),
        sa.Column("sample_minutes", sa.Integer(), nullable=False),
        sa.Column("sample_matches", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("contribution_status", sa.String(length=32), nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("raw_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "player_id", "as_of", "calculation_version",
            name="uq_player_contribution_snapshot",
        ),
    )
    op.create_index("ix_player_contribution_snapshots_player_id", "player_contribution_snapshots", ["player_id"])
    op.create_index("ix_player_contribution_snapshots_as_of", "player_contribution_snapshots", ["as_of"])


def downgrade() -> None:
    op.drop_table("player_contribution_snapshots")
    op.drop_table("canonical_actions")
