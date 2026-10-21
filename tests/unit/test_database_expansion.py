"""Unit tests for the database expansion layer.

Covers: name normalisation, conservative identity scoring, checkpoint scope keys,
the dated country-priority registry, the source licence policy, the scope planner
and the "unknown statistic is not zero" rule in the provider transformer.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.ingestion.checkpoints import BLOCKED, COMPLETE, PARTIAL, scope_key
from app.ingestion.country_priorities import load_snapshot
from app.ingestion.scope import load_priority_competitions
from app.ingestion.sources import SOURCE_POLICIES
from app.identity.names import name_key, names_are_close, normalize_name
from app.identity.resolution import AUTO_MERGE_SCORE, REVIEW_SCORE, score_candidates
from app.normalization.transformers import transform_api_football_players


# --------------------------------------------------------------------------- names
def test_name_normalisation_folds_accents_but_keeps_order_independent_key():
    assert normalize_name("Ángel Di María") == "angel di maria"
    assert name_key("Di María, Ángel") == name_key("Angel Maria")
    assert names_are_close("M. Akanji", "Manuel Akanji")
    assert not names_are_close("M. Akanji", "M. Aké")


def test_name_key_drops_particles_but_keeps_distinct_surnames():
    assert name_key("João Ferreira") != name_key("Pedro Ferreira")
    assert "de" not in name_key("Vitor de Marinho")


# ------------------------------------------------------------------- identity rules
class _FakePlayer:
    def __init__(self, name, dob=None, nationality=None, pid=1):
        self.id = pid
        self.name = name
        self.date_of_birth = dob
        self.nationality = nationality


def test_two_players_with_the_same_name_are_not_merged_on_name_alone():
    scored = score_candidates(
        name="John Smith",
        date_of_birth=None,
        nationality=None,
        club_ids=None,
        candidates=[
            (_FakePlayer("John Smith", date(1990, 1, 1), "England", 1), set()),
            (_FakePlayer("John Smith", date(1995, 6, 6), "England", 2), set()),
        ],
    )
    best, score, _evidence = scored[0]
    # Name matches but nothing else does: the score must stay below the auto-merge bar.
    assert score < AUTO_MERGE_SCORE
    assert score >= REVIEW_SCORE  # ... but it is queued for review instead of dropped


def test_same_name_same_dob_same_nationality_is_strong_evidence():
    scored = score_candidates(
        name="John Smith",
        date_of_birth=date(1990, 1, 1),
        nationality="England",
        club_ids={"50"},
        candidates=[(_FakePlayer("John Smith", date(1990, 1, 1), "England", 1), {"50"})],
    )
    _player, score, evidence = scored[0]
    assert score >= AUTO_MERGE_SCORE
    assert evidence.dob_match is True
    assert evidence.nationality_match is True
    assert evidence.shared_clubs == 1


def test_conflicting_date_of_birth_blocks_the_merge():
    scored = score_candidates(
        name="John Smith",
        date_of_birth=date(1990, 1, 1),
        nationality="England",
        club_ids=None,
        candidates=[(_FakePlayer("John Smith", date(1988, 3, 3), "England", 1), set())],
    )
    _player, score, evidence = scored[0]
    assert evidence.dob_match is False
    assert score < AUTO_MERGE_SCORE


def test_conflicting_nationality_lowers_the_score():
    scored = score_candidates(
        name="John Smith",
        date_of_birth=date(1990, 1, 1),
        nationality="England",
        club_ids=None,
        candidates=[(_FakePlayer("John Smith", date(1990, 1, 1), "Brazil", 1), set())],
    )
    _player, score, evidence = scored[0]
    assert evidence.nationality_match is False
    assert score < AUTO_MERGE_SCORE


# ---------------------------------------------------------------------- checkpoints
def test_scope_key_excludes_the_page_and_is_order_independent():
    assert scope_key({"league": 39, "season": 2023, "page": 2}) == scope_key(
        {"season": 2023, "league": 39}
    )
    assert scope_key({"team": "50", "season": 2023}) != scope_key({"team": "51", "season": 2023})


def test_checkpoint_status_vocabulary_is_explicit():
    assert COMPLETE == "COMPLETE_FOR_DECLARED_SCOPE"
    assert BLOCKED == "BLOCKED_BY_PLAN"
    assert PARTIAL == "PARTIAL"


# ---------------------------------------------------------------- country priorities
def test_country_priority_snapshot_is_dated_and_has_twenty_countries():
    snapshot = load_snapshot()
    assert snapshot.ranking_snapshot_date == date(2026, 10, 7)
    assert len(snapshot.countries) == 20
    assert snapshot.countries[0]["country_code"] == "ESP"
    assert snapshot.scope.startswith("men's senior")


def test_country_priority_snapshot_file_records_its_source():
    from app.ingestion.country_priorities import registry_dir

    payload = json.loads(
        (registry_dir() / "country_priority_snapshot_2026-10-07.json").read_text(encoding="utf-8")
    )
    assert "FIFA" in payload["ranking_source"]
    assert payload["ranking_snapshot_date"] == "2026-10-07"
    assert len(payload["countries"]) == 20


# ------------------------------------------------------------------- source policy
def test_every_evaluated_source_records_licence_and_enablement():
    names = {policy.name for policy in SOURCE_POLICIES}
    assert {"api-football", "statsbomb", "football-data-org", "openligadb", "thesportsdb"} <= names
    for policy in SOURCE_POLICIES:
        assert policy.license
        assert policy.notes


def test_sources_without_a_token_or_without_player_data_stay_disabled():
    disabled = {policy.name for policy in SOURCE_POLICIES if not policy.enabled}
    assert {"football-data-org", "openligadb", "thesportsdb"} <= disabled


# --------------------------------------------------------------------- scope plan
def test_priority_leagues_come_from_configuration_not_code():
    competitions = load_priority_competitions()
    assert [item.key for item in competitions][:5] == [
        "premier-league",
        "la-liga",
        "bundesliga",
        "serie-a",
        "ligue-1",
    ]
    assert all(item.provider_competition_id for item in competitions)


# ------------------------------------------------------------------- unknown != zero
def test_missing_provider_statistics_stay_none_and_measured_zero_stays_zero():
    payload = {
        "response": [
            {
                "player": {
                    "id": 1,
                    "name": "A. Player",
                    "firstname": "A",
                    "lastname": "Player",
                    "birth": {"date": "1995-01-01"},
                    "nationality": "Testland",
                    "height": "180",
                    "weight": "75",
                    "photo": "https://example.invalid/p.png",
                },
                "statistics": [
                    {
                        "team": {"id": 50},
                        "league": {"id": 39, "season": 2023},
                        "games": {"appearences": 10, "lineups": 10, "minutes": 900},
                        "goals": {"total": None, "assists": 1, "conceded": 0},
                    }
                ],
            }
        ]
    }
    players, stats = transform_api_football_players(payload)
    assert len(players) == 1 and len(stats) == 1
    stat = stats[0]
    assert stat.goals is None  # the provider sent null -> unknown, not zero
    assert stat.assists == 1
    assert stat.conceded == 0  # the provider sent 0 -> measured zero
    assert stat.minutes == 900
    assert stat.appearances == 10
    assert "A Player" in players[0].aliases
