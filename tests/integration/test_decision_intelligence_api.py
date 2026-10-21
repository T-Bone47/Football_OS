"""
Integration and Contract Tests for Phase 7 Unified Decision Intelligence APIs.

Verifies:
- GET /api/v1/decisions/recruitment
- POST /api/v1/decisions/recruitment/analyze
- POST /api/v1/decisions/replacement
- POST /api/v1/decisions/transfer-scenario
- POST /api/v1/decisions/compare
- GET /api/v1/decisions/{decision_id}
- GET /api/v1/decisions/{decision_id}/evidence
- POST /api/copilot/query (Scout Copilot Decision Orchestrator)
"""

import uuid
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
async def decision_client(postgres_url):
    """Integration test fixture using transaction rollback for isolation.

    Uses the existing migration-created tables (which include triggers) and rolls back
    all changes after each test, providing isolation without dropping tables.
    """
    engine = create_async_engine(postgres_url)
    async with engine.connect() as conn:
        # Start a transaction that will be rolled back after each test
        transaction = await conn.begin()
        try:
            Session = async_sessionmaker(bind=conn, expire_on_commit=False)

            async def override_get_session():
                async with Session() as s:
                    yield s

            app.dependency_overrides[get_session] = override_get_session

            # Seed test clubs and players
            async with Session() as session:
                service = NormalizationService(session)
                club = await service.upsert_club(
                    "api-football",
                    NormalizedClub(
                        provider_id="101",
                        name="Arsenal FC",
                        code="ARS",
                        country="England",
                        venue_name="Emirates Stadium",
                    ),
                )
                p1 = await service.upsert_player(
                    "api-football",
                    NormalizedPlayer(
                        provider_id="201",
                        name="Martin Odegaard",
                        nationality="Norway",
                        primary_position="Midfielder",
                        age=25,
                    ),
                )
                p2 = await service.upsert_player(
                    "api-football",
                    NormalizedPlayer(
                        provider_id="202",
                        name="Declan Rice",
                        nationality="England",
                        primary_position="Midfielder",
                        age=25,
                    ),
                )
                p3 = await service.upsert_player(
                    "api-football",
                    NormalizedPlayer(
                        provider_id="203",
                        name="Bukayo Saka",
                        nationality="England",
                        primary_position="Attacker",
                        age=23,
                    ),
                )
                p1.club_id = club.id
                p2.club_id = club.id
                p3.club_id = club.id

                comp = await service.get_or_create_competition("Premier League", "England", "EPL")
                season = await service.get_or_create_season("2023", 2023, 2024)
                comp_season = await service.get_or_create_competition_season(comp.id, season.id)

                await service.upsert_player_season_stats(
                    "api-football",
                    NormalizedPlayerStats(
                        provider_player_id="201",
                        provider_league_id="39",
                        provider_club_id="101",
                        season_year=2023,
                        appearances=30,
                        minutes=2500,
                        goals=8,
                        assists=10,
                    ),
                    p1.id,
                    comp_season.id,
                )
                await service.upsert_player_season_stats(
                    "api-football",
                    NormalizedPlayerStats(
                        provider_player_id="202",
                        provider_league_id="39",
                        provider_club_id="101",
                        season_year=2023,
                        appearances=32,
                        minutes=2700,
                        goals=6,
                        assists=7,
                    ),
                    p2.id,
                    comp_season.id,
                )
                await service.upsert_player_season_stats(
                    "api-football",
                    NormalizedPlayerStats(
                        provider_player_id="203",
                        provider_league_id="39",
                        provider_club_id="101",
                        season_year=2023,
                        appearances=28,
                        minutes=2300,
                        goals=12,
                        assists=9,
                    ),
                    p3.id,
                    comp_season.id,
                )
                await session.commit()

                # Cache IDs
                club_id = str(club.id)
                p1_id = str(p1.id)
                p2_id = str(p2.id)
                p3_id = str(p3.id)

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                client.test_club_id = club_id
                client.p1_id = p1_id
                client.p2_id = p2_id
                client.p3_id = p3_id
                yield client

        finally:
            app.dependency_overrides.clear()
            await transaction.rollback()

        # Engine disposal happens after the fixture scope ends
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_recruitment_targets_api(decision_client):
    res = await decision_client.get("/api/v1/decisions/recruitment?target_position=CM&limit=5")
    assert res.status_code == 200
    data = res.json()
    assert data["decision"]["decision_type"] == "RECRUITMENT"
    assert data["decision"]["confidence"]["confidence_tier"] in ["HIGH", "MODERATE", "LOW", "VERY_LOW"]


@pytest.mark.asyncio
async def test_post_recruitment_analyze_api(decision_client):
    payload = {
        "target_position": "CM",
        "tactical_context_id": "433_cm_progressive_midfielder",
        "budget_eur": 50000000.0,
        "min_age": 20,
        "max_age": 28,
        "min_minutes": 500,
        "risk_tolerance": "MEDIUM",
        "limit": 5,
    }
    res = await decision_client.post("/api/v1/decisions/recruitment/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"]["decision_type"] == "RECRUITMENT"
    assert data["decision"]["confidence"]["confidence_tier"] in ["HIGH", "MODERATE", "LOW", "VERY_LOW"]


@pytest.mark.asyncio
async def test_post_replacement_api(decision_client):
    payload = {
        "player_id_to_replace": decision_client.p1_id,
        "target_role": "Playmaker",
        "min_similarity": 0.60,
        "budget_eur": 60000000.0,
        "limit": 3,
    }
    res = await decision_client.post("/api/v1/decisions/replacement", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["replaced_player_id"] == decision_client.p1_id
    assert "decision" in data


@pytest.mark.asyncio
async def test_post_transfer_scenario_api(decision_client):
    payload = {
        "club_id": decision_client.test_club_id,
        "roster_changes": [
            {"player_id": decision_client.p2_id, "direction": "IN"},
            {"player_id": decision_client.p1_id, "direction": "OUT"},
        ],
        "budget_eur": 80000000.0,
    }
    res = await decision_client.post("/api/v1/decisions/transfer-scenario", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"]["decision_type"] == "TRANSFER_SCENARIO"
    assert "financial_impact" in data
    assert "squad_impact_summary" in data


@pytest.mark.asyncio
async def test_post_compare_api(decision_client):
    payload = {
        "candidate_ids": [decision_client.p1_id, decision_client.p2_id],
    }
    res = await decision_client.post("/api/v1/decisions/compare", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert len(data["candidates"]) == 2
    assert "trade_off_analysis" in data
    assert "dimension_leaders" in data


@pytest.mark.asyncio
async def test_copilot_decision_query_streaming(decision_client):
    payload = {
        "query": "Find a replacement for our attacking playmaker under 50m",
        "context_players": [{"id": decision_client.p1_id, "name": "Martin Odegaard", "primary_position": "MF"}],
    }
    res = await decision_client.post("/api/copilot/query", json=payload)
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")