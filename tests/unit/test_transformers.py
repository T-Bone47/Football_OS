from datetime import date

from app.normalization.transformers import (
    _parse_date,
    _parse_float_clean,
    _parse_int_clean,
    transform_api_football_leagues,
    transform_api_football_players,
    transform_api_football_teams,
)


def test_transformers_parsing_helpers():
    from app.normalization.transformers import _parse_int_clean, _parse_float_clean, _parse_date
    assert _parse_int_clean("188 cm") == 188
    assert _parse_int_clean("91 kg") == 91
    assert _parse_int_clean(188) == 188
    assert _parse_int_clean(None) is None
    assert _parse_int_clean("N/A") is None

    assert _parse_float_clean("7.28") == 7.28
    assert _parse_float_clean(7.5) == 7.5
    assert _parse_float_clean(None) is None

    assert _parse_date("1995-07-19") == date(1995, 7, 19)
    assert _parse_date(None) is None
    assert _parse_date("invalid-date") is None


def test_transform_api_football_teams():
    payload = {
        "response": [
            {
                "team": {
                    "id": 50,
                    "name": "Manchester City",
                    "code": "MCI",
                    "country": "England",
                    "founded": 1880,
                    "logo": "https://media.api-sports.io/football/teams/50.png",
                },
                "venue": {
                    "id": 555,
                    "name": "Etihad Stadium",
                    "capacity": 55097,
                },
            }
        ]
    }
    clubs = transform_api_football_teams(payload)
    assert len(clubs) == 1
    c = clubs[0]
    assert c.provider_id == "50"
    assert c.name == "Manchester City"
    assert c.code == "MCI"
    assert c.country == "England"
    assert c.founded == 1880
    assert c.venue_name == "Etihad Stadium"
    assert c.venue_capacity == 55097


def test_transform_api_football_players():
    payload = {
        "response": [
            {
                "player": {
                    "id": 5,
                    "name": "M. Akanji",
                    "firstname": "Manuel Obafemi",
                    "lastname": "Akanji",
                    "birth": {"date": "1995-07-19", "country": "Switzerland"},
                    "nationality": "Switzerland",
                    "height": "188 cm",
                    "weight": "91 kg",
                    "photo": "https://media.api-sports.io/football/players/5.png",
                },
                "statistics": [
                    {
                        "team": {"id": 50, "name": "Manchester City"},
                        "league": {"id": 39, "name": "Premier League", "season": 2023},
                        "games": {
                            "appearences": 30,
                            "lineups": 28,
                            "minutes": 2500,
                            "position": "Defender",
                            "rating": "7.25",
                        },
                        "goals": {"total": 2, "assists": 1, "conceded": 0},
                        "tackles": {"total": 40},
                        "passes": {"total": 2000},
                        "duels": {"total": 150},
                        "dribbles": {"attempts": 5},
                        "fouls": {"drawn": 10},
                        "cards": {"yellow": 3},
                    }
                ],
            }
        ]
    }
    players, stats_list = transform_api_football_players(payload)
    assert len(players) == 1
    p = players[0]
    assert p.provider_id == "5"
    assert p.name == "M. Akanji"
    assert p.first_name == "Manuel Obafemi"
    assert p.date_of_birth == date(1995, 7, 19)
    assert p.height_cm == 188
    assert p.weight_kg == 91
    assert p.primary_position == "Defender"

    assert len(stats_list) == 1
    s = stats_list[0]
    assert s.provider_player_id == "5"
    assert s.provider_club_id == "50"
    assert s.provider_league_id == "39"
    assert s.season_year == 2023
    assert s.appearances == 30
    assert s.minutes == 2500
    assert s.goals == 2
    assert s.assists == 1
    assert s.rating == 7.25
    assert s.raw_stats["passes"] == {"total": 2000}


def test_transform_api_football_leagues():
    payload = {
        "response": [
            {
                "league": {"id": 39, "name": "Premier League", "type": "League"},
                "country": {"name": "England"},
                "seasons": [
                    {"year": 2023, "start": "2023-08-11", "end": "2024-05-19", "current": True}
                ],
            }
        ]
    }
    results = transform_api_football_leagues(payload)
    assert len(results) == 1
    comp, seasons = results[0]
    assert comp.provider_id == "39"
    assert comp.name == "Premier League"
    assert comp.country == "England"
    assert comp.type == "LEAGUE"

    assert len(seasons) == 1
    s = seasons[0]
    assert s.name == "2023"
    assert s.start_year == 2023
    assert s.end_year == 2024
    assert s.start_date == date(2023, 8, 11)
    assert s.end_date == date(2024, 5, 19)
    assert s.is_current is True
