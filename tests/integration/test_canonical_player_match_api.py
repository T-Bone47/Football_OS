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

    # Seed match and player match performance
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
                    "goals": {"home": 2, "away": 1},
                    "score": {
                        "halftime": {"home": 1, "away": 0},
                        "fulltime": {"home": 2, "away": 1},
                    },
                }
            ]
        }
        await service.normalize_fixtures_payload("api-football", fixture_payload)

        # 2. Lineup
        lineups_payload = {
            "parameters": {"fixture": "1492387"},
            "response": [
                {
                    "team": {"id": 126, "name": "Sao Paulo"},
                    "formation": "4-2-3-1",
                    "startXI": [
                        {"player": {"id": 47368, "name": "Jonathan Calleri", "number": 9, "pos": "F", "grid": "4:1"}},
                    ],
                    "substitutes": [
                        {"player": {"id": 41188, "name": "Andre Silva", "number": 17, "pos": "F", "grid": None}},
                    ],
                },
                {
                    "team": {"id": 119, "name": "Internacional"},
                    "formation": "4-3-3",
                    "startXI": [
                        {"player": {"id": 306552, "name": "Anthoni", "number": 12, "pos": "G", "grid": "1:1"}},
                    ],
                    "substitutes": [],
                },
            ],
        }
        await service.normalize_lineups_payload("api-football", lineups_payload)

        # 3. Player Match Stats
        p_stats_payload = {
            "parameters": {"fixture": "1492387"},
            "response": [
                {
                    "team": {"id": 126, "name": "Sao Paulo"},
                    "players": [
                        {
                            "player": {"id": 47368, "name": "Jonathan Calleri", "photo": "https://img/47368.png"},
                            "statistics": [
                                {
                                    "games": {
                                        "minutes": 73,
                                        "number": 9,
                                        "position": "F",
                                        "rating": "7.45",
                                        "captain": True,
                                        "substitute": False,
                                    },
                                    "offsides": 1,
                                    "shots": {"total": 3, "on": 2},
                                    "goals": {"total": 1, "conceded": None, "assists": 0, "saves": None},
                                    "passes": {"total": 18, "key": 2, "accuracy": "78%"},
                                    "tackles": {"total": 1, "blocks": 0, "interceptions": 1},
                                    "duels": {"total": 12, "won": 7},
                                    "dribbles": {"attempts": 2, "success": 1, "past": 0},
                                    "fouls": {"drawn": 3, "committed": 2},
                                    "cards": {"yellow": 1, "red": 0},
                                    "penalty": {
                                        "won": 1,
                                        "commited": 0,
                                        "scored": 1,
                                        "missed": 0,
                                        "saved": None,
                                    },
                                }
                            ],
                        },
                        {
                            "player": {"id": 41188, "name": "Andre Silva", "photo": "https://img/41188.png"},
                            "statistics": [
                                {
                                    "games": {
                                        "minutes": 17,
                                        "number": 17,
                                        "position": "F",
                                        "rating": "6.47",
                                        "captain": False,
                                        "substitute": False,
                                    },
                                    "offsides": 0,
                                    "shots": {"total": 1, "on": 1},
                                    "goals": {"total": 0, "conceded": None, "assists": 0, "saves": None},
                                    "passes": {"total": 4, "key": 0, "accuracy": "75"},
                                    "tackles": {"total": 0, "blocks": 0, "interceptions": 0},
                                    "duels": {"total": 3, "won": 1},
                                    "dribbles": {"attempts": 0, "success": 0, "past": None},
                                    "fouls": {"drawn": 0, "committed": 1},
                                    "cards": {"yellow": 0, "red": 0},
                                    "penalty": {
                                        "won": None,
                                        "commited": None,
                                        "scored": 0,
                                        "missed": None,
                                        "saved": None,
                                    },
                                }
                            ],
                        },
                    ],
                },
                {
                    "team": {"id": 119, "name": "Internacional"},
                    "players": [
                        {
                            "player": {"id": 306552, "name": "Anthoni", "photo": "https://img/306552.png"},
                            "statistics": [
                                {
                                    "games": {
                                        "minutes": 90,
                                        "number": 12,
                                        "position": "G",
                                        "rating": "5.91",
                                        "captain": False,
                                        "substitute": False,
                                    },
                                    "offsides": 0,
                                    "shots": {"total": 0, "on": 0},
                                    "goals": {"total": 0, "conceded": 2, "assists": 0, "saves": 4},
                                    "passes": {"total": 29, "key": 0, "accuracy": "19"},
                                    "tackles": {"total": 0, "blocks": 0, "interceptions": 0},
                                    "duels": {"total": 1, "won": 1},
                                    "dribbles": {"attempts": 0, "success": 0, "past": None},
                                    "fouls": {"drawn": 1, "committed": 0},
                                    "cards": {"yellow": 0, "red": 0},
                                    "penalty": {
                                        "won": None,
                                        "commited": None,
                                        "scored": 0,
                                        "missed": None,
                                        "saved": None,
                                    },
                                }
                            ],
                        }
                    ],
                },
            ],
        }
        await service.normalize_player_match_stats_payload("api-football", p_stats_payload)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=await bearer_headers(Session)) as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_match_player_stats_and_alias(app_client):
    # 1. Get Match ID
    m_res = await app_client.get("/api/v1/matches")
    assert m_res.status_code == 200
    matches = m_res.json()
    match_id = matches[0]["id"]

    # 2. Test /matches/{id}/player-stats
    res = await app_client.get(f"/api/v1/matches/{match_id}/player-stats")
    assert res.status_code == 200
    p_stats = res.json()
    assert len(p_stats) == 3

    # Check Calleri record
    calleri = next(p for p in p_stats if p["player_name"] == "Jonathan Calleri")
    assert calleri["club_name"] == "Sao Paulo"
    assert calleri["is_starter"] is True
    assert calleri["is_substitute"] is False
    assert calleri["is_captain"] is True
    assert calleri["formation_position"] == "4:1"
    assert calleri["minutes"] == 73
    assert calleri["rating"] == 7.45
    assert calleri["goals"] == 1
    assert calleri["shots_total"] == 3
    assert calleri["shots_on_target"] == 2
    assert calleri["passes_total"] == 18
    assert calleri["pass_accuracy"] == 78.0
    assert calleri["penalties_won"] == 1
    assert calleri["clean_sheet"] is None

    # Check Andre Silva record (substitute cross-checked from lineup)
    andre = next(p for p in p_stats if p["player_name"] == "Andre Silva")
    assert andre["is_starter"] is False
    assert andre["is_substitute"] is True
    assert andre["minutes"] == 17
    assert andre["rating"] == 6.47

    # Check Goalkeeper record
    anthoni = next(p for p in p_stats if p["player_name"] == "Anthoni")
    assert anthoni["club_name"] == "Internacional"
    assert anthoni["position"] == "G"
    assert anthoni["saves"] == 4
    assert anthoni["goals_conceded"] == 2
    assert anthoni["clean_sheet"] is False

    # 3. Test alias /matches/{id}/players
    alias_res = await app_client.get(f"/api/v1/matches/{match_id}/players")
    assert alias_res.status_code == 200
    assert len(alias_res.json()) == 3
    assert alias_res.json() == p_stats


