"""Integration tests for Tactical Fit Engine persistence, REST API, and sample-size gate (Phase 2 Slice 3)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.canonical import (
    Club,
    Competition,
    CompetitionSeason,
    FeatureSnapshot,
    Player,
    PlayerRoleProfile,
    PlayerTacticalFit,
    Season,
)
from app.db.session import get_session
from app.main import app
from app.tactical.contexts import get_standard_context
from app.tactical.service import TacticalFitService


@pytest_asyncio.fixture
async def db_session(postgres_url):
    """Provides isolated PostgreSQL test database with clean schema."""
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

    data = {}
    async with Session() as session:
        comp = Competition(name="La Liga", country="Spain")
        season = Season(name="2025/2026", start_year=2025, end_year=2026)
        session.add_all([comp, season])
        await session.flush()

        comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
        club = Club(name="Real Madrid", code="RMA", country="Spain")
        session.add_all([comp_season, club])
        await session.flush()

        # Player 1: Qualified Midfielder (Deep Distributor fit)
        p1 = Player(name="Toni Kroos", primary_position="DM", nationality="Germany")
        # Player 2: Qualified Attacking Midfielder (Chance Creator fit)
        p2 = Player(name="Jude Bellingham", primary_position="AM", nationality="England")
        # Player 3: Under-sampled Young Player (80 minutes)
        p3 = Player(name="Academy Talent", primary_position="DM", nationality="Spain")

        session.add_all([p1, p2, p3])
        await session.flush()

        eval_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

        # Snapshots
        snap1 = FeatureSnapshot(
            entity_type="player",
            entity_id=p1.id,
            feature_set="player_match_v1",
            as_of=eval_time,
            features={
                "minutes_last_5": 450,
                "appearances_last_5": 5,
                "passes_per_90_last_5": 82.0,
                "pass_accuracy_avg_last_5": 94.0,
                "passes_key_per_90_last_5": 2.5,
                "tackles_per_90_last_5": 1.8,
            },
        )
        snap2 = FeatureSnapshot(
            entity_type="player",
            entity_id=p2.id,
            feature_set="player_match_v1",
            as_of=eval_time,
            features={
                "minutes_last_5": 450,
                "appearances_last_5": 5,
                "passes_per_90_last_5": 45.0,
                "pass_accuracy_avg_last_5": 85.0,
                "goals_per_90_last_5": 0.60,
                "shots_per_90_last_5": 3.2,
                "passes_key_per_90_last_5": 2.1,
            },
        )
        snap3 = FeatureSnapshot(
            entity_type="player",
            entity_id=p3.id,
            feature_set="player_match_v1",
            as_of=eval_time,
            features={
                "minutes_last_5": 80,
                "appearances_last_5": 1,
                "passes_per_90_last_5": 40.0,
            },
        )
        session.add_all([snap1, snap2, snap3])
        await session.commit()

        data = {
            "p1_id": p1.id,
            "p2_id": p2.id,
            "p3_id": p3.id,
            "eval_time": eval_time,
        }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, data

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_tactical_fit_persistence_and_idempotency(db_session):
    """Tests saving PlayerTacticalFit to PostgreSQL and verifies strict idempotency."""
    service = TacticalFitService(db_session)

    player = Player(name="Joshua Kimmich", primary_position="DM", nationality="Germany")
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
            "passes_per_90_last_5": 78.0,
            "pass_accuracy_avg_last_5": 91.5,
            "passes_key_per_90_last_5": 2.2,
            "tackles_per_90_last_5": 2.1,
        },
    )
    db_session.add(snap)
    await db_session.flush()

    context = get_standard_context("433_dm_deep_distributor")
    assert context is not None

    # 1. First calculation
    fit_1 = await service.calculate_and_save_tactical_fit(player.id, context, as_of=eval_time)
    await db_session.commit()

    assert fit_1.fit_score > 0.70
    assert fit_1.confidence in {"HIGH", "MEDIUM"}
    assert fit_1.fit_status == "FIT"
    initial_id = fit_1.id

    # 2. Re-calculation with identical parameters: must update same row, not duplicate
    fit_2 = await service.calculate_and_save_tactical_fit(player.id, context, as_of=eval_time)
    await db_session.commit()

    assert fit_2.id == initial_id

    # Count rows in database
    count_stmt = select(PlayerTacticalFit).where(PlayerTacticalFit.player_id == player.id)
    records = (await db_session.execute(count_stmt)).scalars().all()
    assert len(records) == 1


@pytest.mark.asyncio
async def test_tactical_fit_sample_size_gate(db_session):
    """Verifies that players with under 450 minutes receive INSUFFICIENT_DATA status."""
    service = TacticalFitService(db_session)

    player = Player(name="Youth Sub", primary_position="DM", nationality="Spain")
    db_session.add(player)
    await db_session.flush()

    eval_time = datetime(2026, 3, 10, 15, 0, 0, tzinfo=timezone.utc)
    snap = FeatureSnapshot(
        entity_type="player",
        entity_id=player.id,
        feature_set="player_match_v1",
        as_of=eval_time,
        features={
            "minutes_last_5": 60,
            "appearances_last_5": 1,
            "passes_per_90_last_5": 50.0,
        },
    )
    db_session.add(snap)
    await db_session.flush()

    context = get_standard_context("433_dm_deep_distributor")
    fit = await service.calculate_and_save_tactical_fit(player.id, context, as_of=eval_time)
    await db_session.commit()

    assert fit.confidence == "INSUFFICIENT_DATA"
    assert fit.fit_status == "INSUFFICIENT_DATA"
    assert any("insufficient sample" in s.lower() for s in fit.why_not_fit)


@pytest.mark.asyncio
async def test_api_tactical_endpoints(api_client):
    """Tests all canonical tactical fit REST API endpoints."""
    client, data = api_client
    p1_id = data["p1_id"]
    p2_id = data["p2_id"]
    p3_id = data["p3_id"]

    # 1. GET /api/v1/tactical/contexts
    resp = await client.get("/api/v1/tactical/contexts")
    assert resp.status_code == 200
    contexts = resp.json()
    assert len(contexts) >= 10
    assert any(c["context_id"] == "433_dm_deep_distributor" for c in contexts)

    # 2. GET /api/v1/players/{id}/tactical-fit?context_id=433_dm_deep_distributor (Qualified)
    resp = await client.get(f"/api/v1/players/{p1_id}/tactical-fit?context_id=433_dm_deep_distributor")
    assert resp.status_code == 200
    fit_json = resp.json()
    assert fit_json["player_name"] == "Toni Kroos"
    assert fit_json["confidence"] in {"HIGH", "MEDIUM"}
    assert fit_json["fit_status"] == "FIT"
    assert "dimension_breakdown" in fit_json
    assert len(fit_json["why_fit"]) > 0

    # 3. GET /api/v1/players/{id}/tactical-fit/{context_id} (Under-sampled young player)
    resp = await client.get(f"/api/v1/players/{p3_id}/tactical-fit/433_dm_deep_distributor")
    assert resp.status_code == 200
    fit_p3 = resp.json()
    assert fit_p3["confidence"] == "INSUFFICIENT_DATA"
    assert fit_p3["fit_status"] == "INSUFFICIENT_DATA"

    # 4. POST /api/v1/tactical-fit/compare (Compare Toni Kroos vs Jude Bellingham for 433 DM Deep Distributor)
    comp_payload = {
        "player_a_id": str(p1_id),
        "player_b_id": str(p2_id),
        "context_id": "433_dm_deep_distributor",
    }
    resp = await client.post("/api/v1/tactical-fit/compare", json=comp_payload)
    assert resp.status_code == 200
    comp_json = resp.json()
    assert comp_json["context_id"] == "433_dm_deep_distributor"
    assert comp_json["player_a"]["player_name"] == "Toni Kroos"
    assert comp_json["player_b"]["player_name"] == "Jude Bellingham"
    assert "dimensional_deltas" in comp_json
    assert "comparison_summary" in comp_json

    # 5. 404 for unknown player
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/players/{fake_id}/tactical-fit?context_id=433_dm_deep_distributor")
    assert resp.status_code == 404

    # 6. 404 for unknown context
    resp = await client.get(f"/api/v1/players/{p1_id}/tactical-fit?context_id=nonexistent_context")
    assert resp.status_code == 404
