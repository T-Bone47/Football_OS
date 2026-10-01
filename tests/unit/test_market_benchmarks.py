"""Unit tests for Market Benchmarks Engine (Phase 4.1L).
Validates sample-gated percentiles, dispersion metrics, and deterministic null handling.
"""
import pytest

from app.market.valuation import MarketBenchmarkEngine


def test_calculate_benchmarks_sufficient_sample():
    """Sample >= 3 computes median, q1, q3, and iqr."""
    fees = [10_000_000.0, 20_000_000.0, 30_000_000.0, 40_000_000.0, 50_000_000.0]
    bench = MarketBenchmarkEngine.calculate_benchmarks(fees, position_group="MID", min_sample=3)

    assert bench.data_status == "EVALUATED"
    assert bench.sample_size == 5
    assert bench.median_fee_eur == 30_000_000.0
    assert bench.min_fee_eur == 10_000_000.0
    assert bench.max_fee_eur == 50_000_000.0
    assert bench.q1_fee_eur == 15_000_000.0  # Median of [10M, 20M]
    assert bench.q3_fee_eur == 45_000_000.0  # Median of [40M, 50M]
    assert bench.iqr_fee_eur == 30_000_000.0


def test_calculate_benchmarks_insufficient_sample():
    """Sample < 3 triggers hard gate: INSUFFICIENT_DATA with all statistical metrics as None."""
    fees = [15_000_000.0, 25_000_000.0]
    bench = MarketBenchmarkEngine.calculate_benchmarks(fees, position_group="ATT", min_sample=3)

    assert bench.data_status == "INSUFFICIENT_DATA"
    assert bench.sample_size == 2
    assert bench.median_fee_eur is None
    assert bench.q1_fee_eur is None
    assert bench.q3_fee_eur is None
    assert bench.iqr_fee_eur is None


def test_calculate_benchmarks_empty():
    """Empty list yields INSUFFICIENT_DATA and sample_size = 0."""
    bench = MarketBenchmarkEngine.calculate_benchmarks([], position_group="GK", min_sample=3)
    assert bench.data_status == "INSUFFICIENT_DATA"
    assert bench.sample_size == 0
    assert bench.median_fee_eur is None
