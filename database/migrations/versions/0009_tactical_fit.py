"""player tactical fit canonical model

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_tactical_fits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clubs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "season_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tactical_context_id", sa.String(64), nullable=False),
        sa.Column("formation", sa.String(32), nullable=False),
        sa.Column("target_position", sa.String(16), nullable=False),
        sa.Column("position_group", sa.String(16), nullable=False),
        sa.Column("target_role", sa.String(64), nullable=False),
        sa.Column("fit_score", sa.Float(), nullable=False),
        sa.Column("position_fit", sa.Float(), nullable=False),
        sa.Column("role_fit", sa.Float(), nullable=False),
        sa.Column("dimension_fit", sa.Float(), nullable=False),
        sa.Column("style_fit", sa.Float(), nullable=True),
        sa.Column("contextual_fit", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("fit_status", sa.String(32), nullable=False),
        sa.Column("dimension_breakdown", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("why_fit", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("why_not_fit", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("calculation_version", sa.String(32), nullable=False, server_default="tactical_fit_v1"),
        sa.Column("feature_set_version", sa.String(64), nullable=False, server_default="role_feature_set_v1"),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "player_id",
            "tactical_context_id",
            "feature_set_version",
            "calculation_version",
            "as_of",
            name="uq_player_tactical_fit",
        ),
    )
    op.create_index("ix_player_tactical_fits_player_id", "player_tactical_fits", ["player_id"])
    op.create_index("ix_player_tactical_fits_team_id", "player_tactical_fits", ["team_id"])
    op.create_index("ix_player_tactical_fits_season_id", "player_tactical_fits", ["season_id"])
    op.create_index("ix_player_tactical_fits_as_of", "player_tactical_fits", ["as_of"])
    op.create_index("ix_player_tactical_fits_tactical_context_id", "player_tactical_fits", ["tactical_context_id"])
    op.create_index("ix_player_tactical_fits_target_role", "player_tactical_fits", ["target_role"])
    op.create_index("ix_player_tactical_fits_fit_status", "player_tactical_fits", ["fit_status"])


def downgrade() -> None:
    op.drop_table("player_tactical_fits")
