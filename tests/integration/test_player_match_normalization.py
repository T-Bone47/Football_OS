import json
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.canonical import (
    Club,
    Match,
    MatchLineup,
    Player,
    PlayerIdentity,
    PlayerMatchStats,
)
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun, IngestionStatus
from app.normalization.service import NormalizationService


@pytest_asyncio.fixture
async def db_session(postgres_url):
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"fios_test not reachable: {exc}")

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_player_match_normalization_and_idempotency(db_session):
    service = NormalizationService(db_session)

    # 1. Seed Match fixture 1492387
    fixture_payload = {
        "response": [
            {
                "fixture": {
                    "id": 1492387,
                    "date": "2026-03-15T19:00:00+00:00",
                    "status": {"short": "FT"},
                },
                "league": {
                    "id": 71,
                    "name": "Serie A",
                    "country": "Brazil",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": 126, "name": "Sao Paulo"},
                    "away": {"id": 119, "name": "Internacional"},
                },
                "goals": {"home": 2, "away": 1},
                "score": {"fulltime": {"home": 2, "away": 1}},
            }
        ]
    }
    matches = await service.normalize_fixtures_payload("api-football", fixture_payload)
    assert len(matches) == 1
    match = matches[0]

    # 2. Seed MatchLineup for fixture 1492387 (to test lineup cross-referencing)
    lineups_payload = {
        "parameters": {"fixture": "1492387"},
        "response": [
            {
                "team": {"id": 126, "name": "Sao Paulo"},
                "formation": "4-2-3-1",
                "startXI": [
                    {
                        "player": {
                            "id": 47368,
                            "name": "Jonathan Calleri",
                            "number": 9,
                            "pos": "F",
                            "grid": "4:1",
                        }
                    }
                ],
                "substitutes": [
                    {
                        "player": {
                            "id": 41188,
                            "name": "Andre Silva",
                            "number": 17,
                            "pos": "F",
                            "grid": None,
                        }
                    }
                ],
            },
            {
                "team": {"id": 119, "name": "Internacional"},
                "formation": "4-3-3",
                "startXI": [
                    {
                        "player": {
                            "id": 306552,
                            "name": "Anthoni",
                            "number": 12,
                            "pos": "G",
                            "grid": "1:1",
                        }
                    }
                ],
                "substitutes": [],
            },
        ],
    }
    lineups = await service.normalize_lineups_payload("api-football", lineups_payload)
    assert len(lineups) == 3

    # 3. Normalize player match statistics payload
    player_stats_payload = {
        "parameters": {"fixture": "1492387"},
        "response": [
            {
                "team": {"id": 119, "name": "Internacional"},
                "players": [
                    {
                        "player": {
                            "id": 306552,
                            "name": "Anthoni",
                            "photo": "https://media.api-sports.io/football/players/306552.png",
                        },
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
            {
                "team": {"id": 126, "name": "Sao Paulo"},
                "players": [
                    {
                        "player": {
                            "id": 47368,
                            "name": "Jonathan Calleri",
                            "photo": "https://media.api-sports.io/football/players/47368.png",
                        },
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
                        "player": {
                            "id": 41188,
                            "name": "Andre Silva",
                            "photo": "https://media.api-sports.io/football/players/41188.png",
                        },
                        "statistics": [
                            {
                                "games": {
                                    "minutes": 17,
                                    "number": 17,
                                    "position": "F",
                                    "rating": "6.47",
                                    "captain": False,
                                    "substitute": False,  # Note: API reports false, but lineup says substitute!
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
        ],
    }

    ds_source = DataSource(name="api-football")
    db_session.add(ds_source)
    await db_session.flush()

    run_pms = IngestionRun(
        data_source_id=ds_source.id,
        endpoint="fixtures/players",
        status=IngestionStatus.SUCCESS,
    )
    db_session.add(run_pms)
    await db_session.flush()

    snap_pms = DataSnapshot(
        ingestion_run_id=run_pms.id,
        sha256="dummy_pms_sha",
        storage_location="dummy_pms",
        size_bytes=100,
    )
    db_session.add(snap_pms)
    await db_session.commit()

    test_snap_id = snap_pms.id
    p_stats_run1 = await service.normalize_player_match_stats_payload(
        "api-football", player_stats_payload, snapshot_id=test_snap_id
    )
    assert len(p_stats_run1) == 3

    # Check database counts
    total_stats = (await db_session.execute(select(func.count(PlayerMatchStats.id)))).scalar_one()
    assert total_stats == 3

    total_players = (await db_session.execute(select(func.count(Player.id)))).scalar_one()
    assert total_players == 3

    total_identities = (await db_session.execute(select(func.count(PlayerIdentity.id)))).scalar_one()
    assert total_identities == 3

    # Inspect normalized player match performance records
    calleri = (
        await db_session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.provider_player_id == "47368")
        )
    ).scalar_one()
    assert calleri.is_starter is True
    assert calleri.is_substitute is False
    assert calleri.is_captain is True
    assert calleri.formation_position == "4:1"  # Derived from MatchLineup
    assert calleri.minutes == 73
    assert calleri.rating == 7.45
    assert calleri.goals == 1
    assert calleri.shots_total == 3
    assert calleri.passes_total == 18
    assert calleri.pass_accuracy == 78.0
    assert calleri.penalties_won == 1
    assert calleri.snapshot_id == test_snap_id

    # Check substitute player whose substitute status was resolved from MatchLineup
    andre = (
        await db_session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.provider_player_id == "41188")
        )
    ).scalar_one()
    assert andre.is_starter is False  # From Lineup cross-reference
    assert andre.is_substitute is True  # From Lineup cross-reference
    assert andre.minutes == 17
    assert andre.rating == 6.47

    # Check goalkeeper record
    anthoni = (
        await db_session.execute(
            select(PlayerMatchStats).where(PlayerMatchStats.provider_player_id == "306552")
        )
    ).scalar_one()
    assert anthoni.is_starter is True
    assert anthoni.formation_position == "1:1"
    assert anthoni.saves == 4
    assert anthoni.goals_conceded == 2
    assert anthoni.clean_sheet is False
    assert anthoni.dribbles_past is None  # Strict NULL preserved
    assert anthoni.penalties_won is None  # Strict NULL preserved

    # 4. IDEMPOTENCY TEST: Run second normalization with identical payload
    stats_ids_before = sorted(
        [str(id_) for id_ in (await db_session.execute(select(PlayerMatchStats.id))).scalars().all()]
    )
    players_count_before = (await db_session.execute(select(func.count(Player.id)))).scalar_one()
    clubs_count_before = (await db_session.execute(select(func.count(Club.id)))).scalar_one()

    p_stats_run2 = await service.normalize_player_match_stats_payload(
        "api-football", player_stats_payload, snapshot_id=test_snap_id
    )
    assert len(p_stats_run2) == 3

    stats_ids_after = sorted(
        [str(id_) for id_ in (await db_session.execute(select(PlayerMatchStats.id))).scalars().all()]
    )
    players_count_after = (await db_session.execute(select(func.count(Player.id)))).scalar_one()
    clubs_count_after = (await db_session.execute(select(func.count(Club.id)))).scalar_one()

    # Assert 0 duplicates and exact primary key stability
    assert stats_ids_before == stats_ids_after
    assert players_count_before == players_count_after
    assert clubs_count_before == clubs_count_after
