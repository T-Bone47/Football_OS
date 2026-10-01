import uuid
import httpx
import pytest
import pytest_asyncio
from phase17_support import bearer_headers
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.normalization.service import NormalizationService


@pytest_asyncio.fixture
async def app_client(postgres_url):
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"fios_test not reachable: {exc}")

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    # Seed match and intelligence entities
    async with Session() as session:
        service = NormalizationService(session)
        # 1. Match
        fixture_payload = {
            "response": [
                {
                    "fixture": {
                        "id": 1492387,
                        "date": "2026-09-20T00:00:00+00:00",
                        "status": {"short": "FT", "long": "Match Finished"},
                        "venue": {"name": "Morumbi", "city": "Sao Paulo"},
                    },
                    "league": {
                        "id": 71,
                        "name": "Serie A",
                        "country": "Brazil",
                        "season": 2026,
                    },
                    "teams": {
                        "home": {"id": 126, "name": "Sao Paulo", "winner": True},
                        "away": {"id": 119, "name": "Internacional", "winner": False},
                    },
                    "goals": {"home": 1, "away": 0},
                    "score": {
                        "halftime": {"home": 1, "away": 0},
                        "fulltime": {"home": 1, "away": 0},
                    },
                },
                {
                    "fixture": {
                        "id": 999999,
                        "date": "2026-09-21T00:00:00+00:00",
                        "status": {"short": "NS", "long": "Not Started"},
                        "venue": {"name": "Maracana", "city": "Rio"},
                    },
                    "league": {
                        "id": 71,
                        "name": "Serie A",
                        "country": "Brazil",
                        "season": 2026,
                    },
                    "teams": {
                        "home": {"id": 126, "name": "Sao Paulo", "winner": None},
                        "away": {"id": 119, "name": "Internacional", "winner": None},
                    },
                    "goals": {"home": None, "away": None},
                    "score": {
                        "halftime": {"home": None, "away": None},
                        "fulltime": {"home": None, "away": None},
                    },
                },
            ]
        }
        matches = await service.normalize_fixtures_payload("api-football", fixture_payload)

        # 2. Events for 1492387
        events_payload = {
            "parameters": {"fixture": "1492387"},
            "response": [
                {
                    "time": {"elapsed": 15, "extra": None},
                    "team": {"id": 126, "name": "Sao Paulo"},
                    "player": {"id": 47368, "name": "Jonathan Calleri"},
                    "assist": {"id": None, "name": None},
                    "type": "Goal",
                    "detail": "Penalty",
                    "comments": None,
                },
                {
                    "time": {"elapsed": 73, "extra": None},
                    "team": {"id": 126, "name": "Sao Paulo"},
                    "player": {"id": 47368, "name": "Jonathan Calleri"},
                    "assist": {"id": 106510, "name": "Aldemir Ferreira"},
                    "type": "subst",
                    "detail": "Substitution 3",
                    "comments": None,
                },
            ],
        }
        await service.normalize_events_payload("api-football", events_payload)

        # 3. Lineups for 1492387
        lineups_payload = {
            "parameters": {"fixture": "1492387"},
            "response": [
                {
                    "team": {"id": 126, "name": "Sao Paulo"},
                    "formation": "3-4-2-1",
                    "coach": {"id": 3059, "name": "Dorival Júnior"},
                    "startXI": [
                        {"player": {"id": 10081, "name": "Rafael", "number": 23, "pos": "G", "grid": "1:1"}},
                    ],
                    "substitutes": [
                        {"player": {"id": 41188, "name": "André Silva", "number": 17, "pos": "F", "grid": None}},
                    ],
                }
            ],
        }
        await service.normalize_lineups_payload("api-football", lineups_payload)

        # 4. Statistics for 1492387
        stats_payload = {
            "parameters": {"fixture": "1492387"},
            "response": [
                {
                    "team": {"id": 126, "name": "Sao Paulo"},
                    "statistics": [
                        {"type": "Ball Possession", "value": "44%"},
                        {"type": "Total Shots", "value": 6},
                        {"type": "Shots on Goal", "value": 1},
                        {"type": "Red Cards", "value": 0},
                        {"type": "Yellow Cards", "value": 1},
                    ],
                }
            ],
        }
        await service.normalize_statistics_payload("api-football", stats_payload)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=await bearer_headers(Session)) as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_match_events(app_client):
    # Retrieve match ID
    res = await app_client.get("/api/v1/matches")
    assert res.status_code == 200
    matches = res.json()
    target_match = next(m for m in matches if m["provider_fixture_id"] == "1492387")
    match_id = target_match["id"]

    # Events endpoint
    ev_res = await app_client.get(f"/api/v1/matches/{match_id}/events")
    assert ev_res.status_code == 200
    events = ev_res.json()
    assert len(events) == 2
    assert events[0]["minute"] == 15
    assert events[0]["event_type"] == "GOAL"
    assert events[0]["event_detail"] == "Penalty"
    assert events[0]["player_name"] == "Jonathan Calleri"
    assert events[0]["club_name"] == "Sao Paulo"

    assert events[1]["minute"] == 73
    assert events[1]["event_type"] == "SUBSTITUTION"
    assert events[1]["assist_player_name"] == "Aldemir Ferreira"


