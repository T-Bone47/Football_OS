"""Integration tests for Squad Intelligence & Transfer Simulation APIs (Phase 5A)."""
import pytest
import pytest_asyncio
from phase17_support import bearer_headers
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.normalization.schemas import NormalizedClub, NormalizedPlayer
from app.normalization.service import NormalizationService


@pytest_asyncio.fixture
async def app_client(postgres_url):
    engine = create_async_engine(postgres_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"fios_test not reachable: {exc}")

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    async with Session() as session:
        service = NormalizationService(session)
        club = await service.upsert_club(
            "api-football",
            NormalizedClub(
                provider_id="50",
                name="Arsenal",
                code="ARS",
                country="England",
            ),
        )
        p1 = await service.upsert_player(
            "api-football",
            NormalizedPlayer(
                provider_id="101",
                name="Bukayo Saka",
                nationality="England",
                primary_position="Attacker",
            ),
        )
        p2 = await service.upsert_player(
            "api-football",
            NormalizedPlayer(
                provider_id="102",
                name="Declan Rice",
                nationality="England",
                primary_position="Midfielder",
            ),
        )
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=await bearer_headers(Session)) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_squad_build_get(app_client):
    res = await app_client.get("/api/v1/squads/build?formation=4-3-3")
    assert res.status_code == 200
    data = res.json()
    assert data["formation"] == "4-3-3"
    assert len(data["positions"]) == 11
    assert "squad_quality_score" in data
    assert "role_coverage_score" in data
    assert "depth_risk_score" in data
    assert "depth_risk_level" in data


@pytest.mark.asyncio
async def test_squad_analyze_post(app_client):
    payload = {"formation": "4-2-3-1"}
    res = await app_client.post("/api/v1/squads/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["formation"] == "4-2-3-1"
    assert len(data["positions"]) == 11


@pytest.mark.asyncio
async def test_simulate_transfer_post(app_client):
    payload = {
        "formation": "4-3-3",
        "outgoing_player_ids": [],
        "incoming_player_ids": [],
    }
    res = await app_client.post("/api/v1/squads/simulate-transfer", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "before" in data
    assert "after" in data
    assert "impact" in data
    assert "delta_squad_quality" in data["impact"]
    assert "summary" in data["impact"]
    assert "recommendations" in data["impact"]


@pytest.mark.asyncio
async def test_scenario_transfer_post(app_client):
    payload = {
        "formation": "3-5-2",
        "outgoing_player_ids": [],
        "incoming_player_ids": [],
    }
    res = await app_client.post("/api/v1/scenarios/transfer", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["before"]["formation"] == "3-5-2"
    assert "impact" in data
