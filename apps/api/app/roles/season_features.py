"""Season-window role features built from persisted PlayerSeasonStats.

The role profiler's feature registry names its inputs with a window suffix
(``*_last_5``). When a club has no per-match rows yet — the default state of a
new canonical index — the match window is empty and every profile is
``INSUFFICIENT_SAMPLE``. Season-to-date aggregates are real, stored provider
data and can fill the same per-90 feature semantics under an explicit
``season`` window; they are never presented as a last-5 window.

Missing provider fields stay missing (not zero): the profiler applies its
documented default for an absent key.
"""
from __future__ import annotations

from typing import Any, Iterable

WINDOW = "season"


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    parsed = _num(value)
    return int(parsed) if parsed is not None else None


def _per90(value: float | None, minutes: int) -> float | None:
    if value is None or minutes <= 0:
        return None
    return round(value * 90.0 / minutes, 4)


def _rate(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def build_season_role_features(rows: Iterable[Any]) -> dict[str, Any]:
    """Aggregate season stats rows into ``*_season`` role features.

    ``rows`` are ``PlayerSeasonStats``-shaped objects (attributes plus a
    ``raw_stats`` dict). Counts are summed across competitions in the same
    season; per-90 values are recomputed from the summed totals so a player
    with a league and a cup row is not double-counted as two per-90 samples.
    """
    minutes = 0
    appearances = 0
    goals = 0
    assists = 0
    conceded = 0

    passes_total = 0
    passes_accuracy_weighted = 0.0
    passes_accuracy_minutes = 0
    key_passes = 0
    tackles_total = 0
    interceptions = 0
    blocks = 0
    duels_total = 0
    duels_won = 0
    dribbles_attempts = 0
    dribbles_success = 0
    fouls_committed = 0
    yellow_cards = 0
    shots_total = 0
    shots_on = 0
    saves = 0

    for row in rows:
        rmin = _int(getattr(row, "minutes", None)) or 0
        minutes += rmin
        appearances += _int(getattr(row, "appearances", None)) or 0
        goals += _int(getattr(row, "goals", None)) or 0
        assists += _int(getattr(row, "assists", None)) or 0
        conceded += _int(getattr(row, "conceded", None)) or 0

        raw = getattr(row, "raw_stats", None) or {}
        passes = raw.get("passes") or {}
        tackles = raw.get("tackles") or {}
        duels = raw.get("duels") or {}
        dribbles = raw.get("dribbles") or {}
        fouls = raw.get("fouls") or {}
        cards = raw.get("cards") or {}
        shots = raw.get("shots") or {}
        goals_block = raw.get("goals") or {}

        total_passes = _int(passes.get("total"))
        if total_passes is not None:
            passes_total += total_passes
            accuracy = _num(passes.get("accuracy"))
            if accuracy is not None:
                # Weight the provider's accuracy by passes attempted.
                passes_accuracy_weighted += accuracy * total_passes
                passes_accuracy_minutes += total_passes
        key_passes += _int(passes.get("key")) or 0
        tackles_total += _int(tackles.get("total")) or 0
        interceptions += _int(tackles.get("interceptions")) or 0
        blocks += _int(tackles.get("blocks")) or 0
        duels_total += _int(duels.get("total")) or 0
        duels_won += _int(duels.get("won")) or 0
        dribbles_attempts += _int(dribbles.get("attempts")) or 0
        dribbles_success += _int(dribbles.get("success")) or 0
        fouls_committed += _int(fouls.get("committed")) or 0
        yellow_cards += _int(cards.get("yellow")) or 0
        shots_total += _int(shots.get("total")) or 0
        shots_on += _int(shots.get("on")) or 0
        saves += _int(goals_block.get("saves")) or 0

    accuracy_avg = (
        round(passes_accuracy_weighted / passes_accuracy_minutes, 4)
        if passes_accuracy_minutes > 0
        else None
    )
    defensive_actions = tackles_total + interceptions + blocks

    features: dict[str, Any] = {
        "minutes_season": minutes,
        "sample_matches_season": appearances,
        "appearances_season": appearances,
        "start_rate_season": None,
        "goals_season": goals,
        "assists_season": assists,
        "goals_per_90_season": _per90(goals, minutes),
        "assists_per_90_season": _per90(assists, minutes),
        "shots_total_season": shots_total,
        "shots_per_90_season": _per90(shots_total, minutes),
        "shots_on_target_season": shots_on,
        "shots_on_target_per_90_season": _per90(shots_on, minutes),
        "passes_total_season": passes_total,
        "passes_per_90_season": _per90(passes_total, minutes),
        "pass_accuracy_avg_season": accuracy_avg,
        "passes_key_season": key_passes,
        "passes_key_per_90_season": _per90(key_passes, minutes),
        "tackles_total_season": tackles_total,
        "tackles_per_90_season": _per90(tackles_total, minutes),
        "interceptions_season": interceptions,
        "blocks_season": blocks,
        "defensive_actions_per_90_season": _per90(defensive_actions, minutes),
        "duels_total_season": duels_total,
        "duels_won_season": duels_won,
        "duel_win_rate_season": _rate(duels_won, duels_total),
        "dribbles_attempts_season": dribbles_attempts,
        "dribbles_success_season": dribbles_success,
        "dribble_success_rate_season": _rate(dribbles_success, dribbles_attempts),
        "fouls_committed_season": fouls_committed,
        "yellow_cards_season": yellow_cards,
        "saves_season": saves,
        "save_rate_season": _rate(saves, saves + conceded) if (saves or conceded) else None,
        "goals_conceded_season": conceded,
        # API-Football player season stats do not expose clean sheets; the key
        # stays absent so the profiler default applies instead of a fake zero.
    }
    return features
