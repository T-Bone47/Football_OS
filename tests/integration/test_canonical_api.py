import pytest
import pytest_asyncio
import httpx

from app.db.session import get_session
from app.main import app
from app.normalization.schemas import NormalizedClub, NormalizedPlayer
from app.normalization.service import NormalizationService


@pytest_asyncio.fixture
async def canonical_client(integration_session):
    """Client with seeded canonical data (clubs, players)."""
    service = NormalizationService(integration_session)

    # Seed one club and one player
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
    await integration_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_get_competitions(canonical_client):
    res = await canonical_client.get("/api/v1/competitions")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 0  # No competitions seeded


async def test_get_clubs(canonical_client):
    res = await canonical_client.get("/api/v1/clubs")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "Manchester City"
    assert len(data[0]["identities"]) == 1
    assert data[0]["identities"][0]["provider"] == "api-football"
    assert data[0]["identities"][0]["provider_club_id"] == "50"


async def test_get_players(canonical_client):
    res = await canonical_client.get("/api/v1/players")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "M. Akanji"
    assert data[0]["primary_position"] == "Defender"
    assert len(data[0]["identities"]) == 1
    assert data[0]["identities"][0]["provider_player_id"] == "5"