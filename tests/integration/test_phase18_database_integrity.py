"""Phase 18 — database integrity (R19 and the truthful-defaults policy).

Runs against a database built only by `alembic upgrade head`. Fails when:
- the ORM and the migrated schema disagree on tables, columns, nullability,
  indexes or column types (what `alembic check` compares);
- a column again gets a default that asserts a fact for the writer;
- a season statistic can no longer be stored as "not reported" (NULL).
"""
from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db.base import Base
import app.db.models  # noqa: F401  (registers every table on Base.metadata)


def _sync(url: str) -> str:
    return url.replace("+asyncpg", "+psycopg2")


def test_orm_and_migrations_have_zero_drift(p17_db_url):
    engine = create_engine(_sync(p17_db_url))
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diffs = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diffs == [], f"schema drift between ORM and migrations: {diffs}"


# Defaults that would let an insert silently claim a fact.
FORBIDDEN_DEFAULTS = {
    ("transfers", "data_quality_status"), ("transfers", "source_provider"), ("transfers", "transfer_type"),
    ("transfers", "is_permanent"), ("canonical_actions", "provider"), ("valuation_models", "status"),
    ("valuation_predictions", "coverage_level"), ("valuation_predictions", "data_status"),
    ("match_lineups", "is_starter"), ("matches", "status"), ("player_role_profiles", "role_status"),
    ("player_match_stats", "provider"),
    ("player_season_stats", "minutes"), ("player_season_stats", "appearances"), ("player_season_stats", "goals"),
}


def test_no_fact_asserting_defaults(p17_db_url):
    engine = create_engine(_sync(p17_db_url))
    insp = inspect(engine)
    found = []
    for table, column in FORBIDDEN_DEFAULTS:
        col = next(c for c in insp.get_columns(table) if c["name"] == column)
        if col["default"] is not None:
            found.append((table, column, col["default"]))
        orm_col = Base.metadata.tables[table].c[column]
        if orm_col.default is not None or orm_col.server_default is not None:
            found.append((table, column, "ORM default"))
    engine.dispose()
    assert found == []


@pytest.mark.parametrize("column", ["appearances", "lineups", "minutes", "goals", "assists", "conceded"])
def test_season_counts_can_be_unreported(p17_db_url, column):
    engine = create_engine(_sync(p17_db_url))
    col = next(c for c in inspect(engine).get_columns("player_season_stats") if c["name"] == column)
    engine.dispose()
    assert col["nullable"] is True
