"""Explicit sync/async Postgres URL handling (handoff R3).

The API runs on asyncpg; Alembic runs on psycopg2 (both pinned in requirements.txt). A bare
``postgresql://`` resolves to a driver chosen by the installed SQLAlchemy/driver mix, which is
how a clean ``alembic upgrade head`` broke before. Name the driver explicitly, in one place.
Non-Postgres URLs are returned unchanged.
"""
from __future__ import annotations

ASYNC_DRIVER = "postgresql+asyncpg"
SYNC_DRIVER = "postgresql+psycopg2"
_POSTGRES_SCHEMES = {"postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg2", "postgresql+psycopg"}


def _swap_scheme(url: str, driver: str) -> str:
    scheme, sep, rest = url.partition("://")
    if not sep:
        raise ValueError("database URL must look like scheme://...")
    if scheme.lower() not in _POSTGRES_SCHEMES:
        return url
    return f"{driver}://{rest}"


def to_async_url(url: str) -> str:
    return _swap_scheme(url, ASYNC_DRIVER)


def to_sync_url(url: str) -> str:
    return _swap_scheme(url, SYNC_DRIVER)
