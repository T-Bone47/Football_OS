"""Regression tests for the squad and market-context defects.

Root causes fixed here:

1. `SquadService.build_player_profile` read `PlayerRoleProfile.primary_role`,
   which does not exist (the column is `primary_archetype`). Every
   `GET /api/v1/squads/build` call raised AttributeError -> HTTP 500.

2. `build_player_market_context` passed the raw `dimension_scores` JSONB
   (`{"duels": {"score": None, ...}}`) into a `dict[str, float]` contract.
   The player profile endpoints (valuation-baseline, transfer-comparables,
   market-context) failed with a pydantic ValidationError (HTTP 400/500).

Both were reachable from the UI, not just from tests.

The tests use the shared transaction-rollback fixture, so they never truncate
or drop shared tables.
"""
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio

from app.db.models.canonical import (
    Player,
    PlayerContributionSnapshot,
    PlayerRoleProfile,
)
from app.market.dimension_scores import dimension_scores_by_dimension
from app.main import app
from app.normalization.schemas import NormalizedPlayer
from app.normalization.service import NormalizationService

PREFIX = "Squad Market Regression"


@pytest_asyncio.fixture
async def seeded_client(integration_session):
    service = NormalizationService(integration_session)
    player = await service.upsert_player(
        "api-football",
        NormalizedPlayer(
            provider_id="squad-market-001",
            name=f"{PREFIX} Player",
            primary_position="Defender",
            nationality="England",
        ),
    )

    now = datetime.now(timezone.utc)
    integration_session.add(
        PlayerRoleProfile(
            player_id=player.id,
            as_of=now,
            feature_set_version="role_feature_set_v1",
            role_status="QUALIFIED",
            sample_minutes=1200,
            sample_matches=14,
            position_group="DEF",
            primary_archetype="BALL_PLAYING_DEFENDER",
            archetype_confidence=0.72,
        )
    )
    # The persisted shape has one record per dimension, and the score can be
    # unknown (None). This is the shape that used to break the response model.
    integration_session.add(
        PlayerContributionSnapshot(
            player_id=player.id,
            as_of=now,
            feature_set_version="1.0",
            calculation_version="1.0",
            position_group="DEF",
            sample_minutes=1200,
            sample_matches=14,
            confidence="MEDIUM",
            contribution_status="PARTIAL",
            dimension_scores={
                "duels": {"score": None, "summary": None, "key_metrics": {}},
                "passing": {"score": 0.61, "summary": "solid", "key_metrics": {}},
            },
        )
    )
    await integration_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, player, integration_session


def test_dimension_score_helper_keeps_unknown_scores_as_none():
    scores = dimension_scores_by_dimension(
        {
            "duels": {"score": None, "summary": None, "key_metrics": {}},
            "passing": {"score": 0.61, "summary": "ok", "key_metrics": {}},
            "finishing": 0.4,
        }
    )
    assert scores["duels"] is None
    assert scores["passing"] == pytest.approx(0.61)
    assert scores["finishing"] == pytest.approx(0.4)


def test_dimension_score_helper_handles_empty_input():
    assert dimension_scores_by_dimension(None) == {}
    assert dimension_scores_by_dimension({}) == {}


@pytest.mark.asyncio
async def test_squad_build_no_longer_crashes_on_role_profile(seeded_client):
    """The squad analysis must read the role profile's real column name."""
    client, _player, _session = seeded_client
    res = await client.get("/api/v1/squads/build", params={"formation": "4-3-3"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["formation"] == "4-3-3"
    assert "positions" in body


@pytest.mark.asyncio
async def test_squad_player_profile_uses_primary_archetype(seeded_client):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.squad.service import SquadService

    _client, player, session = seeded_client
    loaded = (
        await session.execute(
            select(Player)
            .where(Player.id == player.id)
            .options(
                selectinload(Player.role_profiles),
                selectinload(Player.valuation_predictions),
                selectinload(Player.season_stats),
            )
        )
    ).scalar_one()
    profile = SquadService(session).build_player_profile(
        loaded, datetime.now(timezone.utc)
    )
    assert profile.primary_role == "BALL_PLAYING_DEFENDER"
    assert profile.role_confidence == pytest.approx(0.72)


@pytest.mark.asyncio
async def test_market_context_returns_200_with_unknown_scores(seeded_client):
    client, player, _session = seeded_client
    res = await client.get(f"/api/v1/players/{player.id}/market-context")
    assert res.status_code == 200, res.text
    body = res.json()
    # Unknown stays unknown: it must not be coerced to 0.0.
    assert body["contribution_scores"]["duels"] is None
    assert body["contribution_scores"]["passing"] == pytest.approx(0.61)


@pytest.mark.asyncio
async def test_valuation_baseline_and_comparables_return_200(seeded_client):
    client, player, _session = seeded_client
    for path in (
        f"/api/v1/players/{player.id}/valuation-baseline",
        f"/api/v1/players/{player.id}/transfer-comparables",
    ):
        res = await client.get(path)
        assert res.status_code == 200, f"{path} -> {res.status_code}: {res.text}"


def test_comparable_similarity_ignores_unknown_dimensions():
    from app.market.comparables import ComparableTransferEngine

    engine = ComparableTransferEngine()
    score, _parts = engine.calculate_similarity(
        target_age=24.0,
        candidate_age=25.0,
        target_role="BALL_PLAYING_DEFENDER",
        candidate_role="BALL_PLAYING_DEFENDER",
        target_contrib={"duels": None, "passing": 0.6},
        candidate_contrib={"duels": 0.5, "passing": 0.6},
        days_diff=10,
    )
    assert 0.0 <= score <= 1.0
