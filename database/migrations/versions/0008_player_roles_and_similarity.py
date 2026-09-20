"""player role profiles and similarity canonical model

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_role_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_set_version", sa.String(64), nullable=False, server_default="role_feature_set_v1"),
        sa.Column("role_status", sa.String(32), nullable=False, server_default="QUALIFIED"),
        sa.Column("sample_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position_group", sa.String(16), nullable=False),
        sa.Column("primary_archetype", sa.String(64), nullable=True),
        sa.Column("secondary_archetype", sa.String(64), nullable=True),
        sa.Column("archetype_confidence", sa.Float(), nullable=True),
        sa.Column("profile_scores", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("feature_vector", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provenance", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "player_id",
            "feature_set_version",
            "as_of",
            name="uq_player_role_profile",
        ),
    )
    op.create_index("ix_player_role_profiles_player_id", "player_role_profiles", ["player_id"])
    op.create_index("ix_player_role_profiles_as_of", "player_role_profiles", ["as_of"])
    op.create_index("ix_player_role_profiles_position_group", "player_role_profiles", ["position_group"])
    op.create_index("ix_player_role_profiles_primary_archetype", "player_role_profiles", ["primary_archetype"])


def downgrade() -> None:
    op.drop_table("player_role_profiles")
