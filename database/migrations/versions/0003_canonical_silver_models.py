"""canonical silver models: competitions, seasons, competition_seasons, clubs, club_identities, players, player_identities, player_season_stats, matches

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. competitions
    op.create_table(
        "competitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("type", sa.String(32), nullable=False, server_default="LEAGUE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. seasons
    op.create_table(
        "seasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("end_year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_season_name"),
    )

    # 3. competition_seasons
    op.create_table(
        "competition_seasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("competition_id", "season_id", name="uq_competition_season"),
    )

    # 4. clubs
    op.create_table(
        "clubs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("code", sa.String(16), nullable=True),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("founded", sa.Integer(), nullable=True),
        sa.Column("venue_name", sa.String(128), nullable=True),
        sa.Column("venue_capacity", sa.Integer(), nullable=True),
        sa.Column("logo_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 5. club_identities
    op.create_table(
        "club_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_club_id", sa.String(128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("resolution_method", sa.String(64), nullable=False, server_default="DIRECT_PROVIDER_ID"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_club_id", name="uq_club_identity_provider_id"),
    )
    op.create_index("ix_club_identities_provider_lookup", "club_identities", ["provider", "provider_club_id"])

    # 6. players
    op.create_table(
        "players",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("first_name", sa.String(64), nullable=True),
        sa.Column("last_name", sa.String(64), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("nationality", sa.String(64), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("weight_kg", sa.Integer(), nullable=True),
        sa.Column("primary_position", sa.String(32), nullable=True),
        sa.Column("photo_url", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 7. player_identities
    op.create_table(
        "player_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_player_id", sa.String(128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("resolution_method", sa.String(64), nullable=False, server_default="DIRECT_PROVIDER_ID"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_player_id", name="uq_player_identity_provider_id"),
    )
    op.create_index("ix_player_identities_provider_lookup", "player_identities", ["provider", "provider_player_id"])

    # 8. player_season_stats
    op.create_table(
        "player_season_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("competition_season_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competition_seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("appearances", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lineups", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.String(32), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conceded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_stats", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("player_id", "club_id", "competition_season_id", name="uq_player_club_comp_season"),
    )

    # 9. matches
    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("competition_season_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("competition_seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("home_club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("away_club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="SCHEDULED"),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("provider_fixture_id", sa.String(128), nullable=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("competition_season_id", "home_club_id", "away_club_id", "date", name="uq_match_fixture"),
    )


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("player_season_stats")
    op.drop_index("ix_player_identities_provider_lookup", table_name="player_identities")
    op.drop_table("player_identities")
    op.drop_table("players")
    op.drop_index("ix_club_identities_provider_lookup", table_name="club_identities")
    op.drop_table("club_identities")
    op.drop_table("clubs")
    op.drop_table("competition_seasons")
    op.drop_table("seasons")
    op.drop_table("competitions")
