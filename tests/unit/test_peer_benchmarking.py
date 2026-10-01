"""Unit tests for Phase 3.2D: Position-Aware Peer Benchmarking Engine."""
from __future__ import annotations

import pytest

from app.intelligence.benchmarks import PeerBenchmarkingEngine, PEER_DISTRIBUTIONS, _norm_cdf
from app.intelligence.taxonomy import MIN_MINUTES_EVALUATED


def test_peer_distribution_definitions():
    """All 4 standard position groups (GK, DEF, MID, ATT) must have reference distributions."""
    for group in ["GK", "DEF", "MID", "ATT"]:
        assert group in PEER_DISTRIBUTIONS
        dist = PEER_DISTRIBUTIONS[group]
        assert len(dist) >= 4
        for metric, (mean, std) in dist.items():
            assert mean >= 0.0
            assert std > 0.0


def test_norm_cdf_math():
    """Validates normal cumulative distribution function properties."""
    # z=0 -> median (0.5)
    assert pytest.approx(_norm_cdf(0.0), rel=1e-3) == 0.5
    # z=1 -> ~84.1%
    assert pytest.approx(_norm_cdf(1.0), rel=1e-2) == 0.841
    # z=-1 -> ~15.9%
    assert pytest.approx(_norm_cdf(-1.0), rel=1e-2) == 0.159


def test_insufficient_sample_gate():
    """Players below 270 minutes must return INSUFFICIENT_SAMPLE and percentiles must be None."""
    engine = PeerBenchmarkingEngine()
    raw = {"tackles_total_p90": 2.5, "interceptions_p90": 1.8}
    
    result = engine.evaluate_benchmarks(
        raw_metrics=raw,
        position_group="DEF",
        sample_minutes=180,  # Below 270 threshold
    )

    assert result["benchmark_status"] == "INSUFFICIENT_SAMPLE"
    assert result["average_percentile"] is None
    for metric, item in result["metrics"].items():
        assert item["status"] == "INSUFFICIENT_SAMPLE"
        assert item["percentile"] is None
        assert item["z_score"] is None


def test_sufficient_sample_evaluation():
    """Players with >=270 minutes must be benchmarked against position group distributions."""
    engine = PeerBenchmarkingEngine()
    raw = {
        "passes_total_p90": 60.0,
        "pass_accuracy": 88.0,
        "passes_key_p90": 2.0,
        "tackles_total_p90": 2.2,
        "interceptions_p90": 1.5,
        "dribbles_success_p90": 1.5,
        "duels_won_p90": 5.0,
    }

    result = engine.evaluate_benchmarks(
        raw_metrics=raw,
        position_group="MID",
        sample_minutes=450,  # 5 matches
        peer_population_size=120,
    )

    assert result["benchmark_status"] == "EVALUATED"
    assert result["peer_sample_size"] == 120
    assert result["average_percentile"] is not None
    assert 50.0 <= result["average_percentile"] <= 100.0

    key_passes = result["metrics"]["passes_key_p90"]
    assert key_passes["status"] == "EVALUATED"
    assert key_passes["value_p90"] == 2.0
    assert key_passes["z_score"] > 0.0
    assert key_passes["percentile"] > 50.0


def test_semantic_null_safety():
    """Unobserved metrics return NOT_OBSERVED with percentile=None, not fabricated or zero."""
    engine = PeerBenchmarkingEngine()
    # No shots or goals observed
    raw = {"passes_key_p90": 1.5}

    result = engine.evaluate_benchmarks(
        raw_metrics=raw,
        position_group="ATT",
        sample_minutes=360,
    )

    assert result["benchmark_status"] == "EVALUATED"
    shots_item = result["metrics"]["shots_total_p90"]
    assert shots_item["status"] == "NOT_OBSERVED"
    assert shots_item["value_p90"] is None
    assert shots_item["percentile"] is None
    assert shots_item["z_score"] is None


def test_outlier_clamping():
    """Extreme outliers must be clamped within [-3.0, 3.0] Z-score to prevent percentiles exceeding [0, 100]."""
    engine = PeerBenchmarkingEngine()
    raw = {
        "shots_total_p90": 25.0,  # Unrealistic 25 shots per 90
        "shots_on_target_p90": 15.0,
        "goals_p90": 8.0,
        "passes_key_p90": 10.0,
        "dribbles_success_p90": 10.0,
        "duels_won_p90": 20.0,
    }

    result = engine.evaluate_benchmarks(
        raw_metrics=raw,
        position_group="ATT",
        sample_minutes=500,
    )

    for metric, item in result["metrics"].items():
        assert -3.0 <= item["z_score"] <= 3.0
        assert 0.0 <= item["percentile"] <= 100.0
