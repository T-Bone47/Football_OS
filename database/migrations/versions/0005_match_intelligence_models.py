"""match intelligence canonical models: events, lineups, statistics

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. match_events table
    op.create_table(
        "match_events",
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
            sa.ForeignKey("players.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assist_player_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("players.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("event_detail", sa.String(64), nullable=True),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("extra_minute", sa.Integer(), nullable=True),
        sa.Column("comments", sa.String(255), nullable=True),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("provider_event_id", sa.String(128), nullable=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("match_id", "event_key", name="uq_match_event_match_key"),
    )
    op.create_index("ix_match_events_match_id", "match_events", ["match_id"])
    op.create_index("ix_match_events_club_id", "match_events", ["club_id"])
    op.create_index("ix_match_events_player_id", "match_events", ["player_id"])
    op.create_index("ix_match_events_assist_player_id", "match_events", ["assist_player_id"])
    op.create_index("ix_match_events_provider_event_id", "match_events", ["provider_event_id"])
    op.create_index("ix_match_events_snapshot_id", "match_events", ["snapshot_id"])
    op.create_index("ix_match_events_match_minute", "match_events", ["match_id", "minute"])

    # 2. match_lineups table
    op.create_table(
        "match_lineups",
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
        sa.Column("is_starter", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("jersey_number", sa.Integer(), nullable=True),
        sa.Column("position", sa.String(16), nullable=True),
        sa.Column("formation_position", sa.String(16), nullable=True),
        sa.Column("formation", sa.String(32), nullable=True),
        sa.Column("is_captain", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("coach_name", sa.String(128), nullable=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("match_id", "club_id", "player_id", name="uq_match_lineup_player"),
    )
    op.create_index("ix_match_lineups_match_id", "match_lineups", ["match_id"])
    op.create_index("ix_match_lineups_club_id", "match_lineups", ["club_id"])
    op.create_index("ix_match_lineups_player_id", "match_lineups", ["player_id"])
    op.create_index("ix_match_lineups_snapshot_id", "match_lineups", ["snapshot_id"])

    # 3. match_statistics table
    op.create_table(
        "match_statistics",
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
        sa.Column("possession_pct", sa.Float(), nullable=True),
        sa.Column("shots_total", sa.Integer(), nullable=True),
        sa.Column("shots_on_target", sa.Integer(), nullable=True),
        sa.Column("shots_off_target", sa.Integer(), nullable=True),
        sa.Column("blocked_shots", sa.Integer(), nullable=True),
        sa.Column("shots_inside_box", sa.Integer(), nullable=True),
        sa.Column("shots_outside_box", sa.Integer(), nullable=True),
        sa.Column("fouls", sa.Integer(), nullable=True),
        sa.Column("corners", sa.Integer(), nullable=True),
        sa.Column("offsides", sa.Integer(), nullable=True),
        sa.Column("yellow_cards", sa.Integer(), nullable=True),
        sa.Column("red_cards", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("passes_total", sa.Integer(), nullable=True),
        sa.Column("passes_accurate", sa.Integer(), nullable=True),
        sa.Column("pass_accuracy_pct", sa.Float(), nullable=True),
        sa.Column("expected_goals", sa.Float(), nullable=True),
        sa.Column("free_kicks", sa.Integer(), nullable=True),
        sa.Column("raw_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("match_id", "club_id", name="uq_match_statistics_match_club"),
    )
    op.create_index("ix_match_statistics_match_id", "match_statistics", ["match_id"])
    op.create_index("ix_match_statistics_club_id", "match_statistics", ["club_id"])
    op.create_index("ix_match_statistics_snapshot_id", "match_statistics", ["snapshot_id"])

    # 4. Seed capabilities for API-Football match intelligence endpoints
    capabilities_table = sa.table(
        "provider_capabilities",
        sa.column("provider", sa.String),
        sa.column("resource", sa.String),
        sa.column("available", sa.Boolean),
    )
    op.bulk_insert(
        capabilities_table,
        [
            {"provider": "api-football", "resource": "fixtures/events", "available": True},
            {"provider": "api-football", "resource": "fixtures/lineups", "available": True},
            {"provider": "api-football", "resource": "fixtures/statistics", "available": True},
        ],
    )


def downgrade() -> None:
    # Remove seeded capabilities
    op.execute(
        "DELETE FROM provider_capabilities WHERE provider = 'api-football' AND resource IN ('fixtures/events', 'fixtures/lineups', 'fixtures/statistics')"
    )
    op.drop_table("match_statistics")
    op.drop_table("match_lineups")
    op.drop_table("match_events")
