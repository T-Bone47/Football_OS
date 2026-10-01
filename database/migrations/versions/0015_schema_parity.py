"""Schema parity: bring the database in line with the ORM (Phase 18, R19).

Revision ID: 0015
Revises: 0014

`alembic check` on a database migrated to 0014 reported 32 pending operations.
This migration resolves every one of them; it never edits 0001-0014.

- 14 timestamp columns are NOT NULL in the ORM (server default now()) but
  nullable in the database. They become NOT NULL. If any row holds NULL the
  migration stops: a missing timestamp is not invented.
- 10 indexes declared in the ORM were never created. They are created.
- 2 indexes duplicated a unique constraint on the same columns
  (provider, provider_*_id). They are dropped; the constraint's own index
  serves the same lookups.
- The remaining database-only composite indexes are kept and are now
  declared in the ORM instead (match_events, player_match_stats,
  ingestion_runs).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

NOT_NULL_TIMESTAMPS = [
    ("canonical_actions", "created_at"),
    ("club_identities", "created_at"),
    ("clubs", "created_at"),
    ("clubs", "updated_at"),
    ("competition_seasons", "created_at"),
    ("competitions", "created_at"),
    ("competitions", "updated_at"),
    ("data_snapshots", "retrieved_at"),
    ("data_sources", "created_at"),
    ("matches", "created_at"),
    ("player_contribution_snapshots", "created_at"),
    ("player_identities", "created_at"),
    ("player_season_stats", "created_at"),
    ("players", "created_at"),
    ("players", "updated_at"),
    ("seasons", "created_at"),
]

NEW_INDEXES = [
    ("ix_canonical_actions_provider_event_id", "canonical_actions", ["provider_event_id"]),
    ("ix_canonical_actions_recipient_player_id", "canonical_actions", ["recipient_player_id"]),
    ("ix_canonical_actions_related_player_id", "canonical_actions", ["related_player_id"]),
    ("ix_canonical_actions_source_snapshot_id", "canonical_actions", ["source_snapshot_id"]),
    ("ix_player_intelligence_snapshots_club_id", "player_intelligence_snapshots", ["club_id"]),
    ("ix_player_intelligence_snapshots_competition_id", "player_intelligence_snapshots", ["competition_id"]),
    ("ix_player_intelligence_snapshots_role_profile_id", "player_intelligence_snapshots", ["role_profile_id"]),
    ("ix_player_intelligence_snapshots_season_id", "player_intelligence_snapshots", ["season_id"]),
    ("ix_player_intelligence_snapshots_tactical_fit_id", "player_intelligence_snapshots", ["tactical_fit_id"]),
    ("ix_player_match_stats_provider_club_id", "player_match_stats", ["provider_club_id"]),
]

REDUNDANT_INDEXES = [
    ("ix_club_identities_provider_lookup", "club_identities", ["provider", "provider_club_id"]),
    ("ix_player_identities_provider_lookup", "player_identities", ["provider", "provider_player_id"]),
]


def upgrade() -> None:
    conn = op.get_bind()
    for table, column in NOT_NULL_TIMESTAMPS:
        nulls = conn.execute(sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL')).scalar()
        if nulls:
            raise RuntimeError(
                f"{table}.{column} has {nulls} NULL row(s). Refusing to invent timestamps; "
                "resolve these rows from their source records before migrating."
            )
        op.alter_column(table, column, existing_type=sa.DateTime(timezone=True), nullable=False)
    for name, table, cols in NEW_INDEXES:
        op.create_index(name, table, cols)
    for name, table, _ in REDUNDANT_INDEXES:
        op.drop_index(name, table_name=table)


def downgrade() -> None:
    for name, table, cols in REDUNDANT_INDEXES:
        op.create_index(name, table, cols)
    for name, table, _ in NEW_INDEXES:
        op.drop_index(name, table_name=table)
    for table, column in NOT_NULL_TIMESTAMPS:
        op.alter_column(table, column, existing_type=sa.DateTime(timezone=True), nullable=True)