@pytest.mark.asyncio
async def test_get_match_lineups(app_client):
    res = await app_client.get("/api/v1/matches")
    matches = res.json()
    match_id = next(m for m in matches if m["provider_fixture_id"] == "1492387")["id"]

    lu_res = await app_client.get(f"/api/v1/matches/{match_id}/lineups")
    assert lu_res.status_code == 200
    lineups = lu_res.json()
    assert len(lineups) == 2

    starter = next(l for l in lineups if l["is_starter"] is True)
    assert starter["player_name"] == "Rafael"
    assert starter["jersey_number"] == 23
    assert starter["position"] == "G"
    assert starter["formation_position"] == "1:1"
    assert starter["formation"] == "3-4-2-1"
    assert starter["coach_name"] == "Dorival Júnior"

    sub = next(l for l in lineups if l["is_starter"] is False)
    assert sub["player_name"] == "André Silva"
    assert sub["jersey_number"] == 17
    assert sub["position"] == "F"


@pytest.mark.asyncio
async def test_get_match_statistics(app_client):
    res = await app_client.get("/api/v1/matches")
    matches = res.json()
    match_id = next(m for m in matches if m["provider_fixture_id"] == "1492387")["id"]

    st_res = await app_client.get(f"/api/v1/matches/{match_id}/statistics")
    assert st_res.status_code == 200
    stats = st_res.json()
    assert len(stats) == 1
    s = stats[0]
    assert s["club_name"] == "Sao Paulo"
    assert s["possession_pct"] == 44.0
    assert s["shots_total"] == 6
    assert s["shots_on_target"] == 1
    assert s["red_cards"] == 0
    assert s["yellow_cards"] == 1
    assert s["expected_goals"] is None


@pytest.mark.asyncio
async def test_match_intelligence_not_found(app_client):
    random_id = str(uuid.uuid4())
    assert (await app_client.get(f"/api/v1/matches/{random_id}/events")).status_code == 404
    assert (await app_client.get(f"/api/v1/matches/{random_id}/lineups")).status_code == 404
    assert (await app_client.get(f"/api/v1/matches/{random_id}/statistics")).status_code == 404


@pytest.mark.asyncio
async def test_match_without_intelligence_data_returns_empty(app_client):
    res = await app_client.get("/api/v1/matches")
    matches = res.json()
    empty_match = next(m for m in matches if m["provider_fixture_id"] == "999999")
    match_id = empty_match["id"]

    assert (await app_client.get(f"/api/v1/matches/{match_id}/events")).json() == []
    assert (await app_client.get(f"/api/v1/matches/{match_id}/lineups")).json() == []
    assert (await app_client.get(f"/api/v1/matches/{match_id}/statistics")).json() == []
