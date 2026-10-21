"""Field-level provenance: which provider supplied which canonical value.

The record-level provenance (`data_snapshots`) says where a *payload* came from. The
field level answers the question a scout actually asks: "where did this minute value
come from, and does another provider disagree?".
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select

from app.db.models.canonical import (
    Competition,
    CompetitionSeason,
    Player,
    PlayerIdentity,
    Season,
)
from app.db.models.expansion import FieldProvenance, SourceConflict
from app.normalization.schemas import NormalizedPlayer, NormalizedPlayerStats
from app.normalization.service import NormalizationService


def _player(provider_id: str, name: str = "M. Akanji", **overrides) -> NormalizedPlayer:
    payload = {
        "provider_id": provider_id,
        "name": name,
        "first_name": "Manuel",
        "last_name": "Akanji",
        "date_of_birth": "1996-07-27",
        "nationality": "Switzerland",
        "height_cm": 188,
        "weight_kg": 90,
        "primary_position": "Defender",
        "photo_url": "https://example.invalid/p.png",
    }
    payload.update(overrides)
    return NormalizedPlayer(**payload)


@pytest.mark.asyncio
async def test_player_fields_record_field_level_provenance(integration_session):
    service = NormalizationService(integration_session)
    await service.upsert_player_with_status("api-football", _player("5"))
    await integration_session.commit()

    rows = (
        await integration_session.execute(select(FieldProvenance))
    ).scalars().all()
    assert rows, "the normaliser must record which provider supplied each field"
    fields = {row.field_name: row for row in rows}
    assert fields["name"].provider == "api-football"
    assert fields["name"].source_value == {"value": "M. Akanji", "transformation": "PROVIDER_NAME"}
    assert fields["nationality"].source_value["value"] == "Switzerland"
    assert fields["date_of_birth"].transformation == "ISO_DATE"


@pytest.mark.asyncio
async def test_a_second_provider_disagreement_is_recorded_not_overwritten(integration_session):
    service = NormalizationService(integration_session)
    player, _created = await service.upsert_player_with_status(
        "api-football", _player("5", nationality="Switzerland")
    )
    await integration_session.commit()

    # A second provider maps to the SAME canonical player and reports a different
    # nationality: the disagreement must be recorded, not silently applied.
    integration_session.add(
        PlayerIdentity(
            player_id=player.id,
            provider="statsbomb",
            provider_player_id="sb-5",
            confidence=0.9,
            resolution_method="VERIFIED_ALIAS",
        )
    )
    await integration_session.commit()

    await service.upsert_player_with_status(
        "statsbomb", _player("sb-5", name="Manuel Akanji", nationality="France")
    )
    await integration_session.commit()

    conflicts = (
        await integration_session.execute(
            select(SourceConflict).where(SourceConflict.field_name == "nationality")
        )
    ).scalars().all()
    assert conflicts, "a provider disagreement must be recorded"
    conflict = conflicts[0]
    assert conflict.field_name == "nationality"
    assert conflict.status == "OPEN"
    assert conflict.candidates["canonical"] == "Switzerland"
    assert conflict.candidates["statsbomb"] == "France"

    # The canonical value is not silently replaced.
    await integration_session.refresh(player)
    assert player.nationality == "Switzerland"


@pytest.mark.asyncio
async def test_season_statistics_record_their_provenance(integration_session):
    service = NormalizationService(integration_session)
    player, _created = await service.upsert_player_with_status("api-football", _player("5"))
    await integration_session.commit()

    competition = Competition(name="Premier League", country="England", type="LEAGUE")
    season = Season(name="2023", start_year=2023, end_year=2024)
    integration_session.add_all([competition, season])
    await integration_session.flush()
    competition_season = CompetitionSeason(competition_id=competition.id, season_id=season.id)
    integration_session.add(competition_season)
    await integration_session.flush()

    stat = NormalizedPlayerStats(
        provider_player_id="5",
        provider_club_id="50",
        provider_league_id="39",
        season_year=2023,
        appearances=20,
        lineups=20,
        minutes=1800,
        goals=2,
        assists=1,
        conceded=3,
        raw_stats={"games": {"minutes": 1800}},
    )
    await service.upsert_player_season_stats(
        "api-football", stat, player.id, competition_season.id
    )
    await integration_session.commit()

    rows = (
        await integration_session.execute(
            select(FieldProvenance).where(FieldProvenance.entity_type == "player_season_stat")
        )
    ).scalars().all()
    metrics = {row.field_name: row for row in rows}
    assert metrics["minutes"].source_value["value"] == 1800
    assert metrics["goals"].source_value["value"] == 2
