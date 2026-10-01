"""Integration tests for Phase 3.2: Player Intelligence Engine API & PostgreSQL Persistence."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.canonical import (
    Club,
    Competition,
    CompetitionSeason,
    Match,
    Player,
    PlayerMatchStats,
    Season,
)
from app.db.session import get_session
from app.main import app


@pytest_asyncio.fixture
async def int_client(postgres_url):
    """Provides an isolated HTTP client and seeded database session."""
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

    player_id = uuid.uuid4()
    p2_id = uuid.uuid4()
    club_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    season_id = uuid.uuid4()
    cs_id = uuid.uuid4()
    match_id = uuid.uuid4()

    unique_suffix = uuid.uuid4().hex[:8]
    async with Session() as session:
        comp = Competition(id=comp_id, name=f"Premier League {unique_suffix}", country="England", code=f"EPL{unique_suffix[:4]}")
        season = Season(id=season_id, name=f"2024-2025-{unique_suffix}", start_year=2024, end_year=2025)
        cs = CompetitionSeason(id=cs_id, competition_id=comp_id, season_id=season_id)
        club = Club(id=club_id, name=f"Arsenal FC {unique_suffix}", country="England")
        p1 = Player(id=player_id, name=f"M. Odegaard {unique_suffix}", primary_position="Midfielder")
        p2 = Player(id=p2_id, name=f"B. Saka {unique_suffix}", primary_position="Attacker")
        m = Match(
            id=match_id,
            competition_season_id=cs_id,
            home_club_id=club_id,
            away_club_id=club_id,
            date=datetime(2025, 2, 1, 15, 0, tzinfo=timezone.utc),
            status="FINISHED",
        )
        pms1 = PlayerMatchStats(
            provider="test-fixture",
            id=uuid.uuid4(),
            match_id=match_id,
            player_id=player_id,
            club_id=club_id,
            minutes=90,
            is_starter=True,
            rating=8.1,
            passes_total=64,
            passes_key=3,
            tackles_total=2,
            interceptions=1,
            goals=1,
            assists=1,
        )
        pms2 = PlayerMatchStats(
            provider="test-fixture",
            id=uuid.uuid4(),
            match_id=match_id,
            player_id=p2_id,
            club_id=club_id,
            minutes=85,
            is_starter=True,
            rating=7.8,
            shots_total=3,
            shots_on_target=2,
            goals=1,
            assists=0,
        )

        session.add_all([comp, season, cs, club, p1, p2, m, pms1, pms2])
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, player_id, p2_id

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_player_intelligence_endpoint(int_client):
    client, p1_id, _ = int_client

    resp = await client.get(f"/api/v1/players/{p1_id}/intelligence")
    assert resp.status_code == 200
    data = resp.json()

    assert data["player_id"] == str(p1_id)
    assert "M. Odegaard" in data["player_name"]
    assert data["position_group"] == "MID"
    assert data["sample_minutes"] == 90
    assert data["sample_matches"] == 1
    # 90 minutes is below the 270 gate -> INSUFFICIENT_SAMPLE
    assert data["data_status"] == "INSUFFICIENT_SAMPLE"
    assert data["confidence"] == "INSUFFICIENT_SAMPLE"
    assert "contribution_vector" in data
    assert "intelligence_vector" in data
    assert "contextual_adjustments" in data
    assert "explanations" in data
    assert "why_low_confidence" in data["explanations"]
    assert "provenance" in data
    assert data["provenance"]["calculation_version"] == "1.0"


@pytest.mark.asyncio
async def test_get_player_trajectory_endpoint(int_client):
    client, p1_id, _ = int_client

    resp = await client.get(f"/api/v1/players/{p1_id}/trajectory")
    assert resp.status_code == 200
    data = resp.json()

    assert data["player_id"] == str(p1_id)
    assert data["total_recorded_matches"] == 1
    assert data["cumulative_minutes"] == 90
    assert len(data["timeline"]) == 1
    t0 = data["timeline"][0]
    assert t0["minutes"] == 90
    assert t0["goals"] == 1
    assert t0["assists"] == 1
    assert t0["match_impact"] > 0.0


@pytest.mark.asyncio
async def test_get_player_benchmarks_endpoint(int_client):
    client, p1_id, _ = int_client

    resp = await client.get(f"/api/v1/players/{p1_id}/benchmarks")
    assert resp.status_code == 200
    data = resp.json()

    assert data["player_id"] == str(p1_id)
    assert data["position_group"] == "MID"
    assert data["sample_minutes"] == 90
    # Gate enforced: percentiles are None
    assert data["benchmark_status"] == "INSUFFICIENT_SAMPLE"
    assert data["average_percentile"] is None


@pytest.mark.asyncio
async def test_get_similar_players_multi_mode(int_client):
    client, p1_id, _ = int_client

    # Test contribution mode
    r_contrib = await client.get(f"/api/v1/players/{p1_id}/similar?mode=contribution")
    assert r_contrib.status_code == 200, f"Error: {r_contrib.text}"

    # Test replacement mode
    r_rep = await client.get(f"/api/v1/players/{p1_id}/similar?mode=replacement")
    assert r_rep.status_code == 200

    # Test role mode
    r_role = await client.get(f"/api/v1/players/{p1_id}/similar?mode=role")
    assert r_role.status_code == 200


@pytest.mark.asyncio
async def test_player_not_found(int_client):
    client, _, _ = int_client
    random_id = uuid.uuid4()

    r1 = await client.get(f"/api/v1/players/{random_id}/intelligence")
    assert r1.status_code == 404

    r2 = await client.get(f"/api/v1/players/{random_id}/trajectory")
    assert r2.status_code == 404

    r3 = await client.get(f"/api/v1/players/{random_id}/benchmarks")
    assert r3.status_code == 404
