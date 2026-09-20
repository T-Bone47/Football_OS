import pytest
from app.normalization.transformers import (
    _parse_rating_clean,
    _parse_percentage_clean,
    transform_api_football_player_statistics,
)


def test_parse_rating_clean():
    # Valid ratings
    assert _parse_rating_clean("7.8") == 7.8
    assert _parse_rating_clean("7.80") == 7.8
    assert _parse_rating_clean("6.61") == 6.61
    assert _parse_rating_clean(6.5) == 6.5

    # Missing, empty, or placeholder
    assert _parse_rating_clean(None) is None
    assert _parse_rating_clean("") is None
    assert _parse_rating_clean("   ") is None
    assert _parse_rating_clean("-") is None
    assert _parse_rating_clean("None") is None
    assert _parse_rating_clean("null") is None
    assert _parse_rating_clean("invalid") is None

    # Rating "0" or 0 when player had 0 minutes (unused sub unrated placeholder)
    assert _parse_rating_clean("0", minutes=0) is None
    assert _parse_rating_clean(0, minutes=0) is None
    assert _parse_rating_clean("0", minutes=None) is None

    # If player played minutes and had explicit 0 rating
    assert _parse_rating_clean("0", minutes=90) == 0.0


def test_parse_percentage_clean():
    assert _parse_percentage_clean("19") == 19.0
    assert _parse_percentage_clean("85%") == 85.0
    assert _parse_percentage_clean(" 72.5% ") == 72.5
    assert _parse_percentage_clean(85) == 85.0
    assert _parse_percentage_clean(None) is None
    assert _parse_percentage_clean("") is None
    assert _parse_percentage_clean("N/A") is None


