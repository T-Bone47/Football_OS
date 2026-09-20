"""Pure, deterministic feature calculation engine (Phase 2 Slice 1).
Contains zero database queries. All functions accept canonical entities/dictionaries
and compute strictly temporal, leakage-safe features.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence


def safe_per_90(metric: float | int | None, minutes: int | None) -> float | None:
    """Safe per-90 rate calculation.
    Formula: metric / minutes * 90
    Returns None if minutes <= 0 or metric is None.
    Preserves explicit 0.0 when metric == 0 and minutes > 0.
    """
    if minutes is None or minutes <= 0:
        return None
    if metric is None:
        return None
    if metric == 0:
        return 0.0
    return round((float(metric) / float(minutes)) * 90.0, 4)


def safe_rate(numerator: float | int | None, denominator: float | int | None) -> float | None:
    """Safe rate calculation with division by zero avoidance."""
    if denominator is None or denominator <= 0:
        return None
    if numerator is None:
        return None
    if numerator == 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def safe_avg(values: Sequence[float | int | None]) -> float | None:
    """Safe arithmetic mean of non-null values."""
    valid = [float(v) for v in values if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 4)


def safe_sum(values: Sequence[float | int | None]) -> int | None:
    """Sum integers/floats, preserving None if all values are None."""
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return int(sum(valid))


def calculate_rest_days(
    current_match_date: datetime,
    previous_match_date: datetime | None,
) -> float | None:
    """Calculates days elapsed since previous match strictly before current match."""
    if previous_match_date is None:
        return None
    # Normalize timezones if needed
    t_curr = current_match_date.timestamp() if hasattr(current_match_date, "timestamp") else None
    t_prev = previous_match_date.timestamp() if hasattr(previous_match_date, "timestamp") else None
    if t_curr is None or t_prev is None:
        return None
    diff_seconds = t_curr - t_prev
    if diff_seconds < 0:
        # Future match cannot be previous match
        return None
    return round(diff_seconds / 86400.0, 2)


def compute_player_window_features(
    matches_stats: Sequence[Any],  # list of PlayerMatchStats objects or dicts
    position: str | None,
    window_name: str,
) -> dict[str, Any]:
    """Computes all player feature metrics for a single slice/window of matches."""
    sample_size = len(matches_stats)
    features: dict[str, Any] = {
        f"sample_matches_{window_name}": sample_size,
    }

    if sample_size == 0:
        # Empty window defaults
        features[f"appearances_{window_name}"] = 0
        features[f"starts_{window_name}"] = 0
        features[f"minutes_{window_name}"] = 0
        features[f"minutes_per_match_{window_name}"] = None
        features[f"starter_rate_{window_name}"] = None
        features[f"substitution_rate_{window_name}"] = None
        features[f"goals_{window_name}"] = None
        features[f"assists_{window_name}"] = None
        features[f"goals_per_90_{window_name}"] = None
        features[f"assists_per_90_{window_name}"] = None
        features[f"shots_total_{window_name}"] = None
        features[f"shots_per_90_{window_name}"] = None
        features[f"shots_on_target_per_90_{window_name}"] = None
        features[f"passes_key_{window_name}"] = None
        features[f"passes_key_per_90_{window_name}"] = None
        features[f"passes_total_{window_name}"] = None
        features[f"passes_per_90_{window_name}"] = None
        features[f"pass_accuracy_avg_{window_name}"] = None
        features[f"tackles_total_{window_name}"] = None
        features[f"tackles_per_90_{window_name}"] = None
        features[f"interceptions_{window_name}"] = None
        features[f"blocks_{window_name}"] = None
        features[f"defensive_actions_per_90_{window_name}"] = None
        features[f"duels_total_{window_name}"] = None
        features[f"duels_won_{window_name}"] = None
        features[f"duel_win_rate_{window_name}"] = None
        features[f"dribbles_attempts_{window_name}"] = None
        features[f"dribbles_success_{window_name}"] = None
        features[f"dribble_success_rate_{window_name}"] = None
        features[f"yellow_cards_{window_name}"] = None
        features[f"red_cards_{window_name}"] = None
        features[f"fouls_committed_{window_name}"] = None
        features[f"fouls_drawn_{window_name}"] = None
        features[f"saves_{window_name}"] = None
        features[f"goals_conceded_{window_name}"] = None
        features[f"clean_sheets_{window_name}"] = None
        features[f"save_rate_{window_name}"] = None
        features[f"rating_avg_{window_name}"] = None
        return features

    # Extract field values helper
    def get_val(item: Any, attr: str) -> Any:
        if isinstance(item, dict):
            return item.get(attr)
        return getattr(item, attr, None)

    minutes_list = [get_val(m, "minutes") or 0 for m in matches_stats]
    total_minutes = sum(minutes_list)
    appearances = sum(1 for m in matches_stats if (get_val(m, "minutes") or 0) > 0)
    starts = sum(1 for m in matches_stats if get_val(m, "is_starter") is True)
    subs = sum(1 for m in matches_stats if get_val(m, "is_substitute") is True)

    features[f"appearances_{window_name}"] = appearances
    features[f"starts_{window_name}"] = starts
    features[f"minutes_{window_name}"] = total_minutes
    features[f"minutes_per_match_{window_name}"] = (
        round(total_minutes / appearances, 2) if appearances > 0 else None
    )
    features[f"starter_rate_{window_name}"] = safe_rate(starts, appearances)
    features[f"substitution_rate_{window_name}"] = safe_rate(subs, appearances)

    # Scoring
    goals = safe_sum([get_val(m, "goals") for m in matches_stats])
    assists = safe_sum([get_val(m, "assists") for m in matches_stats])
    shots_total = safe_sum([get_val(m, "shots_total") for m in matches_stats])
    shots_on_target = safe_sum([get_val(m, "shots_on_target") for m in matches_stats])

    features[f"goals_{window_name}"] = goals
    features[f"assists_{window_name}"] = assists
    features[f"goals_per_90_{window_name}"] = safe_per_90(goals, total_minutes)
    features[f"assists_per_90_{window_name}"] = safe_per_90(assists, total_minutes)
    features[f"shots_total_{window_name}"] = shots_total
    features[f"shots_per_90_{window_name}"] = safe_per_90(shots_total, total_minutes)
    features[f"shots_on_target_per_90_{window_name}"] = safe_per_90(shots_on_target, total_minutes)

    # Creation
    passes_key = safe_sum([get_val(m, "passes_key") for m in matches_stats])
    features[f"passes_key_{window_name}"] = passes_key
    features[f"passes_key_per_90_{window_name}"] = safe_per_90(passes_key, total_minutes)

    # Passing
    passes_total = safe_sum([get_val(m, "passes_total") for m in matches_stats])
    pass_accuracies = [get_val(m, "pass_accuracy") for m in matches_stats]
    features[f"passes_total_{window_name}"] = passes_total
    features[f"passes_per_90_{window_name}"] = safe_per_90(passes_total, total_minutes)
    features[f"pass_accuracy_avg_{window_name}"] = safe_avg(pass_accuracies)

    # Defending
    tackles_total = safe_sum([get_val(m, "tackles_total") for m in matches_stats])
    interceptions = safe_sum([get_val(m, "interceptions") for m in matches_stats])
    blocks = safe_sum([get_val(m, "blocks") for m in matches_stats])

    features[f"tackles_total_{window_name}"] = tackles_total
    features[f"tackles_per_90_{window_name}"] = safe_per_90(tackles_total, total_minutes)
    features[f"interceptions_{window_name}"] = interceptions
    features[f"blocks_{window_name}"] = blocks

    # Combined defensive actions
    def_actions_sum = None
    if any(x is not None for x in [tackles_total, interceptions, blocks]):
        def_actions_sum = (tackles_total or 0) + (interceptions or 0) + (blocks or 0)
    features[f"defensive_actions_per_90_{window_name}"] = safe_per_90(def_actions_sum, total_minutes)

    # Duels
    duels_total = safe_sum([get_val(m, "duels_total") for m in matches_stats])
    duels_won = safe_sum([get_val(m, "duels_won") for m in matches_stats])
    features[f"duels_total_{window_name}"] = duels_total
    features[f"duels_won_{window_name}"] = duels_won
    features[f"duel_win_rate_{window_name}"] = safe_rate(duels_won, duels_total)

    # Dribbling
    dribbles_attempts = safe_sum([get_val(m, "dribbles_attempts") for m in matches_stats])
    dribbles_success = safe_sum([get_val(m, "dribbles_success") for m in matches_stats])
    features[f"dribbles_attempts_{window_name}"] = dribbles_attempts
    features[f"dribbles_success_{window_name}"] = dribbles_success
    features[f"dribble_success_rate_{window_name}"] = safe_rate(dribbles_success, dribbles_attempts)

    # Discipline
    features[f"yellow_cards_{window_name}"] = safe_sum([get_val(m, "yellow_cards") for m in matches_stats])
    features[f"red_cards_{window_name}"] = safe_sum([get_val(m, "red_cards") for m in matches_stats])
    features[f"fouls_committed_{window_name}"] = safe_sum([get_val(m, "fouls_committed") for m in matches_stats])
    features[f"fouls_drawn_{window_name}"] = safe_sum([get_val(m, "fouls_drawn") for m in matches_stats])

    # Rating
    ratings = [get_val(m, "rating") for m in matches_stats]
    features[f"rating_avg_{window_name}"] = safe_avg(ratings)

    # Goalkeeping (Strict isolation: G only)
    is_gk = (position or "").upper() == "G"
    if is_gk:
        saves = safe_sum([get_val(m, "saves") for m in matches_stats])
        goals_conceded = safe_sum([get_val(m, "goals_conceded") for m in matches_stats])
        clean_sheets_cnt = sum(1 for m in matches_stats if get_val(m, "clean_sheet") is True)

        features[f"saves_{window_name}"] = saves
        features[f"goals_conceded_{window_name}"] = goals_conceded
        features[f"clean_sheets_{window_name}"] = clean_sheets_cnt
        if saves is not None and goals_conceded is not None and (saves + goals_conceded) > 0:
            features[f"save_rate_{window_name}"] = round(float(saves) / float(saves + goals_conceded), 4)
        else:
            features[f"save_rate_{window_name}"] = None
    else:
        features[f"saves_{window_name}"] = None
        features[f"goals_conceded_{window_name}"] = None
        features[f"clean_sheets_{window_name}"] = None
        features[f"save_rate_{window_name}"] = None

    return features


def calculate_player_features(
    history: Sequence[Any],  # PlayerMatchStats sorted chronologically ascending
    as_of: datetime,
    position: str | None,
    season_id: Any | None = None,
) -> dict[str, Any]:
    """Calculates player feature snapshot strictly before as_of across all windows."""
    # Filter strictly before as_of
    def get_date(item: Any) -> datetime | None:
        if isinstance(item, dict):
            return item.get("match_date")
        match = getattr(item, "match", None)
        if match is not None:
            return getattr(match, "date", None)
        return getattr(item, "match_date", None)

    as_of_ts = as_of.timestamp() if hasattr(as_of, "timestamp") else 0
    valid_history = []
    for item in history:
        m_date = get_date(item)
        if m_date is not None and m_date.timestamp() < as_of_ts:
            valid_history.append(item)

    # Sort strictly by match date ascending
    valid_history.sort(key=lambda x: get_date(x).timestamp() if get_date(x) else 0)

    # Windows
    windows = {
        "last_3": valid_history[-3:],
        "last_5": valid_history[-5:],
        "last_10": valid_history[-10:],
    }

    # Season-to-date window
    if season_id is not None:
        def get_season(item: Any) -> Any:
            if isinstance(item, dict):
                return item.get("season_id")
            match = getattr(item, "match", None)
            if match is not None:
                return getattr(match, "season_id", None)
            return getattr(item, "season_id", None)
        season_history = [item for item in valid_history if get_season(item) == season_id]
        windows["season_to_date"] = season_history
    else:
        windows["season_to_date"] = valid_history

    combined_features: dict[str, Any] = {}
    for win_name, win_items in windows.items():
        win_feats = compute_player_window_features(win_items, position, win_name)
        combined_features.update(win_feats)

    return combined_features


def compute_team_window_features(
    matches_teams: Sequence[Any],  # list of MatchTeam or dicts
    window_name: str,
) -> dict[str, Any]:
    """Computes team feature metrics for a single slice/window of matches."""
    sample_size = len(matches_teams)
    features: dict[str, Any] = {
        f"matches_played_{window_name}": sample_size,
    }

    if sample_size == 0:
        features[f"wins_{window_name}"] = 0
        features[f"draws_{window_name}"] = 0
        features[f"losses_{window_name}"] = 0
        features[f"points_{window_name}"] = 0
        features[f"points_per_match_{window_name}"] = None
        features[f"win_rate_{window_name}"] = None
        features[f"goals_scored_{window_name}"] = 0
        features[f"goals_conceded_{window_name}"] = 0
        features[f"goal_difference_{window_name}"] = 0
        features[f"goals_scored_per_match_{window_name}"] = None
        features[f"goals_conceded_per_match_{window_name}"] = None
        features[f"clean_sheets_{window_name}"] = 0
        features[f"clean_sheet_rate_{window_name}"] = None
        features[f"possession_avg_{window_name}"] = None
        features[f"shots_avg_{window_name}"] = None
        features[f"shots_on_target_avg_{window_name}"] = None
        features[f"pass_accuracy_avg_{window_name}"] = None
        features[f"fouls_avg_{window_name}"] = None
        features[f"corners_avg_{window_name}"] = None
        return features

    def get_val(item: Any, attr: str) -> Any:
        if isinstance(item, dict):
            return item.get(attr)
        return getattr(item, attr, None)

    wins = sum(1 for m in matches_teams if (get_val(m, "result") or "").upper() == "WIN")
    draws = sum(1 for m in matches_teams if (get_val(m, "result") or "").upper() == "DRAW")
    losses = sum(1 for m in matches_teams if (get_val(m, "result") or "").upper() == "LOSS")
    points = wins * 3 + draws * 1

    goals_scored = sum(get_val(m, "goals_for") or 0 for m in matches_teams)
    goals_conceded = sum(get_val(m, "goals_against") or 0 for m in matches_teams)
    goal_difference = goals_scored - goals_conceded
    clean_sheets = sum(1 for m in matches_teams if (get_val(m, "goals_against") or 0) == 0)

    features[f"wins_{window_name}"] = wins
    features[f"draws_{window_name}"] = draws
    features[f"losses_{window_name}"] = losses
    features[f"points_{window_name}"] = points
    features[f"points_per_match_{window_name}"] = round(points / sample_size, 4)
    features[f"win_rate_{window_name}"] = round(wins / sample_size, 4)
    features[f"goals_scored_{window_name}"] = goals_scored
    features[f"goals_conceded_{window_name}"] = goals_conceded
    features[f"goal_difference_{window_name}"] = goal_difference
    features[f"goals_scored_per_match_{window_name}"] = round(goals_scored / sample_size, 4)
    features[f"goals_conceded_per_match_{window_name}"] = round(goals_conceded / sample_size, 4)
    features[f"clean_sheets_{window_name}"] = clean_sheets
    features[f"clean_sheet_rate_{window_name}"] = round(clean_sheets / sample_size, 4)

    # Match performance statistics (from attached MatchStatistics or dicts)
    def get_stat(item: Any, attr: str) -> Any:
        if isinstance(item, dict):
            return item.get(attr)
        stats = getattr(item, "statistics", None)
        if stats is not None:
            return getattr(stats, attr, None)
        return getattr(item, attr, None)

    possessions = [get_stat(m, "possession") for m in matches_teams]
    shots_totals = [get_stat(m, "shots_total") for m in matches_teams]
    shots_targets = [get_stat(m, "shots_on_target") for m in matches_teams]
    pass_accs = [get_stat(m, "pass_accuracy") for m in matches_teams]
    fouls = [get_stat(m, "fouls") for m in matches_teams]
    corners = [get_stat(m, "corner_kicks") for m in matches_teams]

    features[f"possession_avg_{window_name}"] = safe_avg(possessions)
    features[f"shots_avg_{window_name}"] = safe_avg(shots_totals)
    features[f"shots_on_target_avg_{window_name}"] = safe_avg(shots_targets)
    features[f"pass_accuracy_avg_{window_name}"] = safe_avg(pass_accs)
    features[f"fouls_avg_{window_name}"] = safe_avg(fouls)
    features[f"corners_avg_{window_name}"] = safe_avg(corners)

    return features


def calculate_team_features(
    history: Sequence[Any],  # MatchTeam records sorted chronologically ascending
    as_of: datetime,
    season_id: Any | None = None,
) -> dict[str, Any]:
    """Calculates team features strictly before as_of across all windows and home/away."""
    def get_date(item: Any) -> datetime | None:
        if isinstance(item, dict):
            return item.get("match_date")
        match = getattr(item, "match", None)
        if match is not None:
            return getattr(match, "date", None)
        return getattr(item, "match_date", None)

    as_of_ts = as_of.timestamp() if hasattr(as_of, "timestamp") else 0
    valid_history = []
    for item in history:
        m_date = get_date(item)
        if m_date is not None and m_date.timestamp() < as_of_ts:
            valid_history.append(item)

    valid_history.sort(key=lambda x: get_date(x).timestamp() if get_date(x) else 0)

    windows = {
        "last_3": valid_history[-3:],
        "last_5": valid_history[-5:],
        "last_10": valid_history[-10:],
    }

    if season_id is not None:
        def get_season(item: Any) -> Any:
            if isinstance(item, dict):
                return item.get("season_id")
            match = getattr(item, "match", None)
            if match is not None:
                return getattr(match, "season_id", None)
            return getattr(item, "season_id", None)
        windows["season_to_date"] = [item for item in valid_history if get_season(item) == season_id]
    else:
        windows["season_to_date"] = valid_history

    combined_features: dict[str, Any] = {}
    for win_name, win_items in windows.items():
        win_feats = compute_team_window_features(win_items, win_name)
        combined_features.update(win_feats)

    # Home / Away subsets (last 5)
    def is_home(item: Any) -> bool:
        if isinstance(item, dict):
            return bool(item.get("is_home"))
        return bool(getattr(item, "is_home", False))

    home_games = [item for item in valid_history if is_home(item)][-5:]
    away_games = [item for item in valid_history if not is_home(item)][-5:]

    def get_val(item: Any, attr: str) -> Any:
        if isinstance(item, dict):
            return item.get(attr)
        return getattr(item, attr, None)

    def calc_pts(games: list[Any]) -> float | None:
        if not games:
            return None
        total_pts = sum(
            3 if (get_val(g, "result") or "").upper() == "WIN"
            else 1 if (get_val(g, "result") or "").upper() == "DRAW"
            else 0
            for g in games
        )
        return round(total_pts / len(games), 4)

    combined_features["home_points_last_5"] = calc_pts(home_games)
    combined_features["away_points_last_5"] = calc_pts(away_games)

    combined_features["home_goals_scored_last_5"] = (
        round(sum(get_val(g, "goals_for") or 0 for g in home_games) / len(home_games), 4)
        if home_games else None
    )
    combined_features["away_goals_scored_last_5"] = (
        round(sum(get_val(g, "goals_for") or 0 for g in away_games) / len(away_games), 4)
        if away_games else None
    )

    combined_features["home_goals_conceded_last_5"] = (
        round(sum(get_val(g, "goals_against") or 0 for g in home_games) / len(home_games), 4)
        if home_games else None
    )
    combined_features["away_goals_conceded_last_5"] = (
        round(sum(get_val(g, "goals_against") or 0 for g in away_games) / len(away_games), 4)
        if away_games else None
    )

    return combined_features


def calculate_opponent_strength_baseline(
    opponent_history: Sequence[Any],  # MatchTeam records of opponent
    as_of: datetime,
) -> dict[str, float | None]:
    """Calculates opponent strength baseline strictly before as_of.
    Formula:
    - points per match over last 5 matches before as_of
    - goal difference per match over last 5 matches before as_of
    - goals scored per match over last 5 matches before as_of
    - goals conceded per match over last 5 matches before as_of
    """
    def get_date(item: Any) -> datetime | None:
        if isinstance(item, dict):
            return item.get("match_date")
        match = getattr(item, "match", None)
        if match is not None:
            return getattr(match, "date", None)
        return getattr(item, "match_date", None)

    as_of_ts = as_of.timestamp() if hasattr(as_of, "timestamp") else 0
    valid = [item for item in opponent_history if get_date(item) and get_date(item).timestamp() < as_of_ts]
    valid.sort(key=lambda x: get_date(x).timestamp())
    last_5 = valid[-5:]

    if not last_5:
        return {
            "opponent_strength_baseline_points_per_match": None,
            "opponent_strength_baseline_goal_diff": None,
            "opponent_strength_goals_scored_per_match": None,
            "opponent_strength_goals_conceded_per_match": None,
        }

    def get_val(item: Any, attr: str) -> Any:
        if isinstance(item, dict):
            return item.get(attr)
        return getattr(item, attr, None)

    pts = sum(
        3 if (get_val(g, "result") or "").upper() == "WIN"
        else 1 if (get_val(g, "result") or "").upper() == "DRAW"
        else 0
        for g in last_5
    )
    scored = sum(get_val(g, "goals_for") or 0 for g in last_5)
    conceded = sum(get_val(g, "goals_against") or 0 for g in last_5)
    n = len(last_5)

    return {
        "opponent_strength_baseline_points_per_match": round(pts / n, 4),
        "opponent_strength_baseline_goal_diff": round((scored - conceded) / n, 4),
        "opponent_strength_goals_scored_per_match": round(scored / n, 4),
        "opponent_strength_goals_conceded_per_match": round(conceded / n, 4),
    }
