"""Phase 18 — health and status are measured, never declared (R5, R6, N2, N4).

Each test changes the real system and checks the endpoint notices: a
database at an older migration, a Silver row with no snapshot, an empty or
populated model registry.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import text

from app.db.models.canonical import Club, Competition, CompetitionSeason, Match, Season
from app.db.session import get_session
from app.main import app
from app.observability.system_health import expected_migration_head


@pytest.fixture
async def api(p17_session):
    async def override():
        async with p17_session.test_sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        yield client
    app.dependency_overrides.clear()


async def test_liveness_is_process_facts_only(api):
    r = await api.get("/health/live")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "ALIVE"
    assert body["memory_rss_mb"] > 0 and body["uptime_s"] >= 0
    assert "demo_fixtures_enabled" in body
    assert (await api.get("/health")).json()["status"] == "ALIVE"


async def test_ready_only_when_database_is_at_code_head(api, p17_session):
    head = expected_migration_head()
    assert head is not None
    r = await api.get("/health/ready")
    assert r.status_code == 200 and r.json()["status"] == "READY"
    assert r.json()["database"]["migration_version"] == head

    # Simulate a deploy whose code is ahead of the database.
    await p17_session.execute(text("UPDATE alembic_version SET version_num = '0013'"))
    await p17_session.commit()
    try:
        r = await api.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "NOT_READY"
        assert any("0013" in reason for reason in r.json()["reasons"])
        assert (await api.get("/readiness")).status_code == 503
    finally:
        await p17_session.execute(text("UPDATE alembic_version SET version_num = :h"), {"h": head})
        await p17_session.commit()


async def _h(session) -> dict[str, str]:
    from app.phase17 import OpsRole
    from app.phase17.auth import issue_user

    _, token = await issue_user(session, "Org", f"v-{uuid.uuid4().hex[:6]}@example.test", "V", OpsRole.VIEWER)
    await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def test_status_endpoints_require_authentication(api):
    assert (await api.get("/data-status")).status_code == 401
    assert (await api.get("/model-status")).status_code == 401


async def test_data_status_measures_provenance_coverage(api, p17_session):
    h = await _h(p17_session)
    empty = (await api.get("/data-status", headers=h)).json()
    assert empty["status"] == "NO_DATA"
    assert empty["latest_snapshot_age_hours"] == "NOT_MEASURED"
    assert empty["provenance_coverage"]["matches"]["coverage"] == "NOT_MEASURED"
    assert empty["schema_version"] == expected_migration_head()

    # A match row with no snapshot link: provenance coverage must drop.
    comp = Competition(name="Test League", country="Nowhere", type="LEAGUE")
    season = Season(name="2099", start_year=2099, end_year=2099)
    p17_session.add_all([comp, season])
    await p17_session.flush()
    cs = CompetitionSeason(competition_id=comp.id, season_id=season.id)
    home = Club(name=f"Home {uuid.uuid4().hex[:4]}", country="Nowhere")
    away = Club(name=f"Away {uuid.uuid4().hex[:4]}", country="Nowhere")
    p17_session.add_all([cs, home, away])
    await p17_session.flush()
    p17_session.add(Match(provider="test-fixture", provider_fixture_id="t1", competition_season_id=cs.id,
                          home_club_id=home.id, away_club_id=away.id,
                          date=datetime(2099, 5, 1, tzinfo=timezone.utc), status="SCHEDULED"))
    await p17_session.commit()

    body = (await api.get("/data-status", headers=h)).json()
    assert body["counts"]["matches"] == 1
    assert body["provenance_coverage"]["matches"] == {"rows": 1, "rows_with_snapshot": 0, "coverage": 0.0}
    assert body["status"] == "PROVENANCE_GAPS" and "matches" in body["tables_with_provenance_gaps"]


async def test_model_status_reads_the_registry(api, p17_session):
    h = await _h(p17_session)
    body = (await api.get("/model-status", headers=h)).json()
    assert body["status"] == "NO_MODELS_REGISTERED" and body["models"] == []
    assert "active_engines" not in body  # the old hardcoded engine list is gone

    await p17_session.execute(text(
        "INSERT INTO ops_model_registry (id, domain, model_id, model_version, feature_version, dataset_version, "
        "supported_competitions, deployment_state, validation_metrics, min_history_matches) VALUES "
        "(gen_random_uuid(), 'match_outcome', 'm', '1', 'f1', 'd1', '[]', 'REGISTERED', '{}', 5)"))
    await p17_session.commit()
    body = (await api.get("/model-status", headers=h)).json()
    assert body["status"] == "NO_SERVABLE_MODEL"
    assert body["models"][0]["status"] == "REGISTERED" and body["models"][0]["has_validation_evidence"] is False


async def test_deep_health_requires_authentication(api):
    assert (await api.get("/health/deep")).status_code == 401
