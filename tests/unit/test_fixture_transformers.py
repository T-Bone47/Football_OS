from datetime import datetime, timezone

import pytest

from app.normalization.schemas import NormalizedFixture
from app.normalization.transformers import (
    _map_fixture_status,
    _parse_datetime,
    transform_api_football_fixtures,
)


def test_fixture_status_mapping():
    assert _map_fixture_status("NS") == "SCHEDULED"
    assert _map_fixture_status("TBD") == "SCHEDULED"
    assert _map_fixture_status("1H") == "LIVE"
    assert _map_fixture_status("HT") == "LIVE"
    assert _map_fixture_status("2H") == "LIVE"
    assert _map_fixture_status("FT") == "FINISHED"
    assert _map_fixture_status("AET") == "FINISHED"
    assert _map_fixture_status("PEN") == "FINISHED"
    assert _map_fixture_status("PST") == "POSTPONED"
    assert _map_fixture_status("CANC") == "CANCELLED"
    assert _map_fixture_status("ABD") == "ABANDONED"
    assert _map_fixture_status("SUSP") == "SUSPENDED"
    assert _map_fixture_status("AWD") == "AWARDED"
    assert _map_fixture_status("UNKNOWN_STATUS") == "UNKNOWN"
    assert _map_fixture_status(None) == "UNKNOWN"
    assert _map_fixture_status("") == "UNKNOWN"


def test_parse_datetime_timezone_awareness():
    # Valid UTC ISO string
    dt1 = _parse_datetime("2026-09-20T13:00:00+00:00")
    assert dt1 is not None
    assert dt1.tzinfo is not None
    assert dt1.hour == 13

    # Timezone offset (+02:00)
    dt2 = _parse_datetime("2026-09-20T15:00:00+02:00")
    assert dt2 is not None
    assert dt2.tzinfo is not None
    # Converted to UTC, 15:00+02:00 is 13:00 UTC
    assert dt2.astimezone(timezone.utc).hour == 13

    # Naive ISO string gets UTC tzinfo
    dt3 = _parse_datetime("2026-09-20T13:00:00")
    assert dt3 is not None
    assert dt3.tzinfo is not None

    # Invalid string
    assert _parse_datetime("invalid-date") is None
    assert _parse_datetime(None) is None
    assert _parse_datetime("") is None


def test_transform_api_football_fixtures_finished_match():
    payload = {
        "response": [
            {
                "fixture": {
                    "id": 1492387,
                    "referee": "Bruno Arleu",
                    "timezone": "UTC",
                    "date": "2026-09-20T00:00:00+00:00",
                    "timestamp": 1789862400,
                    "venue": {"id": 269, "name": "Morumbi", "city": "Sao Paulo"},
                    "status": {
                        "long": "Match Finished",
                        "short": "FT",
                        "elapsed": 90,
                    },
                },
                "league": {
                    "id": 71,
                    "name": "Serie A",
                    "country": "Brazil",
                    "season": 2026,
                    "round": "Regular Season - 28",
                },
                "teams": {
                    "home": {"id": 126, "name": "Sao Paulo", "winner": True, "logo": "http://sp.png"},
                    "away": {"id": 119, "name": "Internacional", "winner": False, "logo": "http://int.png"},
                },
                "goals": {"home": 1, "away": 0},
                "score": {
                    "halftime": {"home": 1, "away": 0},
                    "fulltime": {"home": 1, "away": 0},
                    "extratime": {"home": None, "away": None},
                    "penalty": {"home": None, "away": None},
                },
            }
        ]
    }

    fixtures = transform_api_football_fixtures(payload)
    assert len(fixtures) == 1
    f = fixtures[0]

    assert isinstance(f, NormalizedFixture)
    assert f.provider_fixture_id == "1492387"
    assert f.status == "FINISHED"
    assert f.status_detail == "Match Finished"
    assert f.date == datetime(2026, 9, 20, 0, 0, 0, tzinfo=timezone.utc)
    assert f.venue_name == "Morumbi"
    assert f.venue_city == "Sao Paulo"
    assert f.referee == "Bruno Arleu"
    assert f.round == "Regular Season - 28"
    assert f.stage == "Regular Season"
    assert f.provider_league_id == "71"
    assert f.league_name == "Serie A"
    assert f.season_year == 2026

    assert f.home_provider_club_id == "126"
    assert f.home_club_name == "Sao Paulo"
    assert f.home_winner is True
    assert f.away_provider_club_id == "119"
    assert f.away_club_name == "Internacional"
    assert f.away_winner is False

    assert f.home_score == 1
    assert f.away_score == 0
    assert f.score.halftime.home == 1
    assert f.score.halftime.away == 0
    assert f.score.fulltime.home == 1
    assert f.score.fulltime.away == 0
    assert f.score.extratime.home is None
    assert f.score.penalty.home is None


