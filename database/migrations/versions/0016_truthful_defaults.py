"""Truthful defaults: no column may assert a fact on the writer's behalf (Phase 18).

Revision ID: 0016
Revises: 0015

Comparing server defaults found database defaults that made facts up when
a writer left a column out: data quality 'HIGH', source provider
'api-football', model status 'MODEL_VALIDATED', a lineup row being a starter,
a valuation's coverage level, and zero minutes, appearances or goals for a
player whose provider never reported them.

- Those defaults are dropped, in the database and in the ORM. A writer must
  now state the value or the insert fails.
- player_season_stats counts become nullable: NULL means "not reported", 0
  means an observed zero.

Structural defaults (empty JSON containers, PENDING/QUEUED/UNKNOWN states,
attempt counters, code version labels) stay. They are listed in
docs/PHASE_18_DATABASE_INTEGRITY.md.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# (table, column, previous default as SQL, previous nullability)
FACT_DEFAULTS = [
    ("canonical_actions", "provider", "'api-football'"),
    ("player_match_stats", "provider", "'api-football'"),
    ("matches", "provider", "'api-football'"),
    ("canonical_actions", "action_quantity", "1"),
    ("competitions", "type", "'LEAGUE'"),
    ("matches", "status", "'SCHEDULED'"),
    ("match_lineups", "is_starter", "true"),
    ("match_lineups", "is_captain", "false"),
    ("player_match_stats", "is_captain", "false"),
    ("player_role_profiles", "role_status", "'QUALIFIED'"),
    ("player_role_profiles", "sample_minutes", "0"),
    ("player_role_profiles", "sample_matches", "0"),
    ("player_intelligence_snapshots", "sample_minutes", "0"),
    ("player_intelligence_snapshots", "sample_matches", "0"),
    ("transfers", "transfer_type", "'PERMANENT'"),
    ("transfers", "is_loan", "false"),
    ("transfers", "is_permanent", "true"),
    ("transfers", "option_type", "'NONE'"),
    ("transfers", "source_provider", "'api-football'"),
    ("transfers", "data_quality_status", "'HIGH'"),
    ("valuation_models", "status", "'MODEL_VALIDATED'"),
    ("valuation_predictions", "coverage_level", "0.8"),
    ("valuation_predictions", "data_status", "'VALUATION_AVAILABLE'"),
]

SEASON_COUNTS = ["appearances", "lineups", "minutes", "goals", "assists", "conceded"]


def upgrade() -> None:
    for table, column, _ in FACT_DEFAULTS:
        op.alter_column(table, column, server_default=None)
    for column in SEASON_COUNTS:
        op.alter_column("player_season_stats", column, server_default=None, nullable=True,
                        existing_type=sa.Integer())


def downgrade() -> None:
    conn = op.get_bind()
    for column in SEASON_COUNTS:
        nulls = conn.execute(sa.text(f"SELECT count(*) FROM player_season_stats WHERE {column} IS NULL")).scalar()
        if nulls:
            raise RuntimeError(
                f"player_season_stats.{column} has {nulls} NULL (not reported) row(s); "
                "downgrading would have to turn them into zeros. Refusing."
            )
        op.alter_column("player_season_stats", column, server_default=sa.text("0"), nullable=False,
                        existing_type=sa.Integer())
    for table, column, default in FACT_DEFAULTS:
        op.alter_column(table, column, server_default=sa.text(default))
