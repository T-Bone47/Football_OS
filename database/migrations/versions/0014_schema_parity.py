"""schema parity: align the database with the ORM models (audit item R19)

`tools/check_orm_migration_parity.py` replayed migrations 0001-0013 against the models and found
33 differences. The 11 composite/lookup indexes that exist only in migrations are now declared on
the ORM (no database change). The remaining 22 are fixed here:

* 16 timestamp columns are declared NOT NULL (with server_default now()) by the models but were
  created nullable. server_default fills every new row, so legitimate rows already have a value.
  NO backfill is performed: a legacy row with a NULL timestamp would make SET NOT NULL fail loudly,
  which is deliberate (inventing a creation time would fabricate provenance). Resolve such rows by
  hand before upgrading.
* 11 single-column indexes declared with index=True on the models were never created.
  (Plain CREATE INDEX takes a write lock; these tables are small. For large tables run the
  statements with CREATE INDEX CONCURRENTLY outside a transaction instead.)

Revision ID: 0014
Revises: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("canonical_actions", "created_at", nullable=False)
    op.alter_column("club_identities", "created_at", nullable=False)
    op.alter_column("clubs", "created_at", nullable=False)
    op.alter_column("clubs", "updated_at", nullable=False)
    op.alter_column("competition_seasons", "created_at", nullable=False)
    op.alter_column("competitions", "created_at", nullable=False)
    op.alter_column("competitions", "updated_at", nullable=False)
    op.alter_column("data_snapshots", "retrieved_at", nullable=False)
    op.alter_column("data_sources", "created_at", nullable=False)
    op.alter_column("matches", "created_at", nullable=False)
    op.alter_column("player_contribution_snapshots", "created_at", nullable=False)
    op.alter_column("player_identities", "created_at", nullable=False)
    op.alter_column("player_season_stats", "created_at", nullable=False)
    op.alter_column("players", "created_at", nullable=False)
    op.alter_column("players", "updated_at", nullable=False)
    op.alter_column("seasons", "created_at", nullable=False)
    op.create_index("ix_canonical_actions_provider_event_id", "canonical_actions", ["provider_event_id"])
    op.create_index("ix_canonical_actions_recipient_player_id", "canonical_actions", ["recipient_player_id"])
    op.create_index("ix_canonical_actions_related_player_id", "canonical_actions", ["related_player_id"])
    op.create_index("ix_canonical_actions_source_snapshot_id", "canonical_actions", ["source_snapshot_id"])
    op.create_index("ix_match_events_minute", "match_events", ["minute"])
    op.create_index("ix_player_intelligence_snapshots_club_id", "player_intelligence_snapshots", ["club_id"])
    op.create_index("ix_player_intelligence_snapshots_competition_id", "player_intelligence_snapshots", ["competition_id"])
    op.create_index("ix_player_intelligence_snapshots_role_profile_id", "player_intelligence_snapshots", ["role_profile_id"])
    op.create_index("ix_player_intelligence_snapshots_season_id", "player_intelligence_snapshots", ["season_id"])
    op.create_index("ix_player_intelligence_snapshots_tactical_fit_id", "player_intelligence_snapshots", ["tactical_fit_id"])
    op.create_index("ix_player_match_stats_provider_club_id", "player_match_stats", ["provider_club_id"])


def downgrade() -> None:
    op.drop_index("ix_player_match_stats_provider_club_id", table_name="player_match_stats")
    op.drop_index("ix_player_intelligence_snapshots_tactical_fit_id", table_name="player_intelligence_snapshots")
    op.drop_index("ix_player_intelligence_snapshots_season_id", table_name="player_intelligence_snapshots")
    op.drop_index("ix_player_intelligence_snapshots_role_profile_id", table_name="player_intelligence_snapshots")
    op.drop_index("ix_player_intelligence_snapshots_competition_id", table_name="player_intelligence_snapshots")
    op.drop_index("ix_player_intelligence_snapshots_club_id", table_name="player_intelligence_snapshots")
    op.drop_index("ix_match_events_minute", table_name="match_events")
    op.drop_index("ix_canonical_actions_source_snapshot_id", table_name="canonical_actions")
    op.drop_index("ix_canonical_actions_related_player_id", table_name="canonical_actions")
    op.drop_index("ix_canonical_actions_recipient_player_id", table_name="canonical_actions")
    op.drop_index("ix_canonical_actions_provider_event_id", table_name="canonical_actions")
    op.alter_column("seasons", "created_at", nullable=True)
    op.alter_column("players", "updated_at", nullable=True)
    op.alter_column("players", "created_at", nullable=True)
    op.alter_column("player_season_stats", "created_at", nullable=True)
    op.alter_column("player_identities", "created_at", nullable=True)
    op.alter_column("player_contribution_snapshots", "created_at", nullable=True)
    op.alter_column("matches", "created_at", nullable=True)
    op.alter_column("data_sources", "created_at", nullable=True)
    op.alter_column("data_snapshots", "retrieved_at", nullable=True)
    op.alter_column("competitions", "updated_at", nullable=True)
    op.alter_column("competitions", "created_at", nullable=True)
    op.alter_column("competition_seasons", "created_at", nullable=True)
    op.alter_column("clubs", "updated_at", nullable=True)
    op.alter_column("clubs", "created_at", nullable=True)
    op.alter_column("club_identities", "created_at", nullable=True)
    op.alter_column("canonical_actions", "created_at", nullable=True)
