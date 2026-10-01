"""Integration tests for Feature REST API endpoints (Phase 2 Slice 1).
Tests /features/registry, /players/{id}/features, and /matches/{id}/features.
"""
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
    MatchTeam,
    Player,
    PlayerMatchStats,
    Season,
)
from app.db.session import get_session
from app.main import app


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

    async with Session() as session:
        comp = Competition(type="LEAGUE", name="Premier League", country="England")
        season = Season(name="2025/2026", start_year=2025, end_year=2026)
        session.add_all([comp, season])
        await session.flush()

        comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
        club_a = Club(name="Liverpool", code="LIV", country="England")
        club_b = Club(name="Everton", code="EVE", country="England")
        player = Player(name="Mohamed Salah", primary_position="F", nationality="Egypt")
        session.add_all([comp_season, club_a, club_b, player])
        await session.flush()

        # Prior match on March 1
        m_prior = Match(provider="test-fixture", 
            competition_season_id=comp_season.id,
            date=datetime(2026, 3, 1, 15, 0, 0, tzinfo=timezone.utc),
            status="FINISHED",
            home_club_id=club_a.id,
            away_club_id=club_b.id,
        )
        session.add(m_prior)
        await session.flush()

        mt_prior_a = MatchTeam(
            match_id=m_prior.id,
            club_id=club_a.id,
            opponent_club_id=club_b.id,
            is_home=True,
            result="WIN",
            goals_for=2,
            goals_against=0,
        )
        mt_prior_b = MatchTeam(
            match_id=m_prior.id,
            club_id=club_b.id,
            opponent_club_id=club_a.id,
            is_home=False,
            result="LOSS",
            goals_for=0,
            goals_against=2,
        )
        pms_prior = PlayerMatchStats(
            provider="test-fixture",
            match_id=m_prior.id,
            club_id=club_a.id,
            player_id=player.id,
            position="F",
            minutes=90,
            goals=1,
            assists=1,
            shots_total=3,
            is_starter=True,
        )
        session.add_all([mt_prior_a, mt_prior_b, pms_prior])
        await session.flush()

        # Target match on March 8
        m_target = Match(provider="test-fixture", 
            competition_season_id=comp_season.id,
            date=datetime(2026, 3, 8, 15, 0, 0, tzinfo=timezone.utc),
            status="SCHEDULED",
            home_club_id=club_a.id,
            away_club_id=club_b.id,
        )
        session.add(m_target)
        await session.flush()

        mt_target_a = MatchTeam(
            match_id=m_target.id,
            club_id=club_a.id,
            opponent_club_id=club_b.id,
            is_home=True,
            result=None,
        )
        mt_target_b = MatchTeam(
            match_id=m_target.id,
            club_id=club_b.id,
            opponent_club_id=club_a.id,
            is_home=False,
            result=None,
        )
        session.add_all([mt_target_a, mt_target_b])
        await session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, player.id, m_target.id

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_features_registry(app_client):
    client, _, _ = app_client

    # All registry
    res = await client.get("/api/v1/features/registry")
    assert res.status_code == 200
    defs = res.json()
    assert len(defs) > 200

    # Filter by feature_set
    res_player = await client.get("/api/v1/features/registry?feature_set=player_match_v1")
    assert res_player.status_code == 200
    p_defs = res_player.json()
    assert len(p_defs) > 100
    assert all(d["feature_set"] == "player_match_v1" for d in p_defs)


@pytest.mark.asyncio
async def test_get_player_features_api(app_client):
    client, player_id, match_id = app_client

    # 1. Valid player features
    res = await client.get(f"/api/v1/players/{player_id}/features?match_id={match_id}")
    assert res.status_code == 200
    body = res.json()

    assert body["entity_type"] == "player"
    assert body["entity_id"] == str(player_id)
    assert body["feature_set"] == "player_match_v1"
    assert "goals_last_5" in body["features"]
    assert body["features"]["goals_last_5"] == 1
    assert body["features"]["assists_last_5"] == 1
    assert body["features"]["goals_per_90_last_5"] == 1.0

    # 2. Unknown player 404
    unknown_id = uuid.uuid4()
    res_404 = await client.get(f"/api/v1/players/{unknown_id}/features")
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_get_match_features_api(app_client):
    client, _, match_id = app_client

    # 1. Valid match features
    res = await client.get(f"/api/v1/matches/{match_id}/features")
    assert res.status_code == 200
    body = res.json()

    assert body["match_id"] == str(match_id)
    assert "home_features" in body
    assert "away_features" in body
    assert "match_context" in body
    # Rest days: March 8 - March 1 = 7.0 days
    assert body["match_context"]["home_days_since_previous_match"] == 7.0

    # 2. Unknown match 404
    unknown_id = uuid.uuid4()
    res_404 = await client.get(f"/api/v1/matches/{unknown_id}/features")
    assert res_404.status_code == 404
