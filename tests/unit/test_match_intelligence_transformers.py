from app.normalization.transformers import (
    _normalize_event_type,
    transform_api_football_events,
    transform_api_football_lineups,
    transform_api_football_statistics,
)


def test_normalize_event_type():
    assert _normalize_event_type("Goal") == "GOAL"
    assert _normalize_event_type("Card") == "CARD"
    assert _normalize_event_type("subst") == "SUBSTITUTION"
    assert _normalize_event_type("Substitution") == "SUBSTITUTION"
    assert _normalize_event_type("Var") == "VAR"
    assert _normalize_event_type("VAR-event") == "VAR"
    assert _normalize_event_type(None) == "OTHER"
    assert _normalize_event_type("custom") == "CUSTOM"


def test_transform_events():
    payload = {
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
    events = transform_api_football_events(payload)
    assert len(events) == 3

    e1 = events[0]
    assert e1.provider_fixture_id == "1492387"
    assert e1.provider_club_id == "126"
    assert e1.club_name == "Sao Paulo"
    assert e1.minute == 15
    assert e1.extra_minute is None
    assert e1.event_type == "GOAL"
    assert e1.event_detail == "Penalty"
    assert e1.provider_player_id == "47368"
    assert e1.player_name == "Jonathan Calleri"
    assert e1.provider_assist_id is None
    assert "15_0_GOAL_penalty_126_47368_none" == e1.event_key

    e2 = events[1]
    assert e2.minute == 90
    assert e2.extra_minute == 3
    assert e2.event_type == "CARD"
    assert e2.event_detail == "Yellow Card"
    assert e2.comments == "Dissent"
    assert e2.provider_player_id == "2044"

    e3 = events[2]
    assert e3.event_type == "SUBSTITUTION"
    assert e3.provider_player_id == "47368"
    assert e3.provider_assist_id == "106510"
    assert e3.assist_name == "Aldemir Ferreira"


def test_transform_lineups():
    payload = {
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
            }
        ],
    }
    lineups = transform_api_football_lineups(payload)
    assert len(lineups) == 2

    starter = lineups[0]
    assert starter.provider_fixture_id == "1492387"
    assert starter.provider_club_id == "126"
    assert starter.club_name == "Sao Paulo"
    assert starter.formation == "3-4-2-1"
    assert starter.coach_name == "Dorival Júnior"
    assert starter.provider_player_id == "10081"
    assert starter.player_name == "Rafael"
    assert starter.jersey_number == 23
    assert starter.position == "G"
    assert starter.grid == "1:1"
    assert starter.is_starter is True

    sub = lineups[1]
    assert sub.provider_player_id == "41188"
    assert sub.player_name == "André Silva"
    assert sub.jersey_number == 17
    assert sub.position == "F"
    assert sub.is_starter is False


def test_transform_statistics_preserves_zero_vs_null():
    payload = {
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
                    {"type": "Total passes", "value": 400},
                    {"type": "Passes accurate", "value": 320},
                    {"type": "Passes %", "value": "80%"},
                    # Note: expected_goals is absent / missing from the payload
                ],
            }
        ],
    }
    stats = transform_api_football_statistics(payload)
    assert len(stats) == 1

    s = stats[0]
    assert s.provider_fixture_id == "1492387"
    assert s.provider_club_id == "126"
    assert s.club_name == "Sao Paulo"
    assert s.possession_pct == 44.0
    assert s.shots_total == 6
    assert s.shots_on_target == 1
    # Critical test: explicit 0 vs missing/None
    assert s.red_cards == 0  # Provider reported 0 -> MUST BE 0!
    assert s.expected_goals is None  # Provider did NOT report expected_goals -> MUST BE None!
    assert s.fouls is None  # Absent from statistics list -> MUST BE None!
    assert s.yellow_cards == 1
    assert s.passes_total == 400
    assert s.passes_accurate == 320
    assert s.pass_accuracy_pct == 80.0
