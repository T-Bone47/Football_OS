"""Integration tests for FeatureSnapshot persistence, idempotency, and dataset builder (Phase 2 Slice 1)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.canonical import (
    Club,
    Competition,
    CompetitionSeason,
    FeatureSnapshot,
    Match,
    MatchTeam,
    Player,
    PlayerMatchStats,
    Season,
)
from app.features.service import FeatureService


@pytest_asyncio.fixture
async def db_session(postgres_url):
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
async def test_feature_snapshot_persistence_and_idempotency(db_session):
    service = FeatureService(db_session)

    # 1. Setup entities
    comp = Competition(type="LEAGUE", name="La Liga", country="Spain")
    season = Season(name="2025/2026", start_year=2025, end_year=2026)
    db_session.add_all([comp, season])
    await db_session.flush()

    comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
    club_a = Club(name="Real Madrid", code="RMA", country="Spain")
    club_b = Club(name="Barcelona", code="FCB", country="Spain")
    player = Player(name="Vinicius Junior", primary_position="F", nationality="Brazil")
    db_session.add_all([comp_season, club_a, club_b, player])
    await db_session.flush()

    m1_date = datetime(2026, 2, 1, 15, 0, 0, tzinfo=timezone.utc)
    m1 = Match(provider="test-fixture", 
        competition_season_id=comp_season.id,
        date=m1_date,
        status="FINISHED",
        home_club_id=club_a.id,
        away_club_id=club_b.id,
    )
    db_session.add(m1)
    await db_session.flush()

    mt1 = MatchTeam(
        match_id=m1.id,
        club_id=club_a.id,
        opponent_club_id=club_b.id,
        is_home=True,
        result="WIN",
        goals_for=3,
        goals_against=1,
    )
    mt2 = MatchTeam(
        match_id=m1.id,
        club_id=club_b.id,
        opponent_club_id=club_a.id,
        is_home=False,
        result="LOSS",
        goals_for=1,
        goals_against=3,
    )
    pms1 = PlayerMatchStats(
        provider="test-fixture",
        match_id=m1.id,
        club_id=club_a.id,
        player_id=player.id,
        position="F",
        minutes=90,
        goals=2,
        assists=1,
        shots_total=4,
        is_starter=True,
    )
    db_session.add_all([mt1, mt2, pms1])
    await db_session.flush()

    # Target Match 2
    m2_date = datetime(2026, 2, 8, 15, 0, 0, tzinfo=timezone.utc)
    m2 = Match(provider="test-fixture", 
        competition_season_id=comp_season.id,
        date=m2_date,
        status="SCHEDULED",
        home_club_id=club_a.id,
        away_club_id=club_b.id,
    )
    db_session.add(m2)
    await db_session.flush()

    # 2. First computation & persistence
    snap1 = await service.compute_player_features(
        player_id=player.id,
        as_of=m2_date,
        match_id=m2.id,
        save=True,
    )
    await db_session.commit()

    snap_id = snap1.id
    assert snap1.features["goals_last_5"] == 2
    assert snap1.features["assists_last_5"] == 1
    assert snap1.features["goals_per_90_last_5"] == 2.0
    assert snap1.provenance["record_count"] == 1

    # Check database count
    count1 = (await db_session.execute(select(func.count(FeatureSnapshot.id)))).scalar_one()
    assert count1 == 1

    # 3. Idempotency test: Repeat computation with exact same inputs
    snap2 = await service.compute_player_features(
        player_id=player.id,
        as_of=m2_date,
        match_id=m2.id,
        save=True,
    )
    await db_session.commit()

    # Must retain exact same primary key and 0 duplicate rows
    assert snap2.id == snap_id
    count2 = (await db_session.execute(select(func.count(FeatureSnapshot.id)))).scalar_one()
    assert count2 == 1


@pytest.mark.asyncio
async def test_compute_match_features_and_rest_days(db_session):
    service = FeatureService(db_session)

    comp = Competition(type="LEAGUE", name="Serie A", country="Italy")
    season = Season(name="2025/2026", start_year=2025, end_year=2026)
    db_session.add_all([comp, season])
    await db_session.flush()

    comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
    club_h = Club(name="Juventus", code="JUV", country="Italy")
    club_a = Club(name="AC Milan", code="MIL", country="Italy")
    db_session.add_all([comp_season, club_h, club_a])
    await db_session.flush()

    # Previous match for Juventus 4 days earlier
    m_prev_h = Match(provider="test-fixture", 
        competition_season_id=comp_season.id,
        date=datetime(2026, 2, 11, 15, 0, 0, tzinfo=timezone.utc),
        status="FINISHED",
        home_club_id=club_h.id,
        away_club_id=club_a.id,
    )
    db_session.add(m_prev_h)
    await db_session.flush()

    mt_prev_h = MatchTeam(
        match_id=m_prev_h.id,
        club_id=club_h.id,
        opponent_club_id=club_a.id,
        is_home=True,
        result="WIN",
        goals_for=2,
        goals_against=0,
    )
    mt_prev_a = MatchTeam(
        match_id=m_prev_h.id,
        club_id=club_a.id,
        opponent_club_id=club_h.id,
        is_home=False,
        result="LOSS",
        goals_for=0,
        goals_against=2,
    )
    db_session.add_all([mt_prev_h, mt_prev_a])
    await db_session.flush()

    # Target Match on Feb 15
    m_target = Match(provider="test-fixture", 
        competition_season_id=comp_season.id,
        date=datetime(2026, 2, 15, 15, 0, 0, tzinfo=timezone.utc),
        status="SCHEDULED",
        home_club_id=club_h.id,
        away_club_id=club_a.id,
    )
    db_session.add(m_target)
    await db_session.flush()

    # Target match needs MatchTeam entries so teams relationship is present
    mt_target_h = MatchTeam(
        match_id=m_target.id,
        club_id=club_h.id,
        opponent_club_id=club_a.id,
        is_home=True,
        result=None,
    )
    mt_target_a = MatchTeam(
        match_id=m_target.id,
        club_id=club_a.id,
        opponent_club_id=club_h.id,
        is_home=False,
        result=None,
    )
    db_session.add_all([mt_target_h, mt_target_a])
    await db_session.flush()

    res = await service.compute_match_features(match_id=m_target.id, save=True)
    await db_session.commit()

    assert res["match_id"] == m_target.id
    assert res["home_club_id"] == club_h.id
    assert res["away_club_id"] == club_a.id

    # Rest days: Feb 15 - Feb 11 = 4.0 days
    assert res["match_context"]["home_days_since_previous_match"] == 4.0
    assert res["match_context"]["away_days_since_previous_match"] == 4.0


@pytest.mark.asyncio
async def test_build_model_ready_dataset(db_session):
    service = FeatureService(db_session)

    comp = Competition(type="LEAGUE", name="Bundesliga", country="Germany")
    season = Season(name="2025/2026", start_year=2025, end_year=2026)
    db_session.add_all([comp, season])
    await db_session.flush()

    comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
    club = Club(name="Bayern Munich", code="BAY", country="Germany")
    db_session.add_all([comp_season, club])
    await db_session.flush()

    # Create 2 snapshots
    snap1 = FeatureSnapshot(
        entity_type="team",
        entity_id=club.id,
        feature_set="team_match_v1",
        calculation_version="1.0.0",
        as_of=datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        features={"points_last_5": 12, "goals_scored_last_5": 10},
        provenance={"record_count": 5},
    )
    snap2 = FeatureSnapshot(
        entity_type="team",
        entity_id=club.id,
        feature_set="team_match_v1",
        calculation_version="1.0.0",
        as_of=datetime(2026, 3, 8, 12, 0, 0, tzinfo=timezone.utc),
        features={"points_last_5": 15, "goals_scored_last_5": 14},
        provenance={"record_count": 5},
    )
    db_session.add_all([snap1, snap2])
    await db_session.commit()

    rows = await service.build_model_ready_dataset(
        entity_type="team",
        feature_set="team_match_v1",
        start_date=datetime(2026, 2, 28, tzinfo=timezone.utc),
        end_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )

    assert len(rows) == 2
    assert rows[0]["points_last_5"] == 12
    assert rows[1]["points_last_5"] == 15
    assert rows[0]["entity_id"] == str(club.id)
