from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from app.normalization.schemas import (
    NormalizedClub,
    NormalizedCompetition,
    NormalizedFixture,
    NormalizedPlayer,
    NormalizedPlayerStats,
    NormalizedScore,
    NormalizedScoreDetail,
    NormalizedSeason,
)

FIXTURE_STATUS_MAP: dict[str, str] = {
    "TBD": "SCHEDULED",
    "NS": "SCHEDULED",
    "1H": "LIVE",
    "HT": "LIVE",
    "2H": "LIVE",
    "ET": "LIVE",
    "BT": "LIVE",
    "P": "LIVE",
    "INT": "LIVE",
    "LIVE": "LIVE",
    "FT": "FINISHED",
    "AET": "FINISHED",
    "PEN": "FINISHED",
    "PST": "POSTPONED",
    "CANC": "CANCELLED",
    "ABD": "ABANDONED",
    "SUSP": "SUSPENDED",
    "AWD": "AWARDED",
    "WO": "AWARDED",
}


def _map_fixture_status(status_short: str | None) -> str:
    if not status_short:
        return "UNKNOWN"
    return FIXTURE_STATUS_MAP.get(status_short.strip().upper(), "UNKNOWN")


def _parse_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None
        try:
            dt = datetime.fromisoformat(val_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    return None


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


def transform_api_football_fixtures(
    payload: dict[str, Any],
) -> list[NormalizedFixture]:
    """Transform API-Football /fixtures response into NormalizedFixture records."""
    response = payload.get("response", [])
    fixtures: list[NormalizedFixture] = []

    for item in response:
        if not isinstance(item, dict):
            continue
        fixture_data = item.get("fixture", {})
        league_data = item.get("league", {})
        teams_data = item.get("teams", {})
        goals_data = item.get("goals", {})
        score_data = item.get("score", {})

        fixture_id = fixture_data.get("id")
        if fixture_id is None:
            continue

        raw_date = fixture_data.get("date")
        raw_timestamp = fixture_data.get("timestamp")
        parsed_dt = _parse_datetime(raw_date)
        if parsed_dt is None and raw_timestamp is not None:
            try:
                parsed_dt = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                parsed_dt = None

        if parsed_dt is None:
            # Kickoff datetime is required for canonical match data quality rule
            continue

        status_obj = fixture_data.get("status", {})
        status_short = status_obj.get("short")
        status_long = status_obj.get("long")
        elapsed = _parse_int_clean(status_obj.get("elapsed"))
        canonical_status = _map_fixture_status(status_short)

        venue_obj = fixture_data.get("venue", {})
        venue_name = venue_obj.get("name") if isinstance(venue_obj, dict) else None
        venue_city = venue_obj.get("city") if isinstance(venue_obj, dict) else None
        referee = fixture_data.get("referee")

        league_id = league_data.get("id")
        season_year = _parse_int_clean(league_data.get("season"))
        if league_id is None or season_year is None:
            continue

        home_team = teams_data.get("home", {})
        away_team = teams_data.get("away", {})
        home_id = home_team.get("id")
        away_id = away_team.get("id")
        if home_id is None or away_id is None:
            continue

        # Data quality rule: home != away
        if str(home_id) == str(away_id):
            continue

        home_winner = home_team.get("winner")
        away_winner = away_team.get("winner")

        def _parse_detail(stage_data: Any) -> NormalizedScoreDetail:
            if not isinstance(stage_data, dict):
                return NormalizedScoreDetail()
            return NormalizedScoreDetail(
                home=_parse_int_clean(stage_data.get("home")),
                away=_parse_int_clean(stage_data.get("away")),
            )

        ht_score = _parse_detail(score_data.get("halftime"))
        ft_score = _parse_detail(score_data.get("fulltime"))
        et_score = _parse_detail(score_data.get("extratime"))
        pen_score = _parse_detail(score_data.get("penalty"))

        norm_score = NormalizedScore(
            halftime=ht_score,
            fulltime=ft_score,
            extratime=et_score,
            penalty=pen_score,
        )

        home_score = _parse_int_clean(goals_data.get("home"))
        away_score = _parse_int_clean(goals_data.get("away"))
        if canonical_status == "FINISHED":
            if home_score is None and ft_score.home is not None:
                home_score = ft_score.home
            if away_score is None and ft_score.away is not None:
                away_score = ft_score.away
        elif canonical_status in ("SCHEDULED", "POSTPONED", "CANCELLED", "SUSPENDED", "ABANDONED"):
            if canonical_status in ("SCHEDULED", "POSTPONED", "CANCELLED"):
                home_score = None
                away_score = None

        round_val = league_data.get("round")
        stage_val = None
        if round_val and " - " in round_val:
            stage_val = round_val.split(" - ")[0].strip()

        fixture = NormalizedFixture(
            provider_fixture_id=str(fixture_id),
            date=parsed_dt,
            timestamp=_parse_int_clean(raw_timestamp),
            status=canonical_status,
            status_detail=status_long or status_short,
            elapsed=elapsed,
            round=round_val,
            stage=stage_val,
            venue_name=venue_name,
            venue_city=venue_city,
            referee=referee,
            provider_league_id=str(league_id),
            league_name=league_data.get("name", "Unknown"),
            league_country=league_data.get("country", "Unknown"),
            season_year=season_year,
            home_provider_club_id=str(home_id),
            home_club_name=home_team.get("name", "Unknown"),
            home_club_logo=home_team.get("logo"),
            home_winner=home_winner if isinstance(home_winner, bool) else None,
            away_provider_club_id=str(away_id),
            away_club_name=away_team.get("name", "Unknown"),
            away_club_logo=away_team.get("logo"),
            away_winner=away_winner if isinstance(away_winner, bool) else None,
            home_score=home_score,
            away_score=away_score,
            score=norm_score,
        )
        fixtures.append(fixture)

    return fixtures
