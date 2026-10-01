"""Unit tests for Comparable Transfer Engine (Phase 4.1K).
Validates multi-dimensional similarity formulation, weight calibration, and ranking.
"""
import math
import pytest

from app.market.comparables import ComparableTransferEngine


def test_weights_sum_to_one():
    """All explicit similarity dimension weights must sum to exactly 1.0."""
    engine = ComparableTransferEngine()
    total_weight = (
        engine.WEIGHT_ROLE
        + engine.WEIGHT_CONTRIBUTION
        + engine.WEIGHT_AGE
        + engine.WEIGHT_TIER
        + engine.WEIGHT_RECENCY
    )
    assert abs(total_weight - 1.0) < 1e-6


def test_calculate_similarity_identical_profiles():
    """Identical candidate and target with zero days elapsed must produce high similarity near 1.0."""
    engine = ComparableTransferEngine()
    score, breakdown = engine.calculate_similarity(
        target_age=25.0,
        candidate_age=25.0,
        target_role="Box-to-Box Midfielder",
        candidate_role="Box-to-Box Midfielder",
        target_contrib={"passing": 0.8, "creation": 0.7, "defending": 0.6},
        candidate_contrib={"passing": 0.8, "creation": 0.7, "defending": 0.6},
        days_diff=0,
        target_tier=1.0,
        candidate_tier=1.0,
    )
    assert score >= 0.95
    assert breakdown["role"] == 1.0
    assert breakdown["age"] == 1.0
    assert breakdown["contribution"] == 1.0
    assert breakdown["tier"] == 1.0
    assert breakdown["recency"] == 1.0


def test_calculate_similarity_divergent_profiles():
    """Divergent age, role, and old transaction must produce lower similarity."""
    engine = ComparableTransferEngine()
    score, breakdown = engine.calculate_similarity(
        target_age=21.0,
        candidate_age=32.0,  # 11-year age difference
        target_role="Poacher",
        candidate_role="Ball-Playing Defender",
        target_contrib={"finishing": 0.9, "creation": 0.2},
        candidate_contrib={"defending": 0.9, "duels": 0.8},
        days_diff=1825,  # 5 years ago
        target_tier=1.0,
        candidate_tier=3.0,
    )
    assert score < 0.60
    assert breakdown["role"] == 0.65
    assert breakdown["age"] < 0.20
    assert breakdown["recency"] < 0.50


def test_recency_decay():
    """Recent transfer (e.g. 30 days ago) must have higher recency score than transfer 6 years ago."""
    engine = ComparableTransferEngine()
    _, breakdown_recent = engine.calculate_similarity(
        target_age=24.0, candidate_age=24.0,
        target_role="Winger", candidate_role="Winger",
        target_contrib={}, candidate_contrib={},
        days_diff=30,
    )
    _, breakdown_old = engine.calculate_similarity(
        target_age=24.0, candidate_age=24.0,
        target_role="Winger", candidate_role="Winger",
        target_contrib={}, candidate_contrib={},
        days_diff=2190,  # ~6 years
    )
    assert breakdown_recent["recency"] > breakdown_old["recency"]
