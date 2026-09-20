"""canonical player-match performance model

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. player_match_stats table
    op.create_table(
        "player_match_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "match_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "club_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clubs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(64),
            nullable=False,
            server_default="api-football",
        ),
        sa.Column("provider_player_id", sa.String(128), nullable=True),
        sa.Column("provider_fixture_id", sa.String(128), nullable=True),
        sa.Column("provider_club_id", sa.String(128), nullable=True),
        sa.Column("is_starter", sa.Boolean(), nullable=True),
        sa.Column("is_substitute", sa.Boolean(), nullable=True),
        sa.Column("position", sa.String(16), nullable=True),
        sa.Column("jersey_number", sa.Integer(), nullable=True),
        sa.Column("formation_position", sa.String(16), nullable=True),
        sa.Column("is_captain", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("goals", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("shots_total", sa.Integer(), nullable=True),
        sa.Column("shots_on_target", sa.Integer(), nullable=True),
        sa.Column("offsides", sa.Integer(), nullable=True),
        sa.Column("passes_total", sa.Integer(), nullable=True),
        sa.Column("passes_key", sa.Integer(), nullable=True),
        sa.Column("pass_accuracy", sa.Float(), nullable=True),
        sa.Column("tackles_total", sa.Integer(), nullable=True),
        sa.Column("blocks", sa.Integer(), nullable=True),
        sa.Column("interceptions", sa.Integer(), nullable=True),
        sa.Column("duels_total", sa.Integer(), nullable=True),
        sa.Column("duels_won", sa.Integer(), nullable=True),
        sa.Column("dribbles_attempts", sa.Integer(), nullable=True),
        sa.Column("dribbles_success", sa.Integer(), nullable=True),
        sa.Column("dribbles_past", sa.Integer(), nullable=True),
        sa.Column("fouls_drawn", sa.Integer(), nullable=True),
        sa.Column("fouls_committed", sa.Integer(), nullable=True),
        sa.Column("yellow_cards", sa.Integer(), nullable=True),
        sa.Column("red_cards", sa.Integer(), nullable=True),
        sa.Column("penalties_won", sa.Integer(), nullable=True),
        sa.Column("penalties_committed", sa.Integer(), nullable=True),
        sa.Column("penalties_scored", sa.Integer(), nullable=True),
        sa.Column("penalties_missed", sa.Integer(), nullable=True),
        sa.Column("penalties_saved", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("goals_conceded", sa.Integer(), nullable=True),
        sa.Column("clean_sheet", sa.Boolean(), nullable=True),
        sa.Column("raw_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("match_id", "club_id", "player_id", name="uq_player_match_stats"),
    )
    op.create_index("ix_player_match_stats_match_id", "player_match_stats", ["match_id"])
    op.create_index("ix_player_match_stats_club_id", "player_match_stats", ["club_id"])
    op.create_index("ix_player_match_stats_player_id", "player_match_stats", ["player_id"])
    op.create_index("ix_player_match_stats_snapshot_id", "player_match_stats", ["snapshot_id"])
    op.create_index("ix_player_match_stats_provider_player_id", "player_match_stats", ["provider_player_id"])
    op.create_index("ix_player_match_stats_provider_fixture_id", "player_match_stats", ["provider_fixture_id"])
    op.create_index("ix_player_match_stats_match_club", "player_match_stats", ["match_id", "club_id"])
    op.create_index("ix_player_match_stats_match_player", "player_match_stats", ["match_id", "player_id"])

    # 2. Seed capability for API-Football fixtures/players endpoint
    capabilities_table = sa.table(
        "provider_capabilities",
        sa.column("provider", sa.String),
        sa.column("resource", sa.String),
        sa.column("available", sa.Boolean),
    )
    op.bulk_insert(
        capabilities_table,
        [
            {"provider": "api-football", "resource": "fixtures/players", "available": True},
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM provider_capabilities WHERE provider = 'api-football' AND resource = 'fixtures/players'"
    )
    op.drop_table("player_match_stats")
