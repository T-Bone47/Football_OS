"""Unit tests for pure feature calculation engine (Phase 2 Slice 1).
Tests mathematical correctness, division by zero prevention, small sample handling,
outfield vs goalkeeper isolation, null vs zero preservation, and feature registry.
"""
from __future__ import annotations

from datetime import datetime, timezone
import pytest

from app.features.calculator import (
    calculate_opponent_strength_baseline,
    calculate_player_features,
    calculate_rest_days,
    calculate_team_features,
    compute_player_window_features,
    compute_team_window_features,
    safe_avg,
    safe_per_90,
    safe_rate,
    safe_sum,
)
from app.features.registry import FEATURE_REGISTRY, list_features


def test_safe_per_90():
    # Division by zero avoidance
    assert safe_per_90(5, 0) is None
    assert safe_per_90(5, -10) is None
    assert safe_per_90(5, None) is None

    # Null preservation
    assert safe_per_90(None, 90) is None
    assert safe_per_90(None, 0) is None

    # Zero preservation
    assert safe_per_90(0, 90) == 0.0
    assert safe_per_90(0, 45) == 0.0

    # Normal calculations
    assert safe_per_90(1, 90) == 1.0
    assert safe_per_90(2, 90) == 2.0
    assert safe_per_90(1, 45) == 2.0
    assert safe_per_90(10, 900) == 1.0


def test_safe_rate():
    assert safe_rate(5, 0) is None
    assert safe_rate(5, -1) is None
    assert safe_rate(None, 10) is None
    assert safe_rate(0, 10) == 0.0
    assert safe_rate(3, 10) == 0.3
    assert safe_rate(5, 10) == 0.5


def test_safe_avg_and_sum():
    assert safe_avg([]) is None
    assert safe_avg([None, None]) is None
    assert safe_avg([1, 2, 3]) == 2.0
    assert safe_avg([1, None, 3]) == 2.0

    assert safe_sum([]) is None
    assert safe_sum([None, None]) is None
    assert safe_sum([1, 2, 3]) == 6
    assert safe_sum([0, 0]) == 0
    assert safe_sum([0, None]) == 0


def test_calculate_rest_days():
    t1 = datetime(2026, 3, 1, 15, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 4, 15, 0, 0, tzinfo=timezone.utc)
    t_same = datetime(2026, 3, 1, 15, 0, 0, tzinfo=timezone.utc)

    # Normal 3 days
    assert calculate_rest_days(t2, t1) == 3.0

    # Same moment
    assert calculate_rest_days(t1, t_same) == 0.0

    # Missing previous match
    assert calculate_rest_days(t1, None) is None

    # Future match cannot be previous match
    assert calculate_rest_days(t1, t2) is None


def test_player_window_features_empty():
    feats = compute_player_window_features([], position="M", window_name="last_5")
    assert feats["sample_matches_last_5"] == 0
    assert feats["appearances_last_5"] == 0
    assert feats["minutes_last_5"] == 0
    assert feats["goals_last_5"] is None
    assert feats["goals_per_90_last_5"] is None
    assert feats["saves_last_5"] is None


def test_player_window_features_outfield_vs_goalkeeper():
    # Outfield player
    match_data = [
        {
            "minutes": 90,
            "is_starter": True,
            "goals": 1,
            "assists": 0,
            "shots_total": 3,
            "shots_on_target": 2,
            "passes_key": 2,
            "passes_total": 45,
            "pass_accuracy": 80.0,
            "tackles_total": 2,
            "interceptions": 1,
            "blocks": 0,
            "duels_total": 8,
            "duels_won": 5,
            "dribbles_attempts": 4,
            "dribbles_success": 3,
            "yellow_cards": 0,
            "red_cards": 0,
            "fouls_committed": 1,
            "fouls_drawn": 2,
            "rating": 7.5,
            "saves": 0,
            "goals_conceded": 1,
            "clean_sheet": False,
        }
    ]

    outfield_feats = compute_player_window_features(match_data, position="F", window_name="last_3")
    assert outfield_feats["appearances_last_3"] == 1
    assert outfield_feats["minutes_last_3"] == 90
    assert outfield_feats["goals_last_3"] == 1
    assert outfield_feats["goals_per_90_last_3"] == 1.0
    assert outfield_feats["assists_per_90_last_3"] == 0.0
    assert outfield_feats["defensive_actions_per_90_last_3"] == 3.0  # 2 tackles + 1 int + 0 blocks
    assert outfield_feats["duel_win_rate_last_3"] == 0.625
    assert outfield_feats["dribble_success_rate_last_3"] == 0.75
    # Strict GK isolation: must be None for outfield
    assert outfield_feats["saves_last_3"] is None
    assert outfield_feats["goals_conceded_last_3"] is None
    assert outfield_feats["clean_sheets_last_3"] is None
    assert outfield_feats["save_rate_last_3"] is None

    # Goalkeeper
    gk_data = [
        {
            "minutes": 90,
            "is_starter": True,
            "saves": 4,
            "goals_conceded": 1,
            "clean_sheet": False,
            "rating": 7.0,
        },
        {
            "minutes": 90,
            "is_starter": True,
            "saves": 3,
            "goals_conceded": 0,
            "clean_sheet": True,
            "rating": 8.0,
        },
    ]
    gk_feats = compute_player_window_features(gk_data, position="G", window_name="last_3")
    assert gk_feats["appearances_last_3"] == 2
    assert gk_feats["saves_last_3"] == 7
    assert gk_feats["goals_conceded_last_3"] == 1
    assert gk_feats["clean_sheets_last_3"] == 1
    assert gk_feats["save_rate_last_3"] == round(7 / 8, 4)


