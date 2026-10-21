"""Sync/async Postgres URL helpers (R3): the driver is always named, never left to defaults."""
from __future__ import annotations

import pytest

from app.db.urls import to_async_url, to_sync_url


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@h:5432/db", "postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db", "postgresql+psycopg2://u:p@h/db", "postgresql+psycopg://u:p@h/db"],
)
def test_postgres_aliases_get_explicit_drivers(url):
    assert to_async_url(url).startswith("postgresql+asyncpg://u:p@h")
    assert to_sync_url(url).startswith("postgresql+psycopg2://u:p@h")


def test_rest_of_url_is_untouched():
    assert to_sync_url("postgresql+asyncpg://u:p%40x@h:5433/db?sslmode=require") == "postgresql+psycopg2://u:p%40x@h:5433/db?sslmode=require"


def test_non_postgres_urls_pass_through():
    assert to_sync_url("sqlite:///x.db") == "sqlite:///x.db"


def test_url_without_scheme_is_an_error():
    with pytest.raises(ValueError):
        to_sync_url("not-a-url")
