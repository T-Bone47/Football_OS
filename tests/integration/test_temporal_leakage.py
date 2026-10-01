"""Mandatory temporal data leakage tests (Phase 2 Slice 1).
Verifies that feature computation for Match T is strictly invariant to future
matches and future performance.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
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
async def test_definitive_temporal_leakage_invariance(db_session):
    """THE DEFINITIVE TEMPORAL LEAKAGE TEST:
    Calculate Match 5 features.
    Insert Match 6 with massive performance values.
    Recalculate Match 5 features.
    Assert Match 5 feature values remain 100% BIT-FOR-BIT IDENTICAL.
    """
    service = FeatureService(db_session)

    # 1. Base entities
    comp = Competition(name="Premier League", country="England", type="LEAGUE")
    season = Season(name="2025/2026", start_year=2025, end_year=2026)
    db_session.add_all([comp, season])
    await db_session.flush()

    comp_season = CompetitionSeason(competition_id=comp.id, season_id=season.id)
    club_a = Club(name="Arsenal FC", code="ARS", country="England")
    club_b = Club(name="Chelsea FC", code="CHE", country="England")
    player = Player(name="Bukayo Saka", primary_position="F", nationality="England")
    db_session.add_all([comp_season, club_a, club_b, player])
    await db_session.flush()

    # 2. Sequential Matches 1 to 4 (Historical matches strictly before Match 5)
    match_dates = [
        datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 5, 15, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 10, 15, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 1, 15, 15, 0, 0, tzinfo=timezone.utc),
    ]

    # Historical performances
    # Match 1: Team wins 1-0, Saka: 90 mins, 1 goal, 2 shots
    # Match 2: Team draws 0-0, Saka: 90 mins, 0 goals, 1 shot
    # Match 3: Team wins 2-1, Saka: 90 mins, 2 goals, 3 shots
    # Match 4: Team loses 0-1, Saka: 45 mins, 0 goals, 0 shots
    player_hist_data = [
        (90, 1, 2),
        (90, 0, 1),
        (90, 2, 3),
        (45, 0, 0),
    ]
    team_hist_data = [
        ("WIN", 1, 0),
        ("DRAW", 0, 0),
        ("WIN", 2, 1),
        ("LOSS", 0, 1),
    ]

    for i in range(4):
        m = Match(
            competition_season_id=comp_season.id,
            date=match_dates[i],
            status="FINISHED",
            home_club_id=club_a.id,
            away_club_id=club_b.id,
        )
        db_session.add(m)
        await db_session.flush()

        res, gf, ga = team_hist_data[i]
        mt = MatchTeam(
            match_id=m.id,
            club_id=club_a.id,
            opponent_club_id=club_b.id,
            is_home=True,
            result=res,
            goals_for=gf,
            goals_against=ga,
        )
        mins, goals, shots = player_hist_data[i]
        pms = PlayerMatchStats(
            provider="test-fixture",
            match_id=m.id,
            club_id=club_a.id,
            player_id=player.id,
            position="F",
            minutes=mins,
            goals=goals,
            shots_total=shots,
            is_starter=(mins == 90),
        )
        db_session.add_all([mt, pms])
        await db_session.flush()

    # Target Match 5
    match_5_date = datetime(2026, 1, 20, 15, 0, 0, tzinfo=timezone.utc)
    match_5 = Match(
        competition_season_id=comp_season.id,
        date=match_5_date,
        status="SCHEDULED",
        home_club_id=club_a.id,
        away_club_id=club_b.id,
    )
    db_session.add(match_5)
    await db_session.flush()

    # 3. Compute baseline features for Match 5 as of Match 5 kickoff
    p_snap_before = await service.compute_player_features(
        player_id=player.id,
        as_of=match_5_date,
        match_id=match_5.id,
        save=True,
    )
    t_snap_before = await service.compute_team_features(
        club_id=club_a.id,
        as_of=match_5_date,
        match_id=match_5.id,
        save=True,
    )

    p_features_before = dict(p_snap_before.features)
    t_features_before = dict(t_snap_before.features)

    # Sanity checks on baseline
    assert p_features_before["appearances_last_5"] == 4
    assert p_features_before["minutes_last_5"] == 315
    assert p_features_before["goals_last_5"] == 3
    assert p_features_before["shots_total_last_5"] == 6
    assert p_features_before["goals_per_90_last_5"] == round((3 / 315) * 90.0, 4)

    assert t_features_before["matches_played_last_5"] == 4
    assert t_features_before["wins_last_5"] == 2
    assert t_features_before["draws_last_5"] == 1
    assert t_features_before["losses_last_5"] == 1
    assert t_features_before["points_last_5"] == 7
    assert t_features_before["goals_scored_last_5"] == 3
    assert t_features_before["goals_conceded_last_5"] == 2

    # 4. Now insert Match 6 with massive future performance (day 25)
    match_6_date = datetime(2026, 1, 25, 15, 0, 0, tzinfo=timezone.utc)
    match_6 = Match(
        competition_season_id=comp_season.id,
        date=match_6_date,
        status="FINISHED",
        home_club_id=club_a.id,
        away_club_id=club_b.id,
    )
    db_session.add(match_6)
    await db_session.flush()

    # Massive numbers in Match 6: 10 goals, 15 shots!
    mt_6 = MatchTeam(
        match_id=match_6.id,
        club_id=club_a.id,
        opponent_club_id=club_b.id,
        is_home=True,
        result="WIN",
        goals_for=10,
        goals_against=0,
    )
    pms_6 = PlayerMatchStats(
        provider="test-fixture",
        match_id=match_6.id,
        club_id=club_a.id,
        player_id=player.id,
        position="F",
        minutes=90,
        goals=10,
        shots_total=15,
        rating=10.0,
        is_starter=True,
    )
    db_session.add_all([mt_6, pms_6])
    await db_session.flush()

    # 5. Recalculate features for Match 5 with exact same as_of
    p_snap_after = await service.compute_player_features(
        player_id=player.id,
        as_of=match_5_date,
        match_id=match_5.id,
        save=True,
    )
    t_snap_after = await service.compute_team_features(
        club_id=club_a.id,
        as_of=match_5_date,
        match_id=match_5.id,
        save=True,
    )

    # 6. DEFINITIVE ASSERTIONS: Match 5 feature values are 100% IDENTICAL
    assert p_snap_after.features == p_features_before, (
        "TEMPORAL LEAKAGE DETECTED! Player Match 5 features changed after Match 6 was inserted!"
    )
    assert t_snap_after.features == t_features_before, (
        "TEMPORAL LEAKAGE DETECTED! Team Match 5 features changed after Match 6 was inserted!"
    )

    assert p_snap_after.features["goals_last_5"] == 3
    assert p_snap_after.features["shots_total_last_5"] == 6
    assert t_snap_after.features["goals_scored_last_5"] == 3
    assert t_snap_after.features["points_last_5"] == 7

    # 7. When we compute Match 6 features (as_of = Match 6 date), future matches ARE visible up to Match 6
    p_snap_6 = await service.compute_player_features(
        player_id=player.id,
        as_of=match_6_date,
        match_id=match_6.id,
        save=True,
    )
    # Match 6 does not include Match 6 itself (pre-match cutoff is strictly < as_of)
    assert p_snap_6.features["goals_last_5"] == 3
    assert p_snap_6.features["minutes_last_5"] == 315
