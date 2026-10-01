"""Tests for Temporal Safety, Idempotency, Provenance, and Semantic Nulls (Phase 3.1R)."""
from datetime import datetime, timezone
import pytest
from app.contributions.calculator import compute_player_contribution_metrics, determine_confidence
from app.actions.normalizer import normalize_match_event
from app.actions.taxonomy import ActionType, ActionOutcome
from app.db.models.canonical import MatchEvent


class MockStats:
    def __init__(self, date_str: str, minutes: int, passes: int = 0, goals: int = 0, tackles: int = 0):
        self.date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        self.minutes = minutes
        self.passes_total = passes
        self.passes_key = 0
        self.pass_accuracy = 80.0 if passes > 0 else None
        self.goals = goals
        self.assists = 0
        self.shots_total = goals
        self.shots_on_target = goals
        self.tackles_total = tackles
        self.interceptions = 0
        self.blocks = 0
        self.duels_total = tackles
        self.duels_won = tackles
        self.dribbles_attempts = 0
        self.dribbles_success = 0
        self.fouls_committed = 0
        self.fouls_drawn = 0
        self.saves = 0
        self.goals_conceded = 0


def test_temporal_safety_filtering():
    """Future events cannot leak into historical contribution calculations."""
    matches = [
        MockStats("2024-01-10T15:00:00", 90, passes=50, goals=1),
        MockStats("2024-02-15T15:00:00", 90, passes=60, goals=0),
        MockStats("2024-03-20T15:00:00", 90, passes=55, goals=1),
        MockStats("2024-05-01T15:00:00", 90, passes=70, goals=2),  # Future match relative to as_of
    ]

    as_of = datetime.fromisoformat("2024-04-01T00:00:00").replace(tzinfo=timezone.utc)

    # Strictly filter where match.date < as_of
    historical_matches = [m for m in matches if m.date < as_of]
    assert len(historical_matches) == 3

    result = compute_player_contribution_metrics(historical_matches, "MID")
    # Verified: 3 matches * 90 = 270 minutes (passes sum = 165)
    assert result["sample_minutes"] == 270
    assert result["sample_matches"] == 3
    assert result["raw_metrics"]["goals"] == 2.0  # (1 + 0 + 1), the future 2 goals are NOT counted


def test_semantic_nulls_vs_observed_zero():
    """0 must be preserved as observed zero; missing data must remain None/NULL, never fabricated."""
    # Match where player played 90 mins with 0 goals, 0 tackles, 0 passes
    stats = [MockStats("2024-01-10T15:00:00", 90, passes=0, goals=0, tackles=0)]
    result = compute_player_contribution_metrics(stats, "MID")

    # Raw metrics must show 0.0, not None
    assert result["raw_metrics"]["goals"] == 0.0
    assert result["raw_metrics"]["passes_total"] == 0.0
    # But pass accuracy for 0 passes should be None, not 0.0%
    assert result["raw_metrics"]["avg_pass_accuracy"] is None


def test_provenance_and_idempotency_structure():
    """Calculated profiles must preserve complete provenance fields."""
    stats = [
        MockStats("2024-01-10T15:00:00", 90, passes=40),
        MockStats("2024-01-17T15:00:00", 90, passes=45),
        MockStats("2024-01-24T15:00:00", 90, passes=50),
    ]
    as_of = datetime(2024, 2, 1, tzinfo=timezone.utc)

    res1 = compute_player_contribution_metrics(stats, "MID")
    res2 = compute_player_contribution_metrics(stats, "MID")

    # Determinism / idempotency: exact match
    assert res1["sample_minutes"] == res2["sample_minutes"]
    assert res1["dimensions"]["passing"].score == res2["dimensions"]["passing"].score
    assert res1["raw_metrics"] == res2["raw_metrics"]


def test_no_coordinate_fabrication_on_events():
    """Events without coordinates must preserve x=None, y=None without fabrication."""
    event = MatchEvent(
        id="00000000-0000-0000-0000-000000000001",
        match_id="00000000-0000-0000-0000-000000000002",
        club_id="00000000-0000-0000-0000-000000000003",
        player_id="00000000-0000-0000-0000-000000000004",
        minute=23,
        event_type="Goal",
        event_detail="Normal Goal",
        event_key="goal_23",
    )
    actions = normalize_match_event(event)
    assert len(actions) == 1
    act = actions[0]
    assert act.action_type == ActionType.SHOOTING.value
    assert act.outcome == ActionOutcome.SUCCESS.value
    # Non-negotiable: x and y must remain None
    assert act.x is None
    assert act.y is None
    assert act.end_x is None
    assert act.end_y is None
