"""Integration tests for Player Role Discovery, Profile Persistence, and Similarity APIs (Phase 2 Slice 2)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import httpx
import pytest
import pytest_asyncio
from phase17_support import bearer_headers
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.canonical import (
    Club,
    Competition,
    CompetitionSeason,
    FeatureSnapshot,
    Match,
    Player,
    PlayerRoleProfile,
    Season,
)
from app.db.session import get_session
from app.main import app
from app.roles.service import RoleService


@pytest_asyncio.fixture
async def db_session(postgres_url):
    """Provides an isolated database session with freshly synced tables."""
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


@pytest_asyncio.fixture
async def api_client(postgres_url):
    """Provides an httpx client with test database dependency overrides."""
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

    players_data = {}
    async with Session() as session:
        comp = Competition(type="LEAGUE", name="La Liga", country="Spain")
        season = Season(name="2025/2026", start_year=2025, end_year=2026)
        session.add_all([comp, season])
        await session.flush()

        comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
        club = Club(name="Barcelona", code="FCB", country="Spain")
        session.add_all([comp_season, club])
        await session.flush()

        # Player 1: Pedri (Qualified Midfielder, Playmaker / Creator)
        p1 = Player(name="Pedri", primary_position="M", nationality="Spain")
        # Player 2: Gavi (Qualified Midfielder, Ball Winner)
        p2 = Player(name="Gavi", primary_position="M", nationality="Spain")
        # Player 3: Pau Cubarsi (Qualified Defender, Ball-Playing Defender)
        p3 = Player(name="Pau Cubarsi", primary_position="D", nationality="Spain")
        # Player 4: Young Sub (Insufficient Sample, 90 mins)
        p4 = Player(name="Marc Bernal", primary_position="M", nationality="Spain")

        session.add_all([p1, p2, p3, p4])
        await session.flush()

        now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Feature Snapshots
        snap1 = FeatureSnapshot(
            entity_type="player",
            entity_id=p1.id,
            feature_set="player_match_v1",
            as_of=now,
            features={
                "minutes_last_5": 450,
                "appearances_last_5": 5,
                "passes_per_90_last_5": 68.5,
                "pass_accuracy_avg_last_5": 91.2,
                "passes_key_per_90_last_5": 2.8,
                "assists_per_90_last_5": 0.45,
                "dribbles_success_last_5": 12,
                "tackles_per_90_last_5": 1.2,
            },
        )
        snap2 = FeatureSnapshot(
            entity_type="player",
            entity_id=p2.id,
            feature_set="player_match_v1",
            as_of=now,
            features={
                "minutes_last_5": 450,
                "appearances_last_5": 5,
                "passes_per_90_last_5": 42.0,
                "pass_accuracy_avg_last_5": 84.0,
                "tackles_per_90_last_5": 4.1,
                "interceptions_last_5": 8,
                "duels_won_last_5": 38,
                "fouls_committed_last_5": 9,
            },
        )
        snap3 = FeatureSnapshot(
            entity_type="player",
            entity_id=p3.id,
            feature_set="player_match_v1",
            as_of=now,
            features={
                "minutes_last_5": 450,
                "appearances_last_5": 5,
                "passes_per_90_last_5": 62.0,
                "pass_accuracy_avg_last_5": 92.5,
                "tackles_per_90_last_5": 2.5,
                "blocks_last_5": 6,
                "interceptions_last_5": 7,
            },
        )
        snap4 = FeatureSnapshot(
            entity_type="player",
            entity_id=p4.id,
            feature_set="player_match_v1",
            as_of=now,
            features={
                "minutes_last_5": 90,
                "appearances_last_5": 1,
                "passes_per_90_last_5": 50.0,
            },
        )
        session.add_all([snap1, snap2, snap3, snap4])
        await session.commit()

        players_data = {
            "p1_id": p1.id,
            "p2_id": p2.id,
            "p3_id": p3.id,
            "p4_id": p4.id,
            "as_of": now,
        }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=await bearer_headers(Session)) as client:
        yield client, players_data

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_role_profile_persistence_and_idempotency(db_session):
    """Tests saving PlayerRoleProfile to PostgreSQL and verifies strict idempotency."""
    service = RoleService(db_session)

    # 1. Setup Player and Snapshot
    player = Player(name="Luka Modric", primary_position="M", nationality="Croatia")
    db_session.add(player)
    await db_session.flush()

    eval_time = datetime(2026, 3, 10, 15, 0, 0, tzinfo=timezone.utc)
    snap = FeatureSnapshot(
        entity_type="player",
        entity_id=player.id,
        feature_set="player_match_v1",
        as_of=eval_time,
        features={
            "minutes_last_5": 450,
            "appearances_last_5": 5,
            "passes_per_90_last_5": 72.0,
            "pass_accuracy_avg_last_5": 90.5,
            "passes_key_per_90_last_5": 2.4,
            "assists_per_90_last_5": 0.40,
        },
    )
    db_session.add(snap)
    await db_session.flush()

    # 2. Compute and save
    profile_1 = await service.compute_and_save_role_profile(player.id, as_of=eval_time)
    await db_session.commit()

    assert profile_1.role_status == "QUALIFIED"
    assert profile_1.primary_archetype is not None
    assert profile_1.position_group == "MID"
    assert "distribution" in profile_1.profile_scores
    initial_id = profile_1.id

    # 3. Re-run with identical parameters: must update same record, not create duplicate
    profile_2 = await service.compute_and_save_role_profile(player.id, as_of=eval_time)
    await db_session.commit()

    assert profile_2.id == initial_id

    # Verify count in database
    count_stmt = select(PlayerRoleProfile).where(PlayerRoleProfile.player_id == player.id)
    records = (await db_session.execute(count_stmt)).scalars().all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_role_profile_sample_size_gate(db_session):
    """Verifies that players with under 450 minutes receive INSUFFICIENT_SAMPLE without fabricated archetype."""
    service = RoleService(db_session)

    player = Player(name="Youth Talent", primary_position="F", nationality="Spain")
    db_session.add(player)
    await db_session.flush()

    eval_time = datetime(2026, 3, 10, 15, 0, 0, tzinfo=timezone.utc)
    snap = FeatureSnapshot(
        entity_type="player",
        entity_id=player.id,
        feature_set="player_match_v1",
        as_of=eval_time,
        features={
            "minutes_last_5": 90,
            "appearances_last_5": 1,
            "goals_last_5": 1,
        },
    )
    db_session.add(snap)
    await db_session.flush()

    profile = await service.compute_and_save_role_profile(player.id, as_of=eval_time)
    await db_session.commit()

    assert profile.role_status == "INSUFFICIENT_SAMPLE"
    assert profile.primary_archetype is None
    assert profile.secondary_archetype is None
    assert profile.archetype_confidence is None
    assert profile.sample_minutes == 90


@pytest.mark.asyncio
async def test_api_role_endpoints(api_client):
    """Tests all canonical role and similarity REST API endpoints."""
    client, data = api_client
    p1_id = data["p1_id"]
    p2_id = data["p2_id"]
    p3_id = data["p3_id"]
    p4_id = data["p4_id"]

    # 1. GET /api/v1/players/{id}/role (Pedri - Qualified)
    resp = await client.get(f"/api/v1/players/{p1_id}/role")
    assert resp.status_code == 200
    r_json = resp.json()
    assert r_json["player_name"] == "Pedri"
    assert r_json["role_status"] == "QUALIFIED"
    assert r_json["primary_archetype"] is not None
    assert len(r_json["dominant_dimensions"]) > 0

    # 2. GET /api/v1/players/{id}/role (Young Sub - Insufficient Sample)
    resp = await client.get(f"/api/v1/players/{p4_id}/role")
    assert resp.status_code == 200
    r_json = resp.json()
    assert r_json["role_status"] == "INSUFFICIENT_SAMPLE"
    assert r_json["primary_archetype"] is None
    assert "below the minimum threshold" in r_json["summary"]

    # 3. GET /api/v1/players/{id}/role-profile
    resp = await client.get(f"/api/v1/players/{p1_id}/role-profile")
    assert resp.status_code == 200
    prof_json = resp.json()
    assert "profile_scores" in prof_json
    assert "distribution" in prof_json["profile_scores"]
    assert "feature_vector" in prof_json
    assert prof_json["position_group"] == "MID"

    # Pre-populate profiles for candidate similarity search
    await client.get(f"/api/v1/players/{p2_id}/role-profile")
    await client.get(f"/api/v1/players/{p3_id}/role-profile")

    # 4. GET /api/v1/players/{id}/similar (Search candidates similar to Pedri)
    resp = await client.get(f"/api/v1/players/{p1_id}/similar?limit=5")
    assert resp.status_code == 200
    sim_json = resp.json()
    assert sim_json["target_player_name"] == "Pedri"
    assert len(sim_json["results"]) > 0
    first_match = sim_json["results"][0]
    assert "overall_similarity" in first_match
    assert "statistical_similarity" in first_match
    assert "why_similar" in first_match
    assert "why_different" in first_match

    # 5. Position filter on similar players
    resp = await client.get(f"/api/v1/players/{p1_id}/similar?position_filter=DEF")
    assert resp.status_code == 200
    def_results = resp.json()["results"]
    for item in def_results:
        assert item["position_group"] == "DEF"

    # 6. GET /api/v1/players/{id}/similarity/{other_id} (Pedri vs Gavi head-to-head)
    resp = await client.get(f"/api/v1/players/{p1_id}/similarity/{p2_id}")
    assert resp.status_code == 200
    comp_json = resp.json()
    assert comp_json["player_a_name"] == "Pedri"
    assert comp_json["player_b_name"] == "Gavi"
    assert "profile_comparison" in comp_json
    assert "distribution" in comp_json["profile_comparison"]
    assert len(comp_json["why_different"]) > 0

    # 7. 404 handling
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/players/{fake_id}/role")
    assert resp.status_code == 404
