import uuid
import httpx
import pytest
import pytest_asyncio
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

    # Seed 2 fixtures: one finished, one scheduled
    async with Session() as session:
        service = NormalizationService(session)
        payload = {
            "response": [
                {
                    "fixture": {
                        "id": 1001,
                        "referee": "Michael Oliver",
                        "timezone": "UTC",
                        "date": "2026-09-20T12:30:00+00:00",
                        "venue": {"name": "Etihad Stadium", "city": "Manchester"},
                        "status": {"short": "FT", "long": "Match Finished"},
                    },
                    "league": {
                        "id": 39,
                        "name": "Premier League",
                        "country": "England",
                        "season": 2026,
                        "round": "Regular Season - 5",
                    },
                    "teams": {
                        "home": {"id": 50, "name": "Manchester City", "winner": True},
                        "away": {"id": 42, "name": "Arsenal", "winner": False},
                    },
                    "goals": {"home": 2, "away": 1},
                    "score": {
                        "halftime": {"home": 1, "away": 0},
                        "fulltime": {"home": 2, "away": 1},
                        "extratime": {"home": None, "away": None},
                        "penalty": {"home": None, "away": None},
                    },
                },
                {
                    "fixture": {
                        "id": 1002,
                        "referee": "Anthony Taylor",
                        "timezone": "UTC",
                        "date": "2026-09-20T15:00:00+00:00",
                        "venue": {"name": "Anfield", "city": "Liverpool"},
                        "status": {"short": "NS", "long": "Not Started"},
                    },
                    "league": {
                        "id": 39,
                        "name": "Premier League",
                        "country": "England",
                        "season": 2026,
                        "round": "Regular Season - 5",
                    },
                    "teams": {
                        "home": {"id": 40, "name": "Liverpool", "winner": None},
                        "away": {"id": 49, "name": "Chelsea", "winner": None},
                    },
                    "goals": {"home": None, "away": None},
                    "score": {
                        "halftime": {"home": None, "away": None},
                        "fulltime": {"home": None, "away": None},
                        "extratime": {"home": None, "away": None},
                        "penalty": {"home": None, "away": None},
                    },
                },
            ]
        }
        await service.normalize_fixtures_payload("api-football", payload)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_list_matches(app_client):
    res = await app_client.get("/api/v1/matches")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2

    # Matches are ordered by date desc
    m_latest = data[0]
    assert m_latest["provider_fixture_id"] == "1002"
    assert m_latest["status"] == "SCHEDULED"
    assert m_latest["home_club_name"] == "Liverpool"
    assert m_latest["away_club_name"] == "Chelsea"

    m_earlier = data[1]
    assert m_earlier["provider_fixture_id"] == "1001"
    assert m_earlier["status"] == "FINISHED"
    assert m_earlier["home_score"] == 2
    assert m_earlier["away_score"] == 1


async def test_filter_matches_by_status(app_client):
    res_finished = await app_client.get("/api/v1/matches?status=FINISHED")
    assert res_finished.status_code == 200
    data_finished = res_finished.json()
    assert len(data_finished) == 1
    assert data_finished[0]["provider_fixture_id"] == "1001"

    res_sched = await app_client.get("/api/v1/matches?status=SCHEDULED")
    assert res_sched.status_code == 200
    data_sched = res_sched.json()
    assert len(data_sched) == 1
    assert data_sched[0]["provider_fixture_id"] == "1002"


async def test_filter_matches_by_club(app_client):
    # First get matches to find Manchester City's club_id
    res_all = await app_client.get("/api/v1/matches")
    mci_club_id = res_all.json()[1]["home_club_id"]

    res_mci = await app_client.get(f"/api/v1/matches?club_id={mci_club_id}")
    assert res_mci.status_code == 200
    data_mci = res_mci.json()
    assert len(data_mci) == 1
    assert data_mci[0]["home_club_name"] == "Manchester City"


async def test_get_match_detail(app_client):
    res_all = await app_client.get("/api/v1/matches?status=FINISHED")
    match_id = res_all.json()[0]["id"]

    res = await app_client.get(f"/api/v1/matches/{match_id}")
    assert res.status_code == 200
    match = res.json()

    assert match["id"] == match_id
    assert match["provider_fixture_id"] == "1001"
    assert match["status"] == "FINISHED"
    assert match["referee"] == "Michael Oliver"
    assert match["venue_name"] == "Etihad Stadium"
    assert match["venue_city"] == "Manchester"
    assert match["round"] == "Regular Season - 5"
    assert match["home_club"]["name"] == "Manchester City"
    assert match["away_club"]["name"] == "Arsenal"

    # Score breakdown
    assert match["score"]["home"] == 2
    assert match["score"]["away"] == 1
    assert match["score"]["halftime_home"] == 1
    assert match["score"]["halftime_away"] == 0
    assert match["score"]["fulltime_home"] == 2
    assert match["score"]["fulltime_away"] == 1

    # Match teams
    assert len(match["teams"]) == 2
    home_team = next(t for t in match["teams"] if t["is_home"])
    assert home_team["result"] == "WIN"
    assert home_team["points"] == 3
    assert home_team["goals_for"] == 2
    assert home_team["goals_against"] == 1

    away_team = next(t for t in match["teams"] if not t["is_home"])
    assert away_team["result"] == "LOSS"
    assert away_team["points"] == 0
    assert away_team["goals_for"] == 1
    assert away_team["goals_against"] == 2


async def test_get_match_detail_not_found(app_client):
    random_id = uuid.uuid4()
    res = await app_client.get(f"/api/v1/matches/{random_id}")
    assert res.status_code == 404
    assert res.json()["detail"] == "Match not found"


async def test_get_match_detail_invalid_uuid(app_client):
    res = await app_client.get("/api/v1/matches/invalid-uuid-format")
    assert res.status_code == 422
