"""Mandatory temporal leakage and time-travel invariance tests for Tactical Fit Engine (Phase 2 Slice 3).
Verifies that tactical fit computed as-of T0 remains 100% bit-for-bit identical
after future matches, performances, or feature snapshots are added at T1 > T0.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
    PlayerTacticalFit,
    Season,
)
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


@pytest.mark.asyncio
async def test_tactical_fit_temporal_leakage_invariance(db_session):
    """THE DEFINITIVE TACTICAL FIT TEMPORAL LEAKAGE TEST:
    1. Establish Player with historical FeatureSnapshot at T0.
    2. Compute and persist Tactical Fit as of T0.
    3. Record exact metrics: fit_score, dimension_fit, role_fit, confidence, breakdowns, explanations.
    4. Inject future FeatureSnapshot at T1 > T0 with dramatically divergent performance.
    5. Recompute Tactical Fit as of T0.
    6. Assert 100% bit-for-bit identity with original T0 results.
    7. Compute Tactical Fit as of T1 and assert that T1 reflects new performance.
    """
    service = TacticalFitService(db_session)

    # 1. Base entities
    comp = Competition(name="Premier League", country="England")
    season = Season(name="2025/2026", start_year=2025, end_year=2026)
    db_session.add_all([comp, season])
    await db_session.flush()

    comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
    club = Club(name="Manchester City", code="MCI", country="England")
    player = Player(name="Rodri", primary_position="DM", nationality="Spain")
    db_session.add_all([comp_season, club, player])
    await db_session.flush()

    t0 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    # T0 Snapshot: Elite deep distributor numbers (450 minutes)
    snap_t0 = FeatureSnapshot(
        entity_type="player",
        entity_id=player.id,
        feature_set="player_match_v1",
        as_of=t0,
        features={
            "minutes_last_5": 450,
            "appearances_last_5": 5,
            "passes_per_90_last_5": 85.0,
            "pass_accuracy_avg_last_5": 92.5,
            "passes_key_per_90_last_5": 2.2,
            "tackles_per_90_last_5": 2.4,
            "interceptions_per_90_last_5": 1.6,
        },
    )
    db_session.add(snap_t0)
    await db_session.commit()

    context = get_standard_context("433_dm_deep_distributor")
    assert context is not None

    # 2. Compute tactical fit at T0
    fit_t0_initial = await service.calculate_and_save_tactical_fit(
        player_id=player.id,
        context=context,
        as_of=t0,
    )
    await db_session.commit()

    score_t0 = fit_t0_initial.fit_score
    pos_fit_t0 = fit_t0_initial.position_fit
    role_fit_t0 = fit_t0_initial.role_fit
    dim_fit_t0 = fit_t0_initial.dimension_fit
    style_fit_t0 = fit_t0_initial.style_fit
    conf_t0 = fit_t0_initial.confidence
    status_t0 = fit_t0_initial.fit_status
    breakdown_t0 = dict(fit_t0_initial.dimension_breakdown)
    why_fit_t0 = list(fit_t0_initial.why_fit)
    why_not_fit_t0 = list(fit_t0_initial.why_not_fit)

    assert score_t0 > 0.70
    assert conf_t0 in {"HIGH", "MEDIUM"}
    assert status_t0 == "FIT"

    # 3. Inject future snapshot at T1 > T0 with completely collapsed performance (e.g. red cards, 0 passes)
    snap_t1 = FeatureSnapshot(
        entity_type="player",
        entity_id=player.id,
        feature_set="player_match_v1",
        as_of=t1,
        features={
            "minutes_last_5": 450,
            "appearances_last_5": 5,
            "passes_per_90_last_5": 10.0,
            "pass_accuracy_avg_last_5": 50.0,
            "passes_key_per_90_last_5": 0.0,
            "tackles_per_90_last_5": 0.2,
            "red_cards_last_5": 3,
            "fouls_committed_per_90_last_5": 5.0,
        },
    )
    db_session.add(snap_t1)
    await db_session.commit()

    # 4. Recompute tactical fit as of T0: MUST BE INVARIANT TO T1 FUTURE DATA
    fit_t0_recalc = await service.calculate_and_save_tactical_fit(
        player_id=player.id,
        context=context,
        as_of=t0,
    )
    await db_session.commit()

    assert fit_t0_recalc.fit_score == pytest.approx(score_t0, abs=1e-5)
    assert fit_t0_recalc.position_fit == pytest.approx(pos_fit_t0, abs=1e-5)
    assert fit_t0_recalc.role_fit == pytest.approx(role_fit_t0, abs=1e-5)
    assert fit_t0_recalc.dimension_fit == pytest.approx(dim_fit_t0, abs=1e-5)
    assert fit_t0_recalc.style_fit == pytest.approx(style_fit_t0, abs=1e-5)
    assert fit_t0_recalc.confidence == conf_t0
    assert fit_t0_recalc.fit_status == status_t0
    assert fit_t0_recalc.dimension_breakdown == breakdown_t0
    assert fit_t0_recalc.why_fit == why_fit_t0
    assert fit_t0_recalc.why_not_fit == why_not_fit_t0

    # 5. Compute tactical fit as of T1: MUST reflect new future data and be distinct from T0
    fit_t1 = await service.calculate_and_save_tactical_fit(
        player_id=player.id,
        context=context,
        as_of=t1,
    )
    await db_session.commit()

    assert fit_t1.as_of == t1
    assert fit_t1.dimension_fit < dim_fit_t0  # Collapsed passing heavily penalizes Deep Distributor
    assert fit_t1.fit_score < score_t0

    # Verify both distinct point-in-time rows are persisted in PostgreSQL
    all_fits = (
        await db_session.execute(
            select(PlayerTacticalFit)
            .where(PlayerTacticalFit.player_id == player.id)
            .order_by(PlayerTacticalFit.as_of.asc())
        )
    ).scalars().all()

    assert len(all_fits) == 2
    assert all_fits[0].as_of == t0
    assert all_fits[1].as_of == t1
