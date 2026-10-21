"""database expansion: identity, membership, checkpoint, provenance and coverage tables

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-21

This migration is additive. It creates the expansion tables, extends the canonical
player/identity rows with the fields a multi-source world needs, and — importantly —
stops treating "the provider did not report this statistic" as a measured zero.

The `player_season_stats` backfill only nulls a value when the source-native block in
`raw_stats` has no corresponding key AND the stored value is 0. A measured zero (the
provider explicitly sent 0) is preserved.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ extension
    # pg_trgm is available in the supported PostgreSQL images; it is required for the
    # substring player search to use an index.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ------------------------------------------------------------------ players
    op.add_column("players", sa.Column("display_name", sa.String(length=160), nullable=True))
    op.add_column("players", sa.Column("secondary_position", sa.String(length=32), nullable=True))
    op.add_column("players", sa.Column("country_of_birth", sa.String(length=64), nullable=True))
    op.add_column("players", sa.Column("preferred_foot", sa.String(length=16), nullable=True))
    op.add_column(
        "players",
        sa.Column("active_status", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column("players", sa.Column("name_normalized", sa.String(length=160), nullable=True))
    op.add_column(
        "players",
        sa.Column("identity_confidence", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "players",
        sa.Column("data_completeness", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.add_column("players", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))

    # ------------------------------------------------------------------ player identities
    op.add_column("player_identities", sa.Column("source_url", sa.String(length=512), nullable=True))
    op.add_column("player_identities", sa.Column("source_record_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "player_identities",
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="AUTO"),
    )
    op.add_column(
        "player_identities",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "player_identities",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE player_identities SET first_seen_at = created_at WHERE first_seen_at IS NULL"
    )
    op.execute(
        "UPDATE player_identities SET last_seen_at = COALESCE(created_at, now()) WHERE last_seen_at IS NULL"
    )
    op.alter_column(
        "player_identities",
        "first_seen_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    op.alter_column(
        "player_identities",
        "last_seen_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # ------------------------------------------------- player season stats: NULL != 0
    op.alter_column("player_season_stats", "appearances", existing_type=sa.Integer(), nullable=True)
    op.alter_column("player_season_stats", "lineups", existing_type=sa.Integer(), nullable=True)
    op.alter_column("player_season_stats", "minutes", existing_type=sa.Integer(), nullable=True)
    op.alter_column("player_season_stats", "goals", existing_type=sa.Integer(), nullable=True)
    op.alter_column("player_season_stats", "assists", existing_type=sa.Integer(), nullable=True)
    op.alter_column("player_season_stats", "conceded", existing_type=sa.Integer(), nullable=True)

    # A zero that the provider never reported becomes unknown. A zero the provider did
    # report (the key is present in raw_stats) stays a measured zero.
    op.execute(
        """
        UPDATE player_season_stats
           SET appearances = NULL
         WHERE appearances = 0
           AND raw_stats->'games'->>'appearences' IS NULL
           AND raw_stats->'games'->>'appearences' IS NULL
        """
    )
    op.execute(
        """
        UPDATE player_season_stats
           SET lineups = NULL
         WHERE lineups = 0
           AND raw_stats->'games'->>'lineups' IS NULL
        """
    )
    op.execute(
        """
        UPDATE player_season_stats
           SET minutes = NULL
         WHERE minutes = 0
           AND raw_stats->'games'->>'minutes' IS NULL
        """
    )
    op.execute(
        """
        UPDATE player_season_stats
           SET goals = NULL
         WHERE goals = 0
           AND raw_stats->'goals'->>'total' IS NULL
        """
    )
    op.execute(
        """
        UPDATE player_season_stats
           SET assists = NULL
         WHERE assists = 0
           AND raw_stats->'goals'->>'assists' IS NULL
        """
    )
    op.execute(
        """
        UPDATE player_season_stats
           SET conceded = NULL
         WHERE conceded = 0
           AND raw_stats->'goals'->>'conceded' IS NULL
        """
    )

    # ------------------------------------------------------------------ data sources
    op.add_column("data_sources", sa.Column("license_url", sa.String(length=512), nullable=True))
    op.add_column("data_sources", sa.Column("attribution", sa.String(length=256), nullable=True))
    op.add_column(
        "data_sources",
        sa.Column("redistribution_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "data_sources", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column("data_sources", sa.Column("terms_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("data_sources", sa.Column("notes", sa.String(length=512), nullable=True))

    # ------------------------------------------------------------------ new tables
    op.create_table(
        "player_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias", sa.String(length=160), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=False, server_default="SOURCE_NAME"),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_entity_id", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "provider", "alias", name="uq_player_alias_provider_alias"),
    )
    op.create_index("ix_player_aliases_player_id", "player_aliases", ["player_id"])

    op.create_table(
        "player_club_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("competition_season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("membership_type", sa.String(length=32), nullable=False, server_default="REGISTRATION"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=160), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["competition_season_id"], ["competition_seasons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_provider", "source_record_id", name="uq_player_membership_source_record"),
    )
    op.create_index("ix_player_club_memberships_player_id", "player_club_memberships", ["player_id"])
    op.create_index("ix_player_club_memberships_club_id", "player_club_memberships", ["club_id"])
    op.create_index(
        "ix_player_club_memberships_competition_season_id",
        "player_club_memberships",
        ["competition_season_id"],
    )
    op.create_index("ix_player_club_memberships_is_current", "player_club_memberships", ["is_current"])

    op.create_table(
        "ingestion_checkpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=256), nullable=False),
        sa.Column("competition", sa.String(length=128), nullable=True),
        sa.Column("season", sa.String(length=16), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("declared_total_pages", sa.Integer(), nullable=True),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["last_run_id"], ["ingestion_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "entity_type", "scope_key", name="uq_ingestion_checkpoint_scope"),
    )
    op.create_index("ix_ingestion_checkpoints_status", "ingestion_checkpoints", ["status"])
    op.create_index(
        "ix_ingestion_checkpoints_provider", "ingestion_checkpoints", ["provider", "entity_type"]
    )

    op.create_table(
        "ingestion_failures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=256), nullable=False),
        sa.Column("record_key", sa.String(length=160), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="TRANSIENT"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "resource", "scope_key", "record_key", name="uq_ingestion_failure_record"
        ),
    )
    op.create_index("ix_ingestion_failures_status", "ingestion_failures", ["status"])
    op.create_index("ix_ingestion_failures_provider", "ingestion_failures", ["provider", "resource"])

    op.create_table(
        "field_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_entity_id", sa.String(length=128), nullable=True),
        sa.Column("source_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("transformation", sa.String(length=128), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type", "entity_id", "field_name", "provider", name="uq_field_provenance_field"
        ),
    )
    op.create_index("ix_field_provenance_entity", "field_provenance", ["entity_type", "entity_id"])

    op.create_table(
        "source_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("resolution", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", "field_name", name="uq_source_conflict_field"),
    )
    op.create_index("ix_source_conflicts_status", "source_conflicts", ["status"])

    op.create_table(
        "identity_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_entity_id", sa.String(length=160), nullable=False),
        sa.Column("candidate_player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_entity_id", "candidate_player_id",
            name="uq_identity_review_candidate",
        ),
    )
    op.create_index("ix_identity_review_queue_status", "identity_review_queue", ["status"])

    op.create_table(
        "country_priorities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=False),
        sa.Column("country_name", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("ranking_source", sa.String(length=256), nullable=False),
        sa.Column("ranking_snapshot_date", sa.Date(), nullable=False),
        sa.Column("scope_label", sa.String(length=64), nullable=False, server_default="FIFA_MENS_SENIOR"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_code", name="uq_country_priority_code"),
    )
    op.create_index("ix_country_priorities_rank", "country_priorities", ["rank"])
    op.create_index("ix_country_priorities_is_active", "country_priorities", ["is_active"])

    # ------------------------------------------------------------------ indexes
    op.create_index("ix_players_name", "players", ["name"])
    op.create_index("ix_players_nationality", "players", ["nationality"])
    op.create_index("ix_players_primary_position", "players", ["primary_position"])
    op.create_index("ix_players_club_id", "players", ["club_id"])
    op.create_index(
        "ix_players_name_trgm",
        "players",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index("ix_player_identities_player_id", "player_identities", ["player_id"])
    op.create_index("ix_player_season_stats_club_id", "player_season_stats", ["club_id"])
    op.create_index(
        "ix_player_season_stats_competition_season_id", "player_season_stats", ["competition_season_id"]
    )
    op.create_index("ix_player_season_stats_player_id", "player_season_stats", ["player_id"])
    op.create_index("ix_clubs_name", "clubs", ["name"])
    op.create_index("ix_clubs_country", "clubs", ["country"])
    op.create_index(
        "ix_matches_competition_season_date", "matches", ["competition_season_id", "date"]
    )

    # ------------------------------------------------------------------ backfill
    # A player's data completeness is the share of the tracked profile fields that are
    # actually known. Computed once here; the ingestion service keeps it current.
    op.execute(
        """
        UPDATE players
           SET data_completeness = round(
                 (
                   (CASE WHEN date_of_birth IS NOT NULL THEN 1 ELSE 0 END) +
                   (CASE WHEN nationality IS NOT NULL THEN 1 ELSE 0 END) +
                   (CASE WHEN primary_position IS NOT NULL THEN 1 ELSE 0 END) +
                   (CASE WHEN height_cm IS NOT NULL THEN 1 ELSE 0 END) +
                   (CASE WHEN weight_kg IS NOT NULL THEN 1 ELSE 0 END) +
                   (CASE WHEN photo_url IS NOT NULL THEN 1 ELSE 0 END) +
                   (CASE WHEN club_id IS NOT NULL THEN 1 ELSE 0 END) +
                   (CASE WHEN first_name IS NOT NULL AND last_name IS NOT NULL THEN 1 ELSE 0 END)
                 )::numeric / 8, 4)
         WHERE data_completeness = 0
        """
    )


def downgrade() -> None:
    op.drop_index("ix_matches_competition_season_date", table_name="matches")
    op.drop_index("ix_clubs_country", table_name="clubs")
    op.drop_index("ix_clubs_name", table_name="clubs")
    op.drop_index("ix_player_season_stats_player_id", table_name="player_season_stats")
    op.drop_index("ix_player_season_stats_competition_season_id", table_name="player_season_stats")
    op.drop_index("ix_player_season_stats_club_id", table_name="player_season_stats")
    op.drop_index("ix_player_identities_player_id", table_name="player_identities")
    op.drop_index("ix_players_name_trgm", table_name="players")
    op.drop_index("ix_players_club_id", table_name="players")
    op.drop_index("ix_players_primary_position", table_name="players")
    op.drop_index("ix_players_nationality", table_name="players")
    op.drop_index("ix_players_name", table_name="players")

    op.drop_table("country_priorities")
    op.drop_table("identity_review_queue")
    op.drop_table("source_conflicts")
    op.drop_table("field_provenance")
    op.drop_table("ingestion_failures")
    op.drop_table("ingestion_checkpoints")
    op.drop_table("player_club_memberships")
    op.drop_table("player_aliases")

    op.drop_column("data_sources", "notes")
    op.drop_column("data_sources", "terms_reviewed_at")
    op.drop_column("data_sources", "enabled")
    op.drop_column("data_sources", "redistribution_allowed")
    op.drop_column("data_sources", "attribution")
    op.drop_column("data_sources", "license_url")

    op.execute(
        """
        UPDATE player_season_stats
           SET appearances = 0, lineups = 0, minutes = 0,
               goals = 0, assists = 0, conceded = 0
         WHERE appearances IS NULL OR lineups IS NULL OR minutes IS NULL
            OR goals IS NULL OR assists IS NULL OR conceded IS NULL
        """
    )
    op.alter_column("player_season_stats", "conceded", existing_type=sa.Integer(), nullable=False, server_default="0")
    op.alter_column("player_season_stats", "assists", existing_type=sa.Integer(), nullable=False, server_default="0")
    op.alter_column("player_season_stats", "goals", existing_type=sa.Integer(), nullable=False, server_default="0")
    op.alter_column("player_season_stats", "minutes", existing_type=sa.Integer(), nullable=False, server_default="0")
    op.alter_column("player_season_stats", "lineups", existing_type=sa.Integer(), nullable=False, server_default="0")
    op.alter_column("player_season_stats", "appearances", existing_type=sa.Integer(), nullable=False, server_default="0")

    op.drop_column("player_identities", "last_seen_at")
    op.drop_column("player_identities", "first_seen_at")
    op.drop_column("player_identities", "review_status")
    op.drop_column("player_identities", "source_record_hash")
    op.drop_column("player_identities", "source_url")

    op.drop_column("players", "last_synced_at")
    op.drop_column("players", "data_completeness")
    op.drop_column("players", "identity_confidence")
    op.drop_column("players", "name_normalized")
    op.drop_column("players", "active_status")
    op.drop_column("players", "preferred_foot")
    op.drop_column("players", "country_of_birth")
    op.drop_column("players", "secondary_position")
    op.drop_column("players", "display_name")