def test_transform_api_football_fixtures_scheduled_match():
    payload = {
        "response": [
            {
                "fixture": {
                    "id": 1557413,
                    "referee": "Robert Jones",
                    "timezone": "UTC",
                    "date": "2026-09-20T13:00:00+00:00",
                    "timestamp": 1789909200,
                    "venue": {"id": 555, "name": "Etihad Stadium", "city": "Manchester"},
                    "status": {
                        "long": "Not Started",
                        "short": "NS",
                        "elapsed": None,
                    },
                },
                "league": {
                    "id": 39,
                    "name": "Premier League",
                    "country": "England",
                    "season": 2026,
                    "round": "Regular Season - 5",
                },
                "teams": {
                    "home": {"id": 50, "name": "Manchester City", "winner": None},
                    "away": {"id": 746, "name": "Sunderland", "winner": None},
                },
                "goals": {"home": None, "away": None},
                "score": {
                    "halftime": {"home": None, "away": None},
                    "fulltime": {"home": None, "away": None},
                    "extratime": {"home": None, "away": None},
                    "penalty": {"home": None, "away": None},
                },
            }
        ]
    }

    fixtures = transform_api_football_fixtures(payload)
    assert len(fixtures) == 1
    f = fixtures[0]

    assert f.provider_fixture_id == "1557413"
    assert f.status == "SCHEDULED"
    assert f.status_detail == "Not Started"
    assert f.home_score is None
    assert f.away_score is None
    assert f.home_winner is None
    assert f.away_winner is None


def test_transform_api_football_fixtures_extra_time_and_penalties():
    payload = {
        "response": [
            {
                "fixture": {
                    "id": 999999,
                    "date": "2026-05-30T19:00:00+00:00",
                    "status": {"short": "PEN", "long": "Match Finished After Penalties"},
                },
                "league": {"id": 2, "name": "Champions League", "country": "Europe", "season": 2025},
                "teams": {
                    "home": {"id": 50, "name": "Manchester City", "winner": False},
                    "away": {"id": 541, "name": "Real Madrid", "winner": True},
                },
                "goals": {"home": 1, "away": 1},
                "score": {
                    "halftime": {"home": 1, "away": 0},
                    "fulltime": {"home": 1, "away": 1},
                    "extratime": {"home": 1, "away": 1},
                    "penalty": {"home": 3, "away": 4},
                },
            }
        ]
    }

    fixtures = transform_api_football_fixtures(payload)
    assert len(fixtures) == 1
    f = fixtures[0]

    assert f.status == "FINISHED"
    assert f.home_score == 1
    assert f.away_score == 1
    assert f.score.fulltime.home == 1
    assert f.score.fulltime.away == 1
    assert f.score.extratime.home == 1
    assert f.score.extratime.away == 1
    assert f.score.penalty.home == 3
    assert f.score.penalty.away == 4
    assert f.away_winner is True
    assert f.home_winner is False


def test_transform_api_football_fixtures_data_quality_rejections():
    # 1. Missing fixture ID
    bad_payload_no_id = {
        "response": [
            {
                "fixture": {"date": "2026-09-20T13:00:00+00:00"},
                "league": {"id": 39, "season": 2026},
                "teams": {"home": {"id": 50}, "away": {"id": 42}},
            }
        ]
    }
    assert len(transform_api_football_fixtures(bad_payload_no_id)) == 0

    # 2. Missing date
    bad_payload_no_date = {
        "response": [
            {
                "fixture": {"id": 100},
                "league": {"id": 39, "season": 2026},
                "teams": {"home": {"id": 50}, "away": {"id": 42}},
            }
        ]
    }
    assert len(transform_api_football_fixtures(bad_payload_no_date)) == 0

    # 3. Home == Away (impossible fixture)
    bad_payload_same_team = {
        "response": [
            {
                "fixture": {"id": 100, "date": "2026-09-20T13:00:00+00:00"},
                "league": {"id": 39, "season": 2026},
                "teams": {"home": {"id": 50}, "away": {"id": 50}},
            }
        ]
    }
    assert len(transform_api_football_fixtures(bad_payload_same_team)) == 0

    # 4. Missing team IDs
    bad_payload_no_team = {
        "response": [
            {
                "fixture": {"id": 100, "date": "2026-09-20T13:00:00+00:00"},
                "league": {"id": 39, "season": 2026},
                "teams": {"home": {"id": 50}},
            }
        ]
    }
    assert len(transform_api_football_fixtures(bad_payload_no_team)) == 0
