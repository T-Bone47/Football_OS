from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.canonical import (
    Club,
    ClubIdentity,
    Competition,
    CompetitionSeason,
    Match,
    MatchTeam,
    Season,
)
from app.normalization.service import NormalizationService


@pytest_asyncio.fixture
async def session(postgres_url):
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"fios_test not reachable: {exc}")
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_normalize_fixtures_finished_and_scheduled(session):
    service = NormalizationService(session)

    payload = {
        "response": [
            {
                "fixture": {
                    "id": 1492387,
                    "referee": "Bruno Arleu",
                    "timezone": "UTC",
                    "date": "2026-09-20T00:00:00+00:00",
                    "timestamp": 1789862400,
                    "venue": {"id": 269, "name": "Morumbi", "city": "Sao Paulo"},
                    "status": {
                        "long": "Match Finished",
                        "short": "FT",
                        "elapsed": 90,
                    },
                },
                "league": {
                    "id": 71,
                    "name": "Serie A",
                    "country": "Brazil",
                    "season": 2026,
                    "round": "Regular Season - 28",
                },
                "teams": {
                    "home": {"id": 126, "name": "Sao Paulo", "winner": True, "logo": "http://sp.png"},
                    "away": {"id": 119, "name": "Internacional", "winner": False, "logo": "http://int.png"},
                },
                "goals": {"home": 1, "away": 0},
                "score": {
                    "halftime": {"home": 1, "away": 0},
                    "fulltime": {"home": 1, "away": 0},
                    "extratime": {"home": None, "away": None},
                    "penalty": {"home": None, "away": None},
                },
            },
            {
                "fixture": {
                    "id": 1557413,
                    "referee": "Robert Jones",
                    "timezone": "UTC",
                    "date": "2026-09-20T13:00:00+00:00",
                    "timestamp": 1789909200,
                    "venue": {"id": 555, "name": "Etihad Stadium", "city": "Manchester"},
                    "status": {
                        "long": "Not Started",
                        "short": "NS",
                        "elapsed": None,
                    },
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "season": 2026,
                    "round": "Regular Season - 5",
                },
                "teams": {
                    "home": {"id": 50, "name": "Manchester City", "winner": None},
                    "away": {"id": 746, "name": "Sunderland", "winner": None},
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

    matches = await service.normalize_fixtures_payload("api-football", payload)
    assert len(matches) == 2

    # Verify Matches in DB
    db_matches = (await session.execute(select(Match).order_by(Match.date))).scalars().all()
    assert len(db_matches) == 2

    # 1. Finished match verification
    m_finished = db_matches[0]
    assert m_finished.provider_fixture_id == "1492387"
    assert m_finished.status == "FINISHED"
    assert m_finished.status_detail == "Match Finished"
    assert m_finished.round == "Regular Season - 28"
    assert m_finished.stage == "Regular Season"
    assert m_finished.venue_name == "Morumbi"
    assert m_finished.venue_city == "Sao Paulo"
    assert m_finished.referee == "Bruno Arleu"
    assert m_finished.home_score == 1
    assert m_finished.away_score == 0
    assert m_finished.halftime_home_score == 1
    assert m_finished.halftime_away_score == 0
    assert m_finished.fulltime_home_score == 1
    assert m_finished.fulltime_away_score == 0
    assert m_finished.winner_club_id == m_finished.home_club_id

    # 2. MatchTeam verification for finished match
    stmt_teams = select(MatchTeam).where(MatchTeam.match_id == m_finished.id).order_by(MatchTeam.is_home.desc())
    mt_list = (await session.execute(stmt_teams)).scalars().all()
    assert len(mt_list) == 2

    home_mt, away_mt = mt_list[0], mt_list[1]
    assert home_mt.is_home is True
    assert home_mt.club_id == m_finished.home_club_id
    assert home_mt.opponent_club_id == m_finished.away_club_id
    assert home_mt.result == "WIN"
    assert home_mt.points == 3
    assert home_mt.goals_for == 1
    assert home_mt.goals_against == 0

    assert away_mt.is_home is False
    assert away_mt.club_id == m_finished.away_club_id
    assert away_mt.opponent_club_id == m_finished.home_club_id
    assert away_mt.result == "LOSS"
    assert away_mt.points == 0
    assert away_mt.goals_for == 0
    assert away_mt.goals_against == 1

    # 3. Scheduled match verification
    m_sched = db_matches[1]
    assert m_sched.provider_fixture_id == "1557413"
    assert m_sched.status == "SCHEDULED"
    assert m_sched.home_score is None
    assert m_sched.away_score is None
    assert m_sched.winner_club_id is None

    stmt_sched_teams = select(MatchTeam).where(MatchTeam.match_id == m_sched.id)
    sched_teams = (await session.execute(stmt_sched_teams)).scalars().all()
    assert len(sched_teams) == 2
    for mt in sched_teams:
        assert mt.result is None
        assert mt.points is None
        assert mt.goals_for is None
        assert mt.goals_against is None


async def test_normalize_fixtures_idempotent(session):
    service = NormalizationService(session)

    payload = {
        "response": [
            {
                "fixture": {
                    "id": 1492387,
                    "date": "2026-09-20T00:00:00+00:00",
                    "status": {"short": "FT", "long": "Match Finished"},
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
            }
        ]
    }

    # First run
    matches1 = await service.normalize_fixtures_payload("api-football", payload)
    assert len(matches1) == 1
    m1_id = matches1[0].id

    # Check database counts
    matches_db1 = (await session.execute(select(Match))).scalars().all()
    assert len(matches_db1) == 1
    match_teams_db1 = (await session.execute(select(MatchTeam))).scalars().all()
    assert len(match_teams_db1) == 2
    clubs_db1 = (await session.execute(select(Club))).scalars().all()
    assert len(clubs_db1) == 2
    club_identities1 = (await session.execute(select(ClubIdentity))).scalars().all()
    assert len(club_identities1) == 2

    # Second run with exact same payload
    matches2 = await service.normalize_fixtures_payload("api-football", payload)
    assert len(matches2) == 1
    assert matches2[0].id == m1_id

    # Verify no duplicate records were created
    matches_db2 = (await session.execute(select(Match))).scalars().all()
    assert len(matches_db2) == 1
    assert matches_db2[0].id == m1_id

    match_teams_db2 = (await session.execute(select(MatchTeam))).scalars().all()
    assert len(match_teams_db2) == 2

    clubs_db2 = (await session.execute(select(Club))).scalars().all()
    assert len(clubs_db2) == 2

    club_identities2 = (await session.execute(select(ClubIdentity))).scalars().all()
    assert len(club_identities2) == 2


async def test_normalize_fixtures_draw_result(session):
    service = NormalizationService(session)

    payload = {
        "response": [
            {
                "fixture": {
                    "id": 200001,
                    "date": "2026-09-20T16:00:00+00:00",
                    "status": {"short": "FT", "long": "Match Finished"},
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": 50, "name": "Manchester City", "winner": None},
                    "away": {"id": 42, "name": "Arsenal", "winner": None},
                },
                "goals": {"home": 2, "away": 2},
                "score": {
                    "halftime": {"home": 1, "away": 1},
                    "fulltime": {"home": 2, "away": 2},
                },
            }
        ]
    }

    matches = await service.normalize_fixtures_payload("api-football", payload)
    assert len(matches) == 1
    m = matches[0]
    assert m.home_score == 2
    assert m.away_score == 2
    assert m.winner_club_id is None

    stmt_teams = select(MatchTeam).where(MatchTeam.match_id == m.id)
    teams = (await session.execute(stmt_teams)).scalars().all()
    assert len(teams) == 2
    for mt in teams:
        assert mt.result == "DRAW"
        assert mt.points == 1
        assert mt.goals_for == 2
        assert mt.goals_against == 2


async def test_normalize_fixtures_snapshot(session, tmp_path):
    import json
    from app.db.models.provenance import DataSource, IngestionRun, DataSnapshot, IngestionStatus

    ds = DataSource(name="api-football", base_url="https://api-football.com")
    session.add(ds)
    await session.flush()

    run = IngestionRun(
        data_source_id=ds.id,
        endpoint="fixtures",
        status=IngestionStatus.SUCCESS,
        record_count=1,
    )
    session.add(run)
    await session.flush()

    fixture_payload = {
        "response": [
            {
                "fixture": {
                    "id": 888001,
                    "date": "2026-09-20T14:00:00+00:00",
                    "status": {"short": "FT", "long": "Match Finished"},
                    "venue": {"name": "Old Trafford", "city": "Manchester"},
                    "referee": "Michael Oliver",
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "season": 2026,
                    "round": "Regular Season - 5",
                },
                "teams": {
                    "home": {"id": 33, "name": "Manchester United", "winner": True},
                    "away": {"id": 34, "name": "Newcastle", "winner": False},
                },
                "goals": {"home": 3, "away": 1},
                "score": {
                    "halftime": {"home": 1, "away": 0},
                    "fulltime": {"home": 3, "away": 1},
                },
            }
        ]
    }

    file_path = tmp_path / "fixtures_snapshot.json"
    file_path.write_text(json.dumps(fixture_payload), encoding="utf-8")

    snapshot = DataSnapshot(
        ingestion_run_id=run.id,
        storage_location=str(file_path),
        sha256="abc123sha256",
        size_bytes=len(file_path.read_bytes()),
    )
    session.add(snapshot)
    await session.commit()

    service = NormalizationService(session)
    result = await service.normalize_snapshot(snapshot.id)

    assert result["entity"] == "matches"
    assert result["count"] == 1
    assert result["snapshot_id"] == str(snapshot.id)

    # Verify provenance on Match
    m = (await session.execute(select(Match).where(Match.provider_fixture_id == "888001"))).scalar_one()
    assert m.snapshot_id == snapshot.id
    assert m.home_score == 3
    assert m.away_score == 1
