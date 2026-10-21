"""Unit tests for the season-window role feature builder."""
from __future__ import annotations

from types import SimpleNamespace

from app.roles.profiler import RoleProfiler
from app.roles.registry import PositionGroup
from app.roles.season_features import build_season_role_features


def _row(**raw):
    return SimpleNamespace(
        minutes=raw.pop("minutes", 0),
        appearances=raw.pop("appearances", 0),
        goals=raw.pop("goals", 0),
        assists=raw.pop("assists", 0),
        conceded=raw.pop("conceded", 0),
        raw_stats=raw,
    )


def test_season_aggregation_sums_counts_and_recomputes_rates():
    rows = [
        _row(
            minutes=900,
            appearances=10,
            goals=5,
            assists=2,
            passes={"total": 450, "key": 9, "accuracy": 80},
            tackles={"total": 20, "interceptions": 4, "blocks": 2},
            duels={"won": 30, "total": 50},
            dribbles={"success": 6, "attempts": 10},
            shots={"total": 20, "on": 10},
            fouls={"committed": 8},
            cards={"yellow": 2},
        ),
        _row(
            minutes=100,
            appearances=2,
            goals=1,
            assists=0,
            passes={"total": 100, "key": 1, "accuracy": 60},
            tackles={"total": 4, "interceptions": 0, "blocks": 1},
            duels={"won": 5, "total": 10},
            dribbles={"success": 2, "attempts": 5},
            shots={"total": 5, "on": 2},
            fouls={"committed": 2},
            cards={"yellow": 0},
        ),
    ]

    features = build_season_role_features(rows)

    assert features["minutes_season"] == 1000
    assert features["sample_matches_season"] == 12
    assert features["goals_season"] == 6
    assert features["assists_season"] == 2
    assert features["passes_total_season"] == 550
    assert features["passes_per_90_season"] == 49.5
    # Provider accuracy weighted by passes attempted: (80*450 + 60*100) / 550
    assert features["pass_accuracy_avg_season"] == 76.3636
    assert features["shots_on_target_season"] == 12
    assert features["defensive_actions_per_90_season"] == 2.79
    assert features["duel_win_rate_season"] == 0.5833
    assert features["dribble_success_rate_season"] == 0.5333
    assert features["yellow_cards_season"] == 2
    assert features["goals_per_90_season"] == 0.54


def test_missing_fields_stay_absent_instead_of_zero():
    features = build_season_role_features([_row(minutes=500, appearances=5)])
    assert features["minutes_season"] == 500
    assert features["pass_accuracy_avg_season"] is None
    assert features["save_rate_season"] is None
    assert "clean_sheets_season" not in features


def test_profiler_reads_the_requested_window():
    features = build_season_role_features(
        [
            _row(
                minutes=900,
                appearances=10,
                passes={"total": 450, "key": 9, "accuracy": 80},
                tackles={"total": 20, "interceptions": 4, "blocks": 2},
                duels={"won": 30, "total": 50},
                dribbles={"success": 6, "attempts": 10},
                shots={"total": 20, "on": 10},
            )
        ]
    )
    profiler = RoleProfiler()

    season = profiler.extract_role_features(features, PositionGroup.MID, window="season")
    match = profiler.extract_role_features({}, PositionGroup.MID, window="last_5")

    assert season["passes_per_90"] == 45.0
    assert season["tackles_per_90"] == 2.0
    # The empty match window falls back to registry defaults, not season values.
    assert match["passes_per_90"] == 0.0