def test_transform_player_statistics_full_payload():
    payload = {
        "parameters": {"fixture": "1492387"},
        "response": [
            {
                "team": {"id": 119, "name": "Internacional"},
                "players": [
                    {
                        "player": {
                            "id": 306552,
                            "name": "Anthoni",
                            "photo": "https://media.api-sports.io/football/players/306552.png",
                        },
                        "statistics": [
                            {
                                "games": {
                                    "minutes": 90,
                                    "number": 12,
                                    "position": "G",
                                    "rating": "5.91",
                                    "captain": False,
                                    "substitute": False,
                                },
                                "offsides": 0,
                                "shots": {"total": 0, "on": 0},
                                "goals": {"total": 0, "conceded": 0, "assists": 0, "saves": 3},
                                "passes": {"total": 29, "key": 0, "accuracy": "19"},
                                "tackles": {"total": 0, "blocks": 0, "interceptions": 0},
                                "duels": {"total": 2, "won": 1},
                                "dribbles": {"attempts": 0, "success": 0, "past": None},
                                "fouls": {"drawn": 0, "committed": 0},
                                "cards": {"yellow": 0, "red": 0},
                                "penalty": {
                                    "won": None,
                                    "commited": None,
                                    "scored": 0,
                                    "missed": None,
                                    "saved": None,
                                },
                            }
                        ],
                    }
                ],
            },
            {
                "team": {"id": 126, "name": "Sao Paulo"},
                "players": [
                    {
                        "player": {
                            "id": 47368,
                            "name": "Jonathan Calleri",
                            "photo": "https://media.api-sports.io/football/players/47368.png",
                        },
                        "statistics": [
                            {
                                "games": {
                                    "minutes": 73,
                                    "number": 9,
                                    "position": "F",
                                    "rating": "7.45",
                                    "captain": True,
                                    "substitute": False,
                                },
                                "offsides": 1,
                                "shots": {"total": 3, "on": 2},
                                "goals": {"total": 1, "conceded": None, "assists": 0, "saves": None},
                                "passes": {"total": 18, "key": 2, "accuracy": "78%"},
                                "tackles": {"total": 1, "blocks": 0, "interceptions": 1},
                                "duels": {"total": 12, "won": 7},
                                "dribbles": {"attempts": 2, "success": 1, "past": 0},
                                "fouls": {"drawn": 3, "committed": 2},
                                "cards": {"yellow": 1, "red": 0},
                                "penalty": {
                                    "won": 1,
                                    "commited": 0,
                                    "scored": 1,
                                    "missed": 0,
                                    "saved": None,
                                },
                            }
                        ],
                    },
                    {
                        "player": {
                            "id": 41188,
                            "name": "Andre Silva",
                            "photo": "https://media.api-sports.io/football/players/41188.png",
                        },
                        "statistics": [
                            {
                                "games": {
                                    "minutes": 17,
                                    "number": 17,
                                    "position": "F",
                                    "rating": "6.47",
                                    "captain": False,
                                    "substitute": True,
                                },
                                "offsides": 0,
                                "shots": {"total": 1, "on": 1},
                                "goals": {"total": 0, "conceded": None, "assists": 0, "saves": None},
                                "passes": {"total": 4, "key": 0, "accuracy": "75"},
                                "tackles": {"total": 0, "blocks": 0, "interceptions": 0},
                                "duels": {"total": 3, "won": 1},
                                "dribbles": {"attempts": 0, "success": 0, "past": None},
                                "fouls": {"drawn": 0, "committed": 1},
                                "cards": {"yellow": 0, "red": 0},
                                "penalty": {
                                    "won": None,
                                    "commited": None,
                                    "scored": 0,
                                    "missed": None,
                                    "saved": None,
                                },
                            }
                        ],
                    },
                ],
            },
        ],
    }

    records = transform_api_football_player_statistics(payload)
    assert len(records) == 3

    # 1. Goalkeeper record
    gk = records[0]
    assert gk.provider_fixture_id == "1492387"
    assert gk.provider_club_id == "119"
    assert gk.club_name == "Internacional"
    assert gk.provider_player_id == "306552"
    assert gk.player_name == "Anthoni"
    assert gk.position == "G"
    assert gk.jersey_number == 12
    assert gk.minutes == 90
    assert gk.rating == 5.91
    assert gk.is_starter is True
    assert gk.is_substitute is False
    assert gk.is_captain is False
    # Strict preservation of 0 vs None
    assert gk.goals == 0
    assert gk.goals_conceded == 0
    assert gk.clean_sheet is True
    assert gk.saves == 3
    assert gk.assists == 0
    assert gk.shots_total == 0
    assert gk.shots_on_target == 0
    assert gk.passes_total == 29
    assert gk.passes_key == 0
    assert gk.pass_accuracy == 19.0
    assert gk.duels_total == 2
    assert gk.duels_won == 1
    assert gk.dribbles_past is None  # explicitly null from provider
    assert gk.penalties_won is None  # explicitly null from provider
    assert gk.penalties_committed is None

    # 2. Outfield Starter record
    striker = records[1]
    assert striker.provider_fixture_id == "1492387"
    assert striker.provider_club_id == "126"
    assert striker.club_name == "Sao Paulo"
    assert striker.provider_player_id == "47368"
    assert striker.player_name == "Jonathan Calleri"
    assert striker.position == "F"
    assert striker.jersey_number == 9
    assert striker.minutes == 73
    assert striker.rating == 7.45
    assert striker.is_starter is True
    assert striker.is_substitute is False
    assert striker.is_captain is True
    assert striker.goals == 1
    assert striker.goals_conceded is None  # Outfield player
    assert striker.clean_sheet is None
    assert striker.shots_total == 3
    assert striker.shots_on_target == 2
    assert striker.passes_total == 18
    assert striker.passes_key == 2
    assert striker.pass_accuracy == 78.0
    assert striker.offsides == 1
    assert striker.yellow_cards == 1
    assert striker.red_cards == 0
    assert striker.penalties_won == 1
    assert striker.penalties_committed == 0
    assert striker.penalties_scored == 1
    assert striker.penalties_missed == 0

    # 3. Substitute record
    sub = records[2]
    assert sub.provider_player_id == "41188"
    assert sub.is_starter is False
    assert sub.is_substitute is True
    assert sub.minutes == 17
    assert sub.rating == 6.47
    assert sub.pass_accuracy == 75.0


def test_transform_player_statistics_empty_and_unused_sub():
    payload = {
        "parameters": {"fixture": "1492387"},
        "response": [
            {
                "team": {"id": 119, "name": "Internacional"},
                "players": [
                    {
                        "player": {"id": 9893, "name": "Alerrandro", "photo": None},
                        "statistics": [
                            {
                                "games": {
                                    "minutes": 0,
                                    "number": 9,
                                    "position": "F",
                                    "rating": "0",
                                    "captain": False,
                                    "substitute": True,
                                },
                                "offsides": None,
                                "shots": {"total": None, "on": None},
                                "goals": {"total": 0, "conceded": None, "assists": None, "saves": None},
                                "passes": {"total": None, "key": None, "accuracy": None},
                            }
                        ],
                    }
                ],
            }
        ],
    }

    records = transform_api_football_player_statistics(payload)
    assert len(records) == 1
    rec = records[0]
    assert rec.player_name == "Alerrandro"
    assert rec.minutes == 0
    assert rec.rating is None  # rating "0" with 0 minutes parses to None
    assert rec.is_starter is False
    assert rec.is_substitute is True
    assert rec.goals == 0  # explicit 0 preserved
    assert rec.assists is None  # missing/None preserved
    assert rec.shots_total is None
    assert rec.passes_total is None
