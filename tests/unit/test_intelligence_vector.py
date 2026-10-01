"""Unit tests for Phase 3.2E & 3.2F: Player Contribution Vector & Player Intelligence Vector."""
from __future__ import annotations

import pytest

from app.intelligence.taxonomy import DataStatus, ConfidenceTier, INTELLIGENCE_FEATURE_SET_VERSION
from app.intelligence.vector import PlayerIntelligenceVectorCompiler


def test_compile_contribution_vector_insufficient_sample():
    """Contribution vector preserves null scores/percentiles when sample is below gate."""
    compiler = PlayerIntelligenceVectorCompiler()
    dims = {
        "passing": {"score": 0.75, "percentile": 82.0, "key_metrics": {"passes_total_p90": 55.0}},
        "defending": {"score": 0.60, "percentile": 65.0, "key_metrics": {"tackles_total_p90": 2.1}},
    }

    vec = compiler.compile_contribution_vector(
        dimensions=dims,
        raw_metrics={"minutes": 180},
        confidence=ConfidenceTier.INSUFFICIENT_SAMPLE.value,
        status=DataStatus.INSUFFICIENT_SAMPLE.value,
    )

    assert "passing" in vec
    assert "defending" in vec
    # Scores and percentiles must be None under insufficient sample
    assert vec["passing"]["score"] is None
    assert vec["passing"]["percentile"] is None
    assert vec["passing"]["status"] == DataStatus.INSUFFICIENT_SAMPLE.value


def test_compile_contribution_vector_evaluated():
    """Contribution vector retains verified scores and percentiles when sample is sufficient."""
    compiler = PlayerIntelligenceVectorCompiler()
    dims = {
        "passing": {"score": 0.85, "percentile": 90.0, "key_metrics": {"passes_total_p90": 62.0}},
        "creation": {"score": 0.78, "percentile": 84.0, "key_metrics": {"passes_key_p90": 2.2}},
    }

    vec = compiler.compile_contribution_vector(
        dimensions=dims,
        raw_metrics={"minutes": 630},
        confidence=ConfidenceTier.HIGH.value,
        status=DataStatus.EVALUATED.value,
    )

    assert vec["passing"]["score"] == 0.85
    assert vec["passing"]["percentile"] == 90.0
    assert vec["passing"]["status"] == DataStatus.EVALUATED.value
    assert vec["creation"]["score"] == 0.78


def test_compile_intelligence_vector_structure():
    """Validates multi-layer canonical intelligence vector groups and versioning."""
    compiler = PlayerIntelligenceVectorCompiler()

    raw = {
        "minutes": 900,
        "matches": 10,
        "goals_p90": 0.45,
        "assists_p90": 0.22,
        "passes_total_p90": 48.0,
        "avg_pass_accuracy": 85.0,
    }
    contrib_vec = {
        "finishing": {"score": 0.82, "percentile": 88.0},
        "passing": {"score": 0.76, "percentile": 79.0},
    }
    role_prof = {
        "primary_archetype": "Inside Forward",
        "secondary_archetype": "Poacher",
        "archetype_confidence": 0.88,
        "profile_scores": {"finishing": 0.85, "dribbling": 0.78},
    }
    context = {
        "competition_tier": 1.0,
        "starter_ratio": 0.9,
        "minutes_per_match": 85.0,
        "context_multiplier": 1.02,
    }
    action_vals = {
        "action_value_per_90": 0.42,
        "net_action_value": 4.2,
        "total_actions_evaluated": 250,
        "spatial_data_sufficient": False,
    }

    intel_vec = compiler.compile_intelligence_vector(
        player_id="test-player-123",
        position_group="ATT",
        raw_metrics=raw,
        contribution_vector=contrib_vec,
        role_profile=role_prof,
        context=context,
        action_values=action_vals,
        confidence=ConfidenceTier.HIGH.value,
        status=DataStatus.EVALUATED.value,
    )

    assert intel_vec["feature_set_version"] == INTELLIGENCE_FEATURE_SET_VERSION
    assert intel_vec["player_id"] == "test-player-123"
    assert intel_vec["position_group"] == "ATT"

    # Layer checks
    assert intel_vec["performance"]["goals_p90"] == 0.45
    assert intel_vec["performance"]["minutes"] == 900
    assert intel_vec["role"]["primary_archetype"] == "Inside Forward"
    assert intel_vec["role"]["dimension_scores"]["finishing"] == 0.85
    assert intel_vec["action_value"]["action_impact_p90"] == 0.42
    assert intel_vec["action_value"]["spatial_data_sufficient"] is False
    assert intel_vec["context"]["competition_tier"] == 1.0
    assert intel_vec["uncertainty"]["data_status"] == DataStatus.EVALUATED.value
    assert intel_vec["uncertainty"]["confidence"] == ConfidenceTier.HIGH.value
