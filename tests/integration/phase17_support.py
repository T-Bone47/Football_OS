"""Shared fixtures for Phase 17 integration tests.

The database is created and migrated with Alembic (not Base.metadata.create_all)
so the immutability triggers and CHECK constraints from 0014 are real. The
provider transport serves the committed real StatsBomb excerpts in
tests/fixtures/statsbomb, so these tests are deterministic and offline.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "statsbomb"
MATCHES = json.loads((FIX / "matches_43_106_argentina_france.json").read_text())
LINEUPS = json.loads((FIX / "lineups_3869685.json").read_text())
EVENTS = json.loads((FIX / "events_3869685_excerpt.json").read_text())
FINAL_ID = 3869685
DB_NAME = "fios_p17_test"


def _db_urls() -> tuple[str, str]:
    base = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://fios:fios@localhost:5432/fios_test")
    parsed = urlparse(base)
    url = urlunparse(parsed._replace(path=f"/{DB_NAME}"))
    admin = urlunparse(parsed._replace(scheme="postgresql", path="/postgres"))
    return url, admin


def migrated_database_url() -> str:
    url, admin = _db_urls()
    try:
        subprocess.run(["psql", admin, "-q", "-c", f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE);"],
                       check=True, capture_output=True, timeout=30)
        subprocess.run(["psql", admin, "-q", "-c", f"CREATE DATABASE {DB_NAME};"], check=True, capture_output=True, timeout=30)
        subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, env={**os.environ, "DATABASE_URL": url},
                       check=True, capture_output=True, timeout=180)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"PostgreSQL with psql/alembic not available for Phase 17 integration tests: {exc}")
    return url


TABLES_TO_RESET = [
    "ops_project_members", "ops_freshness_records", "ops_operational_metrics", "ops_worker_tasks",
    "ops_scheduled_jobs", "ops_worker_heartbeats",
    "ops_field_validation", "ops_incidents", "ops_notifications", "ops_alerts", "ops_watchlist_items",
    "ops_watchlists", "ops_decisions", "ops_projects", "ops_users", "ops_organizations", "ops_outcomes",
    "ops_inference_log", "ops_model_registry", "ops_feature_refresh", "ops_quality_reports", "ops_job_runs",
    "ops_contract_fingerprints", "ops_provider_probes", "ops_audit_events",
    "match_events", "match_lineups", "match_statistics", "match_teams", "player_match_stats", "matches",
    "player_identities", "club_identities", "player_season_stats", "players", "clubs", "competition_seasons",
    "competitions", "seasons", "data_snapshots", "ingestion_runs", "data_sources",
]


@pytest.fixture(scope="session")
def p17_db_url() -> str:
    return migrated_database_url()


@pytest_asyncio.fixture
async def p17_session(p17_db_url):
    engine = create_async_engine(p17_db_url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE " + ", ".join(TABLES_TO_RESET) + " RESTART IDENTITY CASCADE"))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.test_engine = engine
        s.test_sessionmaker = Session
        yield s
    await engine.dispose()


class StatsBombFixtureTransport(httpx.AsyncBaseTransport):
    """Serves real StatsBomb excerpts; `overrides` swap a path's payload or
    status to simulate drift, outages and corrections."""

    def __init__(self) -> None:
        self.payloads: dict[str, Any] = {
            "/matches/43/106.json": copy.deepcopy(MATCHES),
            f"/lineups/{FINAL_ID}.json": copy.deepcopy(LINEUPS),
            f"/events/{FINAL_ID}.json": copy.deepcopy(EVENTS),
        }
        self.overrides: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/data", 1)[-1]
        self.requests.append(path)
        if path in self.overrides:
            return self.overrides[path](request)
        if path in self.payloads:
            return httpx.Response(200, content=json.dumps(self.payloads[path]).encode(),
                                  headers={"content-type": "application/json"}, request=request)
        return httpx.Response(404, request=request)


async def bearer_headers(sessionmaker, role: str = "ANALYST") -> dict[str, str]:
    """A real bearer token for a freshly issued user in the test database.
    Integration tests authenticate exactly like a client would; there is no
    auth bypass in this suite."""
    import uuid as _uuid

    from app.phase17 import OpsRole
    from app.phase17.auth import issue_user

    async with sessionmaker() as s:
        _, token = await issue_user(s, "Integration tests", f"it-{_uuid.uuid4().hex[:10]}@example.test",
                                    "Integration test user", OpsRole(role))
        await s.commit()
    return {"Authorization": f"Bearer {token}"}
