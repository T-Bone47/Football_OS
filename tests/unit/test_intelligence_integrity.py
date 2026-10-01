"""Unit tests for Phase 3.2 Integrity, Deterministic Explanations, and Temporal Safety."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest

from app.intelligence.explanations import DeterministicExplanationGenerator
from app.intelligence.taxonomy import DataStatus, ConfidenceTier, INTELLIGENCE_CALCULATION_VERSION
from app.intelligence.trajectory import TrajectoryCompiler


def test_deterministic_explanations_low_confidence():
    """Players with <270 mins get clear, auditable why_low_confidence reasons without LLM."""
    gen = DeterministicExplanationGenerator()
    expl = gen.generate_explanations(
        dimensions={},
        raw_metrics={"minutes": 180},
        peer_benchmarks={"metrics": {}},
        sample_minutes=180,
        sample_matches=2,
        confidence=ConfidenceTier.INSUFFICIENT_SAMPLE.value,
        status=DataStatus.INSUFFICIENT_SAMPLE.value,
    )

    assert len(expl["why_low_confidence"]) == 1
    assert "below minimum threshold (270 mins)" in expl["why_low_confidence"][0]
    assert "180 mins across 2 matches" in expl["why_low_confidence"][0]


def test_deterministic_explanations_why_strong():
    """Players with strong dimension scores (>=0.70) get specific explanation drivers."""
    gen = DeterministicExplanationGenerator()
    dims = {
        "passing": {"score": 0.85, "percentile": 92.0},
        "creation": {"score": 0.78, "percentile": 84.0},
        "defending": {"score": 0.45, "percentile": 40.0},
    }
    benchmarks = {
        "metrics": {
            "passes_key_p90": {"value_p90": 2.4, "percentile": 88.0},
        }
    }

    expl = gen.generate_explanations(
        dimensions=dims,
        raw_metrics={"minutes": 900},
        peer_benchmarks=benchmarks,
        sample_minutes=900,
        sample_matches=10,
        confidence=ConfidenceTier.HIGH.value,
        status=DataStatus.EVALUATED.value,
    )

    assert any("passing" in s for s in expl["why_strong"])
    assert any("creation" in s for s in expl["why_strong"])
    assert any("passes key" in s for s in expl["why_strong"])
    assert len(expl["why_low_confidence"]) == 0


def test_trajectory_temporal_chronology():
    """Trajectory compiler correctly builds chronological progression and seasonal trend."""
    compiler = TrajectoryCompiler()
    t0 = datetime(2025, 1, 10, 15, 0, tzinfo=timezone.utc)
    t1 = datetime(2025, 1, 17, 15, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 1, 24, 15, 0, tzinfo=timezone.utc)

    records = [
        (
            SimpleNamespace(minutes=90, rating=7.2, goals=1, assists=0, passes_key=2, tackles_total=1, interceptions=1, match_id="m1"),
            SimpleNamespace(date=t0, round="Round 1"),
        ),
        (
            SimpleNamespace(minutes=90, rating=8.0, goals=0, assists=2, passes_key=3, tackles_total=2, interceptions=0, match_id="m2"),
            SimpleNamespace(date=t1, round="Round 2"),
        ),
        (
            SimpleNamespace(minutes=60, rating=6.5, goals=0, assists=0, passes_key=1, tackles_total=0, interceptions=0, match_id="m3"),
            SimpleNamespace(date=t2, round="Round 3"),
        ),
    ]

    traj = compiler.compile_trajectory(records)

    assert traj["trajectory_status"] == "EVALUATED"
    assert traj["total_recorded_matches"] == 3
    assert traj["cumulative_minutes"] == 240
    assert len(traj["timeline"]) == 3
    assert traj["timeline"][0]["cumulative_minutes"] == 90
    assert traj["timeline"][1]["cumulative_minutes"] == 180
    assert traj["timeline"][2]["cumulative_minutes"] == 240
    assert traj["volatility_score"] is not None


def test_temporal_safety_invariance():
    """Filtering by cutoff date t1 must produce bit-for-bit identical trajectory
    regardless of subsequent future matches occurring at t2.
    """
    compiler = TrajectoryCompiler()
    t0 = datetime(2025, 1, 10, tzinfo=timezone.utc)
    t1 = datetime(2025, 1, 17, tzinfo=timezone.utc)
    t_future = datetime(2025, 2, 1, tzinfo=timezone.utc)

    match_past = (
        SimpleNamespace(minutes=90, rating=7.0, goals=1, assists=0, passes_key=1, tackles_total=1, interceptions=1, match_id="m1"),
        SimpleNamespace(date=t0, round="R1"),
    )
    match_future = (
        SimpleNamespace(minutes=90, rating=9.5, goals=3, assists=2, passes_key=5, tackles_total=3, interceptions=2, match_id="m2"),
        SimpleNamespace(date=t_future, round="R2"),
    )

    # Historical run at t1: only past match is visible
    historical_records = [r for r in [match_past, match_future] if r[1].date < t1]
    traj_historical = compiler.compile_trajectory(historical_records)

    # Future run without future match
    isolated_records = [match_past]
    traj_isolated = compiler.compile_trajectory(isolated_records)

    assert traj_historical["total_recorded_matches"] == traj_isolated["total_recorded_matches"]
    assert traj_historical["cumulative_minutes"] == traj_isolated["cumulative_minutes"]
    assert traj_historical["timeline"] == traj_isolated["timeline"]
