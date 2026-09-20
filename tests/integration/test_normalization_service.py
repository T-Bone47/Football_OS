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
    Player,
    PlayerIdentity,
    PlayerSeasonStats,
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


async def test_normalize_teams_idempotent(session):
    service = NormalizationService(session)
    payload = {
        "response": [
            {
                "team": {
                    "id": 50,
                    "name": "Manchester City",
                    "code": "MCI",
                    "country": "England",
                    "founded": 1880,
                    "logo": "https://media.api-sports.io/football/teams/50.png",
                },
                "venue": {
                    "id": 555,
                    "name": "Etihad Stadium",
                    "capacity": 55097,
                },
            },
            {
                "team": {
                    "id": 42,
                    "name": "Arsenal",
                    "code": "ARS",
                    "country": "England",
                    "founded": 1886,
                    "logo": "https://media.api-sports.io/football/teams/42.png",
                },
                "venue": {
                    "id": 494,
                    "name": "Emirates Stadium",
                    "capacity": 60383,
                },
            },
        ]
    }

    # First normalization run
    clubs1 = await service.normalize_teams_payload("api-football", payload)
    assert len(clubs1) == 2

    # Query DB
    clubs_in_db = (await session.execute(select(Club))).scalars().all()
    assert len(clubs_in_db) == 2
    identities = (await session.execute(select(ClubIdentity))).scalars().all()
    assert len(identities) == 2

    mci_id = (
        await session.execute(
            select(ClubIdentity).where(ClubIdentity.provider_club_id == "50")
        )
    ).scalar_one()
    assert mci_id.resolution_method == "DIRECT_PROVIDER_ID"
    assert mci_id.confidence == 1.0

    # Second normalization run with same payload must be completely idempotent
    clubs2 = await service.normalize_teams_payload("api-football", payload)
    assert len(clubs2) == 2

    clubs_after = (await session.execute(select(Club))).scalars().all()
    assert len(clubs_after) == 2
    identities_after = (await session.execute(select(ClubIdentity))).scalars().all()
    assert len(identities_after) == 2


async def test_normalize_players_links_to_clubs_and_stats(session):
    service = NormalizationService(session)

    # 1. First normalize the club
    team_payload = {
        "response": [
            {
                "team": {
                    "id": 50,
                    "name": "Manchester City",
                    "country": "England",
                }
            }
        ]
    }
    await service.normalize_teams_payload("api-football", team_payload)

    # 2. Normalize player belonging to Manchester City
    player_payload = {
        "response": [
            {
                "player": {
                    "id": 5,
                    "name": "M. Akanji",
                    "firstname": "Manuel Obafemi",
                    "lastname": "Akanji",
                    "birth": {"date": "1995-07-19", "country": "Switzerland"},
                    "nationality": "Switzerland",
                    "height": "188 cm",
                    "weight": "91 kg",
                    "photo": "https://media.api-sports.io/football/players/5.png",
                },
                "statistics": [
                    {
                        "team": {"id": 50, "name": "Manchester City"},
                        "league": {"id": 39, "name": "Premier League", "season": 2023},
                        "games": {
                            "appearences": 30,
                            "lineups": 28,
                            "minutes": 2500,
                            "position": "Defender",
                            "rating": "7.28",
                        },
                        "goals": {"total": 2, "assists": 1, "conceded": 0},
                        "tackles": {"total": 42},
                        "passes": {"total": 2296},
                    }
                ],
            }
        ]
    }

    players = await service.normalize_players_payload("api-football", player_payload)
    assert len(players) == 1

    # Verify Player
    p = (await session.execute(select(Player))).scalar_one()
    assert p.name == "M. Akanji"
    assert p.height_cm == 188
    assert p.primary_position == "Defender"

    # Verify PlayerIdentity
    p_id = (await session.execute(select(PlayerIdentity))).scalar_one()
    assert p_id.player_id == p.id
    assert p_id.provider == "api-football"
    assert p_id.provider_player_id == "5"

    # Verify Competition & Season
    comp = (await session.execute(select(Competition))).scalar_one()
    assert comp.name == "Premier League"
    assert comp.country == "England"

    season = (await session.execute(select(Season))).scalar_one()
    assert season.start_year == 2023

    comp_season = (await session.execute(select(CompetitionSeason))).scalar_one()
    assert comp_season.competition_id == comp.id
    assert comp_season.season_id == season.id

    # Verify PlayerSeasonStats
    stats = (await session.execute(select(PlayerSeasonStats))).scalar_one()
    assert stats.player_id == p.id
    assert stats.competition_season_id == comp_season.id
    assert stats.appearances == 30
    assert stats.minutes == 2500
    assert stats.goals == 2
    assert stats.assists == 1
    assert stats.rating == 7.28
    assert stats.raw_stats["passes"] == {"total": 2296}

    # Verify relationship to Club
    mci = (
        await session.execute(
            select(Club).where(Club.name == "Manchester City")
        )
    ).scalar_one()
    assert stats.club_id == mci.id

    # Second run for player idempotency
    players_again = await service.normalize_players_payload("api-football", player_payload)
    assert len(players_again) == 1
    total_players = (await session.execute(select(Player))).scalars().all()
    assert len(total_players) == 1
    total_stats = (await session.execute(select(PlayerSeasonStats))).scalars().all()
    assert len(total_stats) == 1
