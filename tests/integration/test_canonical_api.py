import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.normalization.schemas import NormalizedClub, NormalizedPlayer, NormalizedPlayerStats
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

    # Seed one club and one player
    async with Session() as session:
        service = NormalizationService(session)
        club = await service.upsert_club(
            "api-football",
            NormalizedClub(
                provider_id="50",
                name="Manchester City",
                code="MCI",
                country="England",
                venue_name="Etihad Stadium",
            ),
        )
        player = await service.upsert_player(
            "api-football",
            NormalizedPlayer(
                provider_id="5",
                name="M. Akanji",
                nationality="Switzerland",
                primary_position="Defender",
            ),
        )
        comp = await service.get_or_create_competition("Premier League", "England", "EPL")
        season = await service.get_or_create_season("2023", 2023, 2024)
        comp_season = await service.get_or_create_competition_season(comp.id, season.id)
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_get_competitions(app_client):
    res = await app_client.get("/api/v1/competitions")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "Premier League"


async def test_get_clubs(app_client):
    res = await app_client.get("/api/v1/clubs")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "Manchester City"
    assert len(data[0]["identities"]) == 1
    assert data[0]["identities"][0]["provider"] == "api-football"
    assert data[0]["identities"][0]["provider_club_id"] == "50"


async def test_get_players(app_client):
    res = await app_client.get("/api/v1/players")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "M. Akanji"
    assert data[0]["primary_position"] == "Defender"
    assert len(data[0]["identities"]) == 1
    assert data[0]["identities"][0]["provider_player_id"] == "5"
