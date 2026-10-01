"""Unit tests for Phase 3.2C: Contextual Performance Engine."""
from __future__ import annotations

from types import SimpleNamespace
import pytest

from app.intelligence.context import ContextualEngine, COMPETITION_TIER_WEIGHTS, DEFAULT_COMPETITION_TIER


def test_competition_tier_evaluation():
    """Validates transparent competition tier multipliers."""
    engine = ContextualEngine()

    # Big 5 + UCL
    assert engine.evaluate_competition_strength("Premier League") == 1.00
    assert engine.evaluate_competition_strength("La Liga") == 1.00
    assert engine.evaluate_competition_strength("Serie A") == 1.00
    assert engine.evaluate_competition_strength("UEFA Champions League") == 1.05

    # Secondary competitions
    assert engine.evaluate_competition_strength("Championship") == 0.85
    assert engine.evaluate_competition_strength("Eredivisie") == 0.85
    assert engine.evaluate_competition_strength("Serie B") == 0.80

    # Unlisted or unknown competition gets default
    assert engine.evaluate_competition_strength("Regional League X") == DEFAULT_COMPETITION_TIER
    assert engine.evaluate_competition_strength(None) == DEFAULT_COMPETITION_TIER


def test_player_context_empty():
    """Empty stats list returns default baseline without errors."""
    engine = ContextualEngine()
    res = engine.evaluate_player_context(stats_list=[])

    assert res["competition_tier"] == DEFAULT_COMPETITION_TIER
    assert res["starter_ratio"] == 0.0
    assert res["minutes_per_match"] == 0.0
    assert "No match appearances recorded" in res["context_summary"]


def test_player_context_starter_and_exposure():
    """Evaluates starter ratio, minutes per match, and exposure share deterministically."""
    engine = ContextualEngine()
    # 4 matches: 3 starts (90 mins each), 1 sub (30 mins)
    stats = [
        SimpleNamespace(minutes=90, is_starter=True, is_substitute=False),
        SimpleNamespace(minutes=90, is_starter=True, is_substitute=False),
        SimpleNamespace(minutes=90, is_starter=True, is_substitute=False),
        SimpleNamespace(minutes=30, is_starter=False, is_substitute=True),
    ]

    res = engine.evaluate_player_context(
        stats_list=stats,
        competition_name="Premier League",
    )

    assert res["competition_tier"] == 1.00
    assert res["starter_ratio"] == 0.75  # 3/4
    assert res["substitute_ratio"] == 0.25  # 1/4
    assert res["minutes_per_match"] == 75.0  # 300 / 4
    assert res["exposure_share"] == pytest.approx(300 / 360, rel=1e-2)
    assert 0.70 <= res["context_multiplier"] <= 1.10
