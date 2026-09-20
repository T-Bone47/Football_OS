from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.normalization.schemas import (
    NormalizedClub,
    NormalizedCompetition,
    NormalizedPlayer,
    NormalizedPlayerStats,
    NormalizedSeason,
)


def _parse_int_clean(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, int):
        return val
    s = str(val).strip()
    match = re.search(r"\d+", s)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None
    return None


def _parse_float_clean(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


def _parse_date(val: Any) -> date | None:
    if not val or not isinstance(val, str):
        return None
    try:
        return date.fromisoformat(val.strip())
    except (ValueError, TypeError):
        return None


def transform_api_football_teams(payload: dict[str, Any]) -> list[NormalizedClub]:
    """Transform API-Football /teams response into NormalizedClub records."""
    response = payload.get("response", [])
    clubs: list[NormalizedClub] = []

    for item in response:
        team_data = item.get("team", {})
        venue_data = item.get("venue", {})

        team_id = team_data.get("id")
        if team_id is None:
            continue

        club = NormalizedClub(
            provider_id=str(team_id),
            name=team_data.get("name", "Unknown"),
            code=team_data.get("code"),
            country=team_data.get("country", "Unknown"),
            founded=_parse_int_clean(team_data.get("founded")),
            venue_name=venue_data.get("name"),
            venue_capacity=_parse_int_clean(venue_data.get("capacity")),
            logo_url=team_data.get("logo"),
        )
        clubs.append(club)

    return clubs


def transform_api_football_players(
    payload: dict[str, Any],
) -> tuple[list[NormalizedPlayer], list[NormalizedPlayerStats]]:
    """Transform API-Football /players response into NormalizedPlayer and NormalizedPlayerStats records."""
    response = payload.get("response", [])
    players: list[NormalizedPlayer] = []
    stats_list: list[NormalizedPlayerStats] = []

    for item in response:
        p_data = item.get("player", {})
        player_id = p_data.get("id")
        if player_id is None:
            continue

        str_player_id = str(player_id)
        birth = p_data.get("birth", {})

        player = NormalizedPlayer(
            provider_id=str_player_id,
            name=p_data.get("name", "Unknown"),
            first_name=p_data.get("firstname"),
            last_name=p_data.get("lastname"),
            date_of_birth=_parse_date(birth.get("date")),
            nationality=p_data.get("nationality"),
            height_cm=_parse_int_clean(p_data.get("height")),
            weight_kg=_parse_int_clean(p_data.get("weight")),
            primary_position=None,  # Will be enriched from games if present
            photo_url=p_data.get("photo"),
        )

        statistics = item.get("statistics", [])
        primary_pos = None

        for stat in statistics:
            team = stat.get("team", {})
            league = stat.get("league", {})
            games = stat.get("games", {})
            goals = stat.get("goals", {})
            tackles = stat.get("tackles", {})
            passes = stat.get("passes", {})
            duels = stat.get("duels", {})
            dribbles = stat.get("dribbles", {})
            fouls = stat.get("fouls", {})
            cards = stat.get("cards", {})

            league_id = league.get("id")
            season_year = _parse_int_clean(league.get("season"))
            if league_id is None or season_year is None:
                continue

            pos = games.get("position")
            if pos and not primary_pos:
                primary_pos = pos

            team_id = team.get("id")
            str_team_id = str(team_id) if team_id is not None else None

            player_stat = NormalizedPlayerStats(
                provider_player_id=str_player_id,
                provider_club_id=str_team_id,
                provider_league_id=str(league_id),
                season_year=season_year,
                appearances=_parse_int_clean(games.get("appearences")) or 0,
                lineups=_parse_int_clean(games.get("lineups")) or 0,
                minutes=_parse_int_clean(games.get("minutes")) or 0,
                position=pos,
                rating=_parse_float_clean(games.get("rating")),
                goals=_parse_int_clean(goals.get("total")) or 0,
                assists=_parse_int_clean(goals.get("assists")) or 0,
                conceded=_parse_int_clean(goals.get("conceded")) or 0,
                raw_stats={
                    "passes": passes,
                    "tackles": tackles,
                    "duels": duels,
                    "dribbles": dribbles,
                    "fouls": fouls,
                    "cards": cards,
                },
            )
            stats_list.append(player_stat)

        if primary_pos and not player.primary_position:
            player.primary_position = primary_pos

        players.append(player)

    return players, stats_list


def transform_api_football_leagues(
    payload: dict[str, Any],
) -> list[tuple[NormalizedCompetition, list[NormalizedSeason]]]:
    """Transform API-Football /leagues response into NormalizedCompetition and NormalizedSeason records."""
    response = payload.get("response", [])
    results: list[tuple[NormalizedCompetition, list[NormalizedSeason]]] = []

    for item in response:
        league = item.get("league", {})
        country = item.get("country", {})
        seasons_data = item.get("seasons", [])

        league_id = league.get("id")
        if league_id is None:
            continue

        comp = NormalizedCompetition(
            provider_id=str(league_id),
            name=league.get("name", "Unknown"),
            country=country.get("name", "Unknown"),
            type=league.get("type", "LEAGUE").upper(),
        )

        seasons: list[NormalizedSeason] = []
        for s in seasons_data:
            year = _parse_int_clean(s.get("year"))
            if year is None:
                continue
            season = NormalizedSeason(
                name=str(year),
                start_year=year,
                end_year=year + 1,
                start_date=_parse_date(s.get("start")),
                end_date=_parse_date(s.get("end")),
                is_current=bool(s.get("current")),
            )
            seasons.append(season)

        results.append((comp, seasons))

    return results
