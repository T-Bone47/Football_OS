"""Integration tests for the paginated match list and batch role endpoint.

They seed deterministic canonical rows inside the shared transaction fixture
and assert true totals, disjoint pages, and honest role coverage counts.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from app.db.models.canonical import (
    Club,
    Competition,
    CompetitionSeason,
    Match,
    Player,
    PlayerRoleProfile,
    Season,
)
from app.main import app


@pytest_asyncio.fixture
async def seeded_matches(integration_session):
    competition = Competition(name="Paging Cup", country="Testland", type="LEAGUE")
    season = Season(name="2099/2100", start_year=2099, end_year=2100)
    integration_session.add_all([competition, season])
    await integration_session.flush()

    competition_season = CompetitionSeason(
        competition_id=competition.id, season_id=season.id, start_date=date(2099, 8, 1), end_date=date(2100, 5, 1)
    )
    home = Club(name="Paging Home", country="Testland")
    away = Club(name="Paging Away", country="Testland")
    integration_session.add_all([competition_season, home, away])
    await integration_session.flush()

    base = datetime(2099, 9, 1, 12, tzinfo=timezone.utc)
    for i in range(30):
        integration_session.add(
            Match(
                provider="test-fixture",
                provider_fixture_id=f"paging-match-{i:03d}",
                competition_season_id=competition_season.id,
                home_club_id=home.id,
                away_club_id=away.id,
                date=base + timedelta(days=i),
                status="FINISHED" if i % 2 == 0 else "SCHEDULED",
                home_score=2 if i % 2 == 0 else None,
                away_score=1 if i % 2 == 0 else None,
            )
        )
    await integration_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, competition_season.id


@pytest.mark.asyncio
async def test_match_search_reports_true_total_and_disjoint_pages(seeded_matches):
    client, competition_season_id = seeded_matches
    first = await client.get(
        "/api/v1/matches/search",
        params={"competition_season_id": str(competition_season_id), "page": 1, "page_size": 10},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["total"] == 30
    assert body["total_pages"] == 3
    assert body["has_next"] is True
    assert len(body["items"]) == 10
    assert body["items"][0]["competition_name"] == "Paging Cup"
    assert body["items"][0]["season_name"] == "2099/2100"

    last = await client.get(
        "/api/v1/matches/search",
        params={"competition_season_id": str(competition_season_id), "page": 3, "page_size": 10},
    )
    last_body = last.json()
    assert len(last_body["items"]) == 10
    assert last_body["has_next"] is False
    assert not (
        {m["id"] for m in body["items"]} & {m["id"] for m in last_body["items"]}
    )


@pytest.mark.asyncio
async def test_match_search_filters_apply_before_counting(seeded_matches):
    client, competition_season_id = seeded_matches
    res = await client.get(
        "/api/v1/matches/search",
        params={
            "competition_season_id": str(competition_season_id),
            "status": "finished",
            "page": 1,
            "page_size": 10,
        },
    )
    body = res.json()
    assert body["total"] == 15
    assert all(m["status"] == "FINISHED" for m in body["items"])
    assert all(m["home_score"] == 2 for m in body["items"])


@pytest_asyncio.fixture
async def seeded_roles(integration_session):
    players = []
    for i, position in enumerate(["Goalkeeper", "Defender", "Midfielder", "Attacker"]):
        player = Player(name=f"Role Fixture {i}", primary_position=position)
        integration_session.add(player)
        players.append(player)
    await integration_session.flush()

    integration_session.add_all(
        [
            PlayerRoleProfile(
                player_id=players[0].id,
                as_of=datetime(2099, 1, 1, tzinfo=timezone.utc),
                role_status="QUALIFIED",
                sample_minutes=2700,
                sample_matches=30,
                position_group="GK",
                primary_archetype="Sweeper Keeper",
                archetype_confidence=0.81,
                profile_scores={"distribution": 0.7},
                feature_vector={"passes_per_90": 1.0},
            ),
            PlayerRoleProfile(
                player_id=players[1].id,
                as_of=datetime(2099, 1, 1, tzinfo=timezone.utc),
                role_status="QUALIFIED",
                sample_minutes=2500,
                sample_matches=28,
                position_group="DEF",
                primary_archetype="Defensive Fullback",
                archetype_confidence=0.74,
                profile_scores={"defending": 0.8},
                feature_vector={"tackles_per_90": 1.2},
            ),
            PlayerRoleProfile(
                player_id=players[2].id,
                as_of=datetime(2099, 1, 1, tzinfo=timezone.utc),
                role_status="INSUFFICIENT_SAMPLE",
                sample_minutes=90,
                sample_matches=1,
                position_group="MID",
                profile_scores={},
                feature_vector={},
            ),
        ]
    )
    await integration_session.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, players


@pytest.mark.asyncio
async def test_batch_roles_reports_classified_insufficient_and_missing(seeded_roles):
    client, players = seeded_roles
    ids = ",".join(str(p.id) for p in players)
    res = await client.get("/api/v1/players/roles", params={"ids": ids})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["requested"] == 4
    assert body["returned"] == 4
    assert body["classified"] == 2
    assert body["insufficient"] == 1
    assert body["not_classified"] == 1
    assert body["coverage"]["qualified_profiles"] >= 2
    assert body["coverage"]["total_players"] >= 4

    by_id = {item["player_id"]: item for item in body["items"]}
    assert by_id[str(players[0].id)]["primary_archetype"] == "Sweeper Keeper"
    assert by_id[str(players[2].id)]["role_status"] == "INSUFFICIENT_SAMPLE"
    assert by_id[str(players[3].id)]["role_status"] == "NOT_CLASSIFIED"


@pytest.mark.asyncio
async def test_batch_roles_rejects_invalid_identifier(seeded_roles):
    client, _ = seeded_roles
    res = await client.get("/api/v1/players/roles", params={"ids": "not-a-uuid"})
    assert res.status_code == 422
