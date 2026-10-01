"""player intelligence snapshots (Phase 3.2)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_intelligence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "club_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clubs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "competition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("competitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "season_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculation_version", sa.String(32), nullable=False, server_default="1.0"),
        sa.Column("data_status", sa.String(32), nullable=False),
        sa.Column("sample_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("position_group", sa.String(16), nullable=False),
        sa.Column("contribution_vector", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("intelligence_vector", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("peer_benchmarks", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("contextual_adjustments", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("explanations", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("trajectory", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "role_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("player_role_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tactical_fit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("player_tactical_fits.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "player_id", "as_of", "calculation_version",
            name="uq_player_intelligence_snapshot",
        ),
    )

    op.create_index(
        "ix_player_intelligence_snapshots_player_id",
        "player_intelligence_snapshots",
        ["player_id"],
    )
    op.create_index(
        "ix_player_intelligence_snapshots_as_of",
        "player_intelligence_snapshots",
        ["as_of"],
    )
    op.create_index(
        "ix_player_intelligence_snapshots_data_status",
        "player_intelligence_snapshots",
        ["data_status"],
    )
    op.create_index(
        "ix_player_intelligence_snapshots_confidence",
        "player_intelligence_snapshots",
        ["confidence"],
    )


def downgrade() -> None:
    op.drop_table("player_intelligence_snapshots")
