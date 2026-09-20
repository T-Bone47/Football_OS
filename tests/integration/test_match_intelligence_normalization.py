import json
import uuid
from pathlib import Path
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.canonical import (
    Club,
    Match,
    MatchEvent,
    MatchLineup,
    MatchStatistics,
    Player,
    PlayerIdentity,
)
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun, IngestionStatus
from app.normalization.service import NormalizationService


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
async def test_match_intelligence_normalization_and_idempotency(db_session):
    service = NormalizationService(db_session)

    # 1. Seed Match fixture 1492387
    fixture_payload = {
        "response": [
            {
                "fixture": {
                    "id": 1492387,
                    "date": "2026-09-20T00:00:00+00:00",
                    "status": {"short": "FT", "long": "Match Finished"},
                    "venue": {"name": "Morumbi", "city": "Sao Paulo"},
                },
                "league": {
                    "id": 71,
                    "name": "Serie A",
                    "country": "Brazil",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": 126, "name": "Sao Paulo", "winner": True},
                    "away": {"id": 119, "name": "Internacional", "winner": False},
                },
                "goals": {"home": 1, "away": 0},
                "score": {
                    "halftime": {"home": 1, "away": 0},
                    "fulltime": {"home": 1, "away": 0},
                },
            }
        ]
    }
    matches = await service.normalize_fixtures_payload("api-football", fixture_payload)
    assert len(matches) == 1
    match = matches[0]

    # Create dummy DataSnapshots for provenance
    ds_source = DataSource(name="api-football")
    db_session.add(ds_source)
    await db_session.flush()

    run_ev = IngestionRun(data_source_id=ds_source.id, endpoint="fixtures/events", status=IngestionStatus.SUCCESS)
    run_lu = IngestionRun(data_source_id=ds_source.id, endpoint="fixtures/lineups", status=IngestionStatus.SUCCESS)
    run_st = IngestionRun(data_source_id=ds_source.id, endpoint="fixtures/statistics", status=IngestionStatus.SUCCESS)
    db_session.add_all([run_ev, run_lu, run_st])
    await db_session.flush()

    snap_ev = DataSnapshot(
        ingestion_run_id=run_ev.id, sha256="dummy_ev_sha", storage_location="dummy_ev", size_bytes=100
    )
    snap_lu = DataSnapshot(
        ingestion_run_id=run_lu.id, sha256="dummy_lu_sha", storage_location="dummy_lu", size_bytes=100
    )
    snap_st = DataSnapshot(
        ingestion_run_id=run_st.id, sha256="dummy_st_sha", storage_location="dummy_st", size_bytes=100
    )
    db_session.add_all([snap_ev, snap_lu, snap_st])
    await db_session.commit()

    # 2. Normalize Events
    events_payload = {
        "parameters": {"fixture": "1492387"},
        "response": [
            {
                "time": {"elapsed": 15, "extra": None},
                "team": {"id": 126, "name": "Sao Paulo"},
                "player": {"id": 47368, "name": "Jonathan Calleri"},
                "assist": {"id": None, "name": None},
                "type": "Goal",
                "detail": "Penalty",
                "comments": None,
            },
            {
                "time": {"elapsed": 90, "extra": 3},
                "team": {"id": 119, "name": "Internacional"},
                "player": {"id": 2044, "name": "Gabriel Mercado"},
                "assist": {"id": None, "name": None},
                "type": "Card",
                "detail": "Yellow Card",
                "comments": "Dissent",
            },
            {
                "time": {"elapsed": 73, "extra": None},
                "team": {"id": 126, "name": "Sao Paulo"},
                "player": {"id": 47368, "name": "Jonathan Calleri"},
                "assist": {"id": 106510, "name": "Aldemir Ferreira"},
                "type": "subst",
                "detail": "Substitution 3",
                "comments": None,
            },
        ],
    }
    events = await service.normalize_events_payload(
        "api-football", events_payload, snapshot_id=snap_ev.id
    )
    assert len(events) == 3

    # 3. Normalize Lineups
    lineups_payload = {
        "parameters": {"fixture": "1492387"},
        "response": [
            {
                "team": {"id": 126, "name": "Sao Paulo"},
                "formation": "3-4-2-1",
                "coach": {"id": 3059, "name": "Dorival Júnior"},
                "startXI": [
                    {"player": {"id": 10081, "name": "Rafael", "number": 23, "pos": "G", "grid": "1:1"}},
                ],
                "substitutes": [
                    {"player": {"id": 41188, "name": "André Silva", "number": 17, "pos": "F", "grid": None}},
                ],
            },
            {
                "team": {"id": 119, "name": "Internacional"},
                "formation": "3-4-2-1",
                "coach": {"id": 1000, "name": "P. Pezzolano"},
                "startXI": [
                    {"player": {"id": 306552, "name": "Anthoni", "number": 12, "pos": "G", "grid": "1:1"}},
                ],
                "substitutes": [
                    {"player": {"id": 63964, "name": "F. Torres", "number": 4, "pos": "D", "grid": None}},
                ],
            },
        ],
    }
    lineups = await service.normalize_lineups_payload(
        "api-football", lineups_payload, snapshot_id=snap_lu.id
    )
    assert len(lineups) == 4

    # 4. Normalize Statistics
    stats_payload = {
        "parameters": {"fixture": "1492387"},
        "response": [
            {
                "team": {"id": 126, "name": "Sao Paulo"},
                "statistics": [
                    {"type": "Ball Possession", "value": "44%"},
                    {"type": "Total Shots", "value": 6},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Red Cards", "value": 0},  # Explicit 0
                    {"type": "Yellow Cards", "value": 1},
                    {"type": "Fouls", "value": 15},
                    {"type": "Corner Kicks", "value": 3},
                    {"type": "Total passes", "value": 400},
                    {"type": "Passes accurate", "value": 320},
                    {"type": "Passes %", "value": "80%"},
                ],
            },
            {
                "team": {"id": 119, "name": "Internacional"},
                "statistics": [
                    {"type": "Ball Possession", "value": "56%"},
                    {"type": "Total Shots", "value": 13},
                    {"type": "Shots on Goal", "value": 1},
                    {"type": "Red Cards", "value": 0},
                    {"type": "Yellow Cards", "value": 3},
                    {"type": "Fouls", "value": 13},
                    {"type": "Corner Kicks", "value": 3},
                    {"type": "Total passes", "value": 494},
                    {"type": "Passes accurate", "value": 424},
                    {"type": "Passes %", "value": "86%"},
                ],
            },
        ],
    }
    stats = await service.normalize_statistics_payload(
        "api-football", stats_payload, snapshot_id=snap_st.id
    )
    assert len(stats) == 2

    # Verify Provenance
    for ev in events:
        assert ev.snapshot_id == snap_ev.id
    for lu in lineups:
        assert lu.snapshot_id == snap_lu.id
    for st in stats:
        assert st.snapshot_id == snap_st.id

    # Verify explicit 0 vs None
    sp_stat = next(s for s in stats if s.possession_pct == 44.0)
    assert sp_stat.red_cards == 0
    assert sp_stat.expected_goals is None  # Never replace missing with 0!
    assert sp_stat.fouls == 15

    # Record BEFORE counts and primary keys
    ev_count_before = (await db_session.execute(select(func.count(MatchEvent.id)))).scalar_one()
    lu_count_before = (await db_session.execute(select(func.count(MatchLineup.id)))).scalar_one()
    st_count_before = (await db_session.execute(select(func.count(MatchStatistics.id)))).scalar_one()
    assert ev_count_before == 3
    assert lu_count_before == 4
    assert st_count_before == 2

    ev_ids_before = sorted([str(e.id) for e in events])
    lu_ids_before = sorted([str(l.id) for l in lineups])
    st_ids_before = sorted([str(s.id) for s in stats])

    # === STRICT IDEMPOTENCY PROOF ===
    # Re-normalize exact same payloads
    events_repeat = await service.normalize_events_payload(
        "api-football", events_payload, snapshot_id=snap_ev.id
    )
    lineups_repeat = await service.normalize_lineups_payload(
        "api-football", lineups_payload, snapshot_id=snap_lu.id
    )
    stats_repeat = await service.normalize_statistics_payload(
        "api-football", stats_payload, snapshot_id=snap_st.id
    )

    ev_count_after = (await db_session.execute(select(func.count(MatchEvent.id)))).scalar_one()
    lu_count_after = (await db_session.execute(select(func.count(MatchLineup.id)))).scalar_one()
    st_count_after = (await db_session.execute(select(func.count(MatchStatistics.id)))).scalar_one()

    # Exact zero duplicates
    assert ev_count_after == ev_count_before == 3
    assert lu_count_after == lu_count_before == 4
    assert st_count_after == st_count_before == 2

    # Primary keys remain identical
    ev_ids_after = sorted([str(e.id) for e in events_repeat])
    lu_ids_after = sorted([str(l.id) for l in lineups_repeat])
    st_ids_after = sorted([str(s.id) for s in stats_repeat])

    assert ev_ids_after == ev_ids_before
    assert lu_ids_after == lu_ids_before
    assert st_ids_after == st_ids_before

    # Verify Player identities created and linked
    calleri_ident = (
        await db_session.execute(
            select(PlayerIdentity).where(
                PlayerIdentity.provider == "api-football",
                PlayerIdentity.provider_player_id == "47368",
            )
        )
    ).scalar_one_or_none()
    assert calleri_ident is not None
    assert calleri_ident.resolution_method == "DIRECT_PROVIDER_ID"

    calleri_player = (
        await db_session.execute(select(Player).where(Player.id == calleri_ident.player_id))
    ).scalar_one_or_none()
    assert calleri_player is not None
    assert calleri_player.name == "Jonathan Calleri"
