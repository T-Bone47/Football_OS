"""match normalization enhancements and match_teams table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add enhancement columns to matches
    op.add_column("matches", sa.Column("provider", sa.String(64), nullable=False, server_default="api-football"))
    op.add_column("matches", sa.Column("round", sa.String(128), nullable=True))
    op.add_column("matches", sa.Column("stage", sa.String(64), nullable=True))
    op.add_column("matches", sa.Column("venue_name", sa.String(255), nullable=True))
    op.add_column("matches", sa.Column("venue_city", sa.String(128), nullable=True))
    op.add_column("matches", sa.Column("referee", sa.String(128), nullable=True))
    op.add_column("matches", sa.Column("status_detail", sa.String(64), nullable=True))
    op.add_column("matches", sa.Column("halftime_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("halftime_away_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("fulltime_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("fulltime_away_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("extratime_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("extratime_away_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("penalty_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("penalty_away_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("winner_club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True))
    op.add_column("matches", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

    # 2. Indexes and constraints for matches
    op.create_unique_constraint("uq_match_provider_fixture", "matches", ["provider", "provider_fixture_id"])
    op.create_index("ix_matches_date", "matches", ["date"])
    op.create_index("ix_matches_status", "matches", ["status"])
    op.create_index("ix_matches_provider_fixture_id", "matches", ["provider_fixture_id"])
    op.create_index("ix_matches_competition_season_id", "matches", ["competition_season_id"])
    op.create_index("ix_matches_home_club_id", "matches", ["home_club_id"])
    op.create_index("ix_matches_away_club_id", "matches", ["away_club_id"])

    # 3. Create match_teams table
    op.create_table(
        "match_teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_club_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("result", sa.String(16), nullable=True),
        sa.Column("goals_for", sa.Integer(), nullable=True),
        sa.Column("goals_against", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("match_id", "club_id", name="uq_match_team_match_club"),
    )
    op.create_index("ix_match_teams_match_id", "match_teams", ["match_id"])
    op.create_index("ix_match_teams_club_id", "match_teams", ["club_id"])
    op.create_index("ix_match_teams_opponent_club_id", "match_teams", ["opponent_club_id"])


def downgrade() -> None:
    op.drop_index("ix_match_teams_opponent_club_id", table_name="match_teams")
    op.drop_index("ix_match_teams_club_id", table_name="match_teams")
    op.drop_index("ix_match_teams_match_id", table_name="match_teams")
    op.drop_table("match_teams")

    op.drop_index("ix_matches_away_club_id", table_name="matches")
    op.drop_index("ix_matches_home_club_id", table_name="matches")
    op.drop_index("ix_matches_competition_season_id", table_name="matches")
    op.drop_index("ix_matches_provider_fixture_id", table_name="matches")
    op.drop_index("ix_matches_status", table_name="matches")
    op.drop_index("ix_matches_date", table_name="matches")
    op.drop_constraint("uq_match_provider_fixture", "matches", type_="unique")

    op.drop_column("matches", "updated_at")
    op.drop_column("matches", "winner_club_id")
    op.drop_column("matches", "penalty_away_score")
    op.drop_column("matches", "penalty_home_score")
    op.drop_column("matches", "extratime_away_score")
    op.drop_column("matches", "extratime_home_score")
    op.drop_column("matches", "fulltime_away_score")
    op.drop_column("matches", "fulltime_home_score")
    op.drop_column("matches", "halftime_away_score")
    op.drop_column("matches", "halftime_home_score")
    op.drop_column("matches", "status_detail")
    op.drop_column("matches", "referee")
    op.drop_column("matches", "venue_city")
    op.drop_column("matches", "venue_name")
    op.drop_column("matches", "stage")
    op.drop_column("matches", "round")
    op.drop_column("matches", "provider")
