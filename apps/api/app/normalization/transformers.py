from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from app.normalization.schemas import (
    NormalizedClub,
    NormalizedCompetition,
    NormalizedFixture,
    NormalizedMatchEvent,
    NormalizedMatchLineup,
    NormalizedMatchStatistics,
    NormalizedPlayer,
    NormalizedPlayerMatchStats,
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


def _normalize_event_type(raw_type: str | None) -> str:
    if not raw_type:
        return "OTHER"
    clean = raw_type.strip().lower()
    if clean == "goal":
        return "GOAL"
    if clean == "card":
        return "CARD"
    if clean in ("subst", "substitution"):
        return "SUBSTITUTION"
    if clean in ("var", "var-event"):
        return "VAR"
    return clean.upper()


def transform_api_football_events(
    payload: dict[str, Any], fixture_id: str | None = None
) -> list[NormalizedMatchEvent]:
    """Transform API-Football /fixtures/events response into NormalizedMatchEvent records."""
    target_fixture_id = fixture_id or str(payload.get("parameters", {}).get("fixture") or "")
    response = payload.get("response", [])
    events: list[NormalizedMatchEvent] = []

    for item in response:
        if not isinstance(item, dict):
            continue

        time_data = item.get("time", {})
        team_data = item.get("team", {})
        player_data = item.get("player", {}) or {}
        assist_data = item.get("assist", {}) or {}

        elapsed = _parse_int_clean(time_data.get("elapsed"))
        team_id = team_data.get("id")
        if elapsed is None or team_id is None:
            # Data quality requirement: elapsed minute and team are required
            continue

        extra = _parse_int_clean(time_data.get("extra"))
        raw_type = item.get("type")
        event_type = _normalize_event_type(raw_type)
        detail = item.get("detail")
        comments = item.get("comments")

        player_id = player_data.get("id")
        player_name = player_data.get("name")
        assist_id = assist_data.get("id")
        assist_name = assist_data.get("name")

        # Deterministic natural key for idempotency
        p_id_str = str(player_id) if player_id is not None else "none"
        a_id_str = str(assist_id) if assist_id is not None else "none"
        det_str = (detail or "").strip().lower()
        event_key = f"{elapsed}_{extra or 0}_{event_type}_{det_str}_{team_id}_{p_id_str}_{a_id_str}"

        event = NormalizedMatchEvent(
            provider_fixture_id=target_fixture_id,
            provider_club_id=str(team_id),
            club_name=team_data.get("name"),
            provider_player_id=str(player_id) if player_id is not None else None,
            player_name=player_name,
            provider_assist_id=str(assist_id) if assist_id is not None else None,
            assist_name=assist_name,
            event_type=event_type,
            event_detail=detail,
            minute=elapsed,
            extra_minute=extra,
            comments=comments,
            event_key=event_key,
            provider_event_id=None,
        )
        events.append(event)

    return events


def transform_api_football_lineups(
    payload: dict[str, Any], fixture_id: str | None = None
) -> list[NormalizedMatchLineup]:
    """Transform API-Football /fixtures/lineups response into NormalizedMatchLineup records."""
    target_fixture_id = fixture_id or str(payload.get("parameters", {}).get("fixture") or "")
    response = payload.get("response", [])
    lineups: list[NormalizedMatchLineup] = []

    for item in response:
        if not isinstance(item, dict):
            continue

        team_data = item.get("team", {})
        team_id = team_data.get("id")
        if team_id is None:
            continue

        team_name = team_data.get("name")
        formation = item.get("formation")
        coach_data = item.get("coach", {}) or {}
        coach_name = coach_data.get("name")

        # 1. Starting XI
        for starter in item.get("startXI", []):
            if not isinstance(starter, dict):
                continue
            p_data = starter.get("player", {}) or {}
            p_id = p_data.get("id")
            p_name = p_data.get("name")
            if p_id is None or not p_name:
                continue

            lineups.append(
                NormalizedMatchLineup(
                    provider_fixture_id=target_fixture_id,
                    provider_club_id=str(team_id),
                    club_name=team_name,
                    formation=formation,
                    coach_name=coach_name,
                    provider_player_id=str(p_id),
                    player_name=p_name,
                    jersey_number=_parse_int_clean(p_data.get("number")),
                    position=p_data.get("pos"),
                    grid=p_data.get("grid"),
                    is_starter=True,
                    is_captain=False,
                )
            )

        # 2. Substitutes
        for sub in item.get("substitutes", []):
            if not isinstance(sub, dict):
                continue
            p_data = sub.get("player", {}) or {}
            p_id = p_data.get("id")
            p_name = p_data.get("name")
            if p_id is None or not p_name:
                continue

            lineups.append(
                NormalizedMatchLineup(
                    provider_fixture_id=target_fixture_id,
                    provider_club_id=str(team_id),
                    club_name=team_name,
                    formation=formation,
                    coach_name=coach_name,
                    provider_player_id=str(p_id),
                    player_name=p_name,
                    jersey_number=_parse_int_clean(p_data.get("number")),
                    position=p_data.get("pos"),
                    grid=p_data.get("grid"),
                    is_starter=False,
                    is_captain=False,
                )
            )

    return lineups


def transform_api_football_statistics(
    payload: dict[str, Any], fixture_id: str | None = None
) -> list[NormalizedMatchStatistics]:
    """Transform API-Football /fixtures/statistics response into NormalizedMatchStatistics records.
    Crucially preserves explicit 0 vs missing/None."""
    target_fixture_id = fixture_id or str(payload.get("parameters", {}).get("fixture") or "")
    response = payload.get("response", [])
    statistics_list: list[NormalizedMatchStatistics] = []

    for item in response:
        if not isinstance(item, dict):
            continue

        team_data = item.get("team", {})
        team_id = team_data.get("id")
        if team_id is None:
            continue

        team_name = team_data.get("name")
        raw_stats_list = item.get("statistics", []) or []
        stats_dict: dict[str, Any] = {}

        for entry in raw_stats_list:
            if isinstance(entry, dict) and "type" in entry:
                key = str(entry["type"]).strip().lower()
                stats_dict[key] = entry.get("value")

        def _get_stat_int(k: str) -> int | None:
            if k not in stats_dict:
                return None
            val = stats_dict[k]
            if val is None:
                return None
            return _parse_int_clean(val)

        def _get_stat_float(k: str) -> float | None:
            if k not in stats_dict:
                return None
            val = stats_dict[k]
            if val is None:
                return None
            if isinstance(val, str) and "%" in val:
                val = val.replace("%", "").strip()
            return _parse_float_clean(val)

        stat = NormalizedMatchStatistics(
            provider_fixture_id=target_fixture_id,
            provider_club_id=str(team_id),
            club_name=team_name,
            possession_pct=_get_stat_float("ball possession"),
            shots_total=_get_stat_int("total shots"),
            shots_on_target=_get_stat_int("shots on goal"),
            shots_off_target=_get_stat_int("shots off goal"),
            blocked_shots=_get_stat_int("blocked shots"),
            shots_inside_box=_get_stat_int("shots insidebox"),
            shots_outside_box=_get_stat_int("shots outsidebox"),
            fouls=_get_stat_int("fouls"),
            corners=_get_stat_int("corner kicks"),
            offsides=_get_stat_int("offsides"),
            yellow_cards=_get_stat_int("yellow cards"),
            red_cards=_get_stat_int("red cards"),
            saves=_get_stat_int("goalkeeper saves"),
            passes_total=_get_stat_int("total passes"),
            passes_accurate=_get_stat_int("passes accurate"),
            pass_accuracy_pct=_get_stat_float("passes %"),
            expected_goals=_get_stat_float("expected_goals"),
            free_kicks=_get_stat_int("free kicks"),
            raw_stats=stats_dict,
        )
        statistics_list.append(stat)

    return statistics_list


def _parse_rating_clean(val: Any, minutes: int | None = None) -> float | None:
    if val is None:
        return None
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str or val_str.lower() in ("-", "none", "null", "n/a"):
            return None
    try:
        f_val = float(val)
        if f_val == 0.0 and (minutes == 0 or minutes is None):
            return None
        return f_val
    except (ValueError, TypeError):
        return None


def _parse_percentage_clean(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("%", "").strip()
    return _parse_float_clean(s)


def transform_api_football_player_statistics(
    payload: dict[str, Any], fixture_id: str | None = None
) -> list[NormalizedPlayerMatchStats]:
    """Pure deterministic transformer converting API-Football /fixtures/players response
    into NormalizedPlayerMatchStats records.
    Strictly preserves explicit 0 vs None across all metrics.
    """
    target_fixture_id = fixture_id or str(payload.get("parameters", {}).get("fixture") or "")
    response = payload.get("response", [])
    player_stats_list: list[NormalizedPlayerMatchStats] = []

    for team_entry in response:
        if not isinstance(team_entry, dict):
            continue

        team_info = team_entry.get("team", {})
        team_id = team_info.get("id")
        if team_id is None:
            continue
        team_name = team_info.get("name")

        players = team_entry.get("players", []) or []
        for p_item in players:
            if not isinstance(p_item, dict):
                continue

            player_info = p_item.get("player", {})
            p_id = player_info.get("id")
            if p_id is None:
                continue
            player_name = player_info.get("name") or "Unknown Player"
            photo_url = player_info.get("photo")

            stats_arr = p_item.get("statistics", []) or []
            stat = stats_arr[0] if stats_arr and isinstance(stats_arr[0], dict) else {}

            games = stat.get("games", {}) or {}
            shots = stat.get("shots", {}) or {}
            goals = stat.get("goals", {}) or {}
            passes = stat.get("passes", {}) or {}
            tackles = stat.get("tackles", {}) or {}
            duels = stat.get("duels", {}) or {}
            dribbles = stat.get("dribbles", {}) or {}
            fouls = stat.get("fouls", {}) or {}
            cards = stat.get("cards", {}) or {}
            penalty = stat.get("penalty", {}) or {}

            raw_minutes = games.get("minutes")
            minutes = _parse_int_clean(raw_minutes)

            raw_rating = games.get("rating")
            rating = _parse_rating_clean(raw_rating, minutes=minutes)

            position = games.get("position")
            jersey_number = _parse_int_clean(games.get("number"))
            is_captain = bool(games.get("captain", False))

            raw_sub = games.get("substitute")
            if raw_sub is True:
                is_starter = False
                is_substitute = True
            elif raw_sub is False:
                is_starter = True
                is_substitute = False
            else:
                is_starter = None
                is_substitute = None

            # Goalkeeper clean sheet calculation
            conceded = _parse_int_clean(goals.get("conceded"))
            saves = _parse_int_clean(goals.get("saves"))
            clean_sheet: bool | None = None
            if position == "G":
                if conceded == 0 and minutes is not None and minutes > 0:
                    clean_sheet = True
                elif conceded is not None and conceded > 0:
                    clean_sheet = False

            # Penalties: handle both 'commited' (API-Football spelling) and 'committed'
            pen_committed = penalty.get("commited")
            if pen_committed is None:
                pen_committed = penalty.get("committed")

            norm_record = NormalizedPlayerMatchStats(
                provider_fixture_id=target_fixture_id,
                provider_club_id=str(team_id),
                club_name=team_name,
                provider_player_id=str(p_id),
                player_name=player_name,
                photo_url=photo_url,
                is_starter=is_starter,
                is_substitute=is_substitute,
                is_captain=is_captain,
                position=position,
                jersey_number=jersey_number,
                grid=None,
                minutes=minutes,
                rating=rating,
                goals=_parse_int_clean(goals.get("total")),
                assists=_parse_int_clean(goals.get("assists")),
                shots_total=_parse_int_clean(shots.get("total")),
                shots_on_target=_parse_int_clean(shots.get("on")),
                offsides=_parse_int_clean(stat.get("offsides")),
                passes_total=_parse_int_clean(passes.get("total")),
                passes_key=_parse_int_clean(passes.get("key")),
                pass_accuracy=_parse_percentage_clean(passes.get("accuracy")),
                tackles_total=_parse_int_clean(tackles.get("total")),
                blocks=_parse_int_clean(tackles.get("blocks")),
                interceptions=_parse_int_clean(tackles.get("interceptions")),
                duels_total=_parse_int_clean(duels.get("total")),
                duels_won=_parse_int_clean(duels.get("won")),
                dribbles_attempts=_parse_int_clean(dribbles.get("attempts")),
                dribbles_success=_parse_int_clean(dribbles.get("success")),
                dribbles_past=_parse_int_clean(dribbles.get("past")),
                fouls_drawn=_parse_int_clean(fouls.get("drawn")),
                fouls_committed=_parse_int_clean(fouls.get("committed")),
                yellow_cards=_parse_int_clean(cards.get("yellow")),
                red_cards=_parse_int_clean(cards.get("red")),
                penalties_won=_parse_int_clean(penalty.get("won")),
                penalties_committed=_parse_int_clean(pen_committed),
                penalties_scored=_parse_int_clean(penalty.get("scored")),
                penalties_missed=_parse_int_clean(penalty.get("missed")),
                penalties_saved=_parse_int_clean(penalty.get("saved")),
                saves=saves,
                goals_conceded=conceded,
                clean_sheet=clean_sheet,
                raw_stats=stat,
            )
            player_stats_list.append(norm_record)

    return player_stats_list