@pytest.mark.asyncio
async def test_get_player_match_history(app_client):
    # Find Calleri's player ID
    m_res = await app_client.get("/api/v1/matches")
    match_id = m_res.json()[0]["id"]
    ps_res = await app_client.get(f"/api/v1/matches/{match_id}/player-stats")
    calleri = next(p for p in ps_res.json() if p["player_name"] == "Jonathan Calleri")
    player_id = calleri["player_id"]
    club_id = calleri["club_id"]

    # Query player's match history
    hist_res = await app_client.get(f"/api/v1/players/{player_id}/matches")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) == 1
    assert history[0]["player_name"] == "Jonathan Calleri"
    assert history[0]["goals"] == 1
    assert history[0]["rating"] == 7.45

    # Test with club_id filter
    filt_res = await app_client.get(f"/api/v1/players/{player_id}/matches?club_id={club_id}")
    assert filt_res.status_code == 200
    assert len(filt_res.json()) == 1

    # Test with pagination
    page_res = await app_client.get(f"/api/v1/players/{player_id}/matches?limit=10&offset=0")
    assert page_res.status_code == 200
    assert len(page_res.json()) == 1


@pytest.mark.asyncio
async def test_player_match_api_404_errors(app_client):
    random_id = uuid.uuid4()

    # Unknown match
    res_match = await app_client.get(f"/api/v1/matches/{random_id}/player-stats")
    assert res_match.status_code == 404
    assert res_match.json()["detail"] == "Match not found"

    # Unknown player
    res_player = await app_client.get(f"/api/v1/players/{random_id}/matches")
    assert res_player.status_code == 404
    assert res_player.json()["detail"] == "Player not found"
