"""Unit tests for Baseline Valuation Engine & Temporal Evaluation (Phase 4.1M, 4.1N, 4.1O).
"""
from datetime import date
from unittest.mock import MagicMock
import pytest

from app.market.valuation import BaselineValuationEngine, evaluate_temporal_baseline


def test_age_adjustment_curve():
    """Verify deterministic age adjustment multipliers across developmental and career phases."""
    engine = BaselineValuationEngine()

    assert engine.get_age_adjustment(19.5) == 1.15  # Youth upside
    assert engine.get_age_adjustment(22.0) == 1.10  # Pre-peak
    assert engine.get_age_adjustment(26.5) == 1.00  # Peak career
    assert engine.get_age_adjustment(30.0) == 0.85  # Late career
    assert engine.get_age_adjustment(34.0) == 0.65  # Veteran depreciation
    assert engine.get_age_adjustment(None) == 1.00  # Fallback neutral


def test_evaluate_temporal_baseline_insufficient():
    """When train or test pool is empty, returns INSUFFICIENT_DATA."""
    res = evaluate_temporal_baseline([], split_date=date(2023, 1, 1))
    assert res["status"] == "INSUFFICIENT_DATA"
    assert res["mae"] is None


def test_evaluate_temporal_baseline_evaluated():
    """Computes MAE, RMSE, and MedAE when train and test pools have verified transactions."""
    # Create mock Transfer objects
    def make_mock_transfer(t_date: date, fee: float, pos: str):
        t = MagicMock()
        t.transfer_date = t_date
        t.fee_eur_normalized = fee
        p = MagicMock()
        p.primary_position = pos
        t.player = p
        return t

    train_transfers = [
        make_mock_transfer(date(2021, 7, 1), 20_000_000.0, "Midfielder"),
        make_mock_transfer(date(2022, 1, 15), 30_000_000.0, "Midfielder"),
        make_mock_transfer(date(2022, 8, 1), 25_000_000.0, "Midfielder"),
    ]
    test_transfers = [
        make_mock_transfer(date(2023, 7, 10), 28_000_000.0, "Midfielder"),
        make_mock_transfer(date(2024, 1, 5), 22_000_000.0, "Midfielder"),
    ]

    all_transfers = train_transfers + test_transfers
    res = evaluate_temporal_baseline(all_transfers, split_date=date(2023, 1, 1))

    assert res["status"] == "EVALUATED"
    assert res["train_size"] == 3
    assert res["test_size"] == 2
    # Train median is 25M. Test errors: |25M - 28M| = 3M, |25M - 22M| = 3M.
    assert res["mae"] == 3_000_000.0
    assert res["rmse"] == 3_000_000.0
    assert res["med_ae"] == 3_000_000.0