def test_team_window_features():
    team_data = [
        {
            "result": "WIN",
            "goals_for": 2,
            "goals_against": 0,
            "possession": 60.0,
            "shots_total": 12,
            "shots_on_target": 6,
            "pass_accuracy": 85.0,
            "fouls": 10,
            "corner_kicks": 5,
        },
        {
            "result": "DRAW",
            "goals_for": 1,
            "goals_against": 1,
            "possession": 50.0,
            "shots_total": 8,
            "shots_on_target": 3,
            "pass_accuracy": 80.0,
            "fouls": 12,
            "corner_kicks": 4,
        },
        {
            "result": "LOSS",
            "goals_for": 0,
            "goals_against": 2,
            "possession": 45.0,
            "shots_total": 6,
            "shots_on_target": 1,
            "pass_accuracy": 75.0,
            "fouls": 14,
            "corner_kicks": 2,
        },
    ]
    feats = compute_team_window_features(team_data, window_name="last_3")
    assert feats["matches_played_last_3"] == 3
    assert feats["wins_last_3"] == 1
    assert feats["draws_last_3"] == 1
    assert feats["losses_last_3"] == 1
    assert feats["points_last_3"] == 4
    assert feats["points_per_match_last_3"] == round(4 / 3, 4)
    assert feats["goals_scored_last_3"] == 3
    assert feats["goals_conceded_last_3"] == 3
    assert feats["goal_difference_last_3"] == 0
    assert feats["clean_sheets_last_3"] == 1
    assert feats["clean_sheet_rate_last_3"] == round(1 / 3, 4)
    assert feats["possession_avg_last_3"] == round((60.0 + 50.0 + 45.0) / 3, 4)


def test_opponent_strength_baseline():
    opp_data = [
        {"match_date": datetime(2026, 3, 1, tzinfo=timezone.utc), "result": "WIN", "goals_for": 3, "goals_against": 1},
        {"match_date": datetime(2026, 3, 5, tzinfo=timezone.utc), "result": "WIN", "goals_for": 2, "goals_against": 0},
        {"match_date": datetime(2026, 3, 10, tzinfo=timezone.utc), "result": "DRAW", "goals_for": 1, "goals_against": 1},
        # Future match after as_of
        {"match_date": datetime(2026, 3, 20, tzinfo=timezone.utc), "result": "WIN", "goals_for": 10, "goals_against": 0},
    ]
    as_of = datetime(2026, 3, 15, tzinfo=timezone.utc)
    strength = calculate_opponent_strength_baseline(opp_data, as_of)

    # Matches strictly before 2026-03-15 are 3 matches (Pts: 3+3+1 = 7 / 3; Goals: (3+2+1) - (1+0+1) = 6 - 2 = 4 / 3)
    assert strength["opponent_strength_baseline_points_per_match"] == round(7 / 3, 4)
    assert strength["opponent_strength_baseline_goal_diff"] == round(4 / 3, 4)
    assert strength["opponent_strength_goals_scored_per_match"] == round(6 / 3, 4)
    assert strength["opponent_strength_goals_conceded_per_match"] == round(2 / 3, 4)


def test_feature_registry():
    assert len(FEATURE_REGISTRY) > 200
    player_feats = list_features(feature_set="player_match_v1")
    assert len(player_feats) > 100

    team_feats = list_features(feature_set="team_match_v1")
    assert len(team_feats) > 80

    for f in FEATURE_REGISTRY.values():
        assert f.leakage_policy == "pre-match-strict"
        assert f.version == "1.0.0"
        assert f.name
        assert f.description
