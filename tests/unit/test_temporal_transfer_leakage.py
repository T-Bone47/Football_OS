"""Unit tests for Temporal Safety and Leakage Invariance (Phase 4.1I & 4.1T).
Verifies that injecting future transfers leaves historical dataset and evaluation bit-for-bit identical.
"""
from datetime import date
from unittest.mock import MagicMock
import pytest

from app.market.universe import filter_transfers_in_memory_as_of
from app.market.valuation import evaluate_temporal_baseline


def _create_mock_transfer(t_id: str, t_date: date, fee: float, player_name: str):
    t = MagicMock()
    t.id = t_id
    t.transfer_date = t_date
    t.fee_eur_normalized = fee
    p = MagicMock()
    p.name = player_name
    p.primary_position = "Midfielder"
    t.player = p
    return t


def test_future_transfer_injection_bit_for_bit_identical():
    """Injecting future transfers must leave historical dataset as of T strictly unchanged."""
    as_of_t = date(2022, 9, 1)

    historical_transfers = [
        _create_mock_transfer("t1", date(2021, 6, 15), 15_000_000.0, "Player A"),
        _create_mock_transfer("t2", date(2022, 1, 10), 25_000_000.0, "Player B"),
        _create_mock_transfer("t3", date(2022, 9, 1), 30_000_000.0, "Player C"),  # Exactly on as_of
    ]

    # Baseline snapshot as of T
    snapshot_before = filter_transfers_in_memory_as_of(historical_transfers, as_of=as_of_t)
    assert len(snapshot_before) == 3

    # Inject future transfers (after T)
    future_transfers = [
        _create_mock_transfer("t_future_1", date(2022, 9, 2), 80_000_000.0, "Future Megastar"),
        _create_mock_transfer("t_future_2", date(2023, 1, 31), 120_000_000.0, "Future Talent"),
        _create_mock_transfer("t_future_3", date(2024, 7, 1), 45_000_000.0, "Future Veteran"),
    ]
    augmented_pool = historical_transfers + future_transfers

    # Snapshot after future injection
    snapshot_after = filter_transfers_in_memory_as_of(augmented_pool, as_of=as_of_t)

    # Must be bit-for-bit identical
    assert len(snapshot_after) == len(snapshot_before)
    assert [t.id for t in snapshot_after] == [t.id for t in snapshot_before]
    assert [t.transfer_date for t in snapshot_after] == [t.transfer_date for t in snapshot_before]
    assert [t.fee_eur_normalized for t in snapshot_after] == [t.fee_eur_normalized for t in snapshot_before]


def test_temporal_baseline_evaluation_no_leakage():
    """Future test transactions must never enter training pool in temporal baseline evaluation."""
    split_date = date(2023, 1, 1)

    train_transfers = [
        _create_mock_transfer("t1", date(2021, 7, 1), 20_000_000.0, "P1"),
        _create_mock_transfer("t2", date(2022, 8, 1), 30_000_000.0, "P2"),
    ]
    test_transfers = [
        _create_mock_transfer("t3", date(2023, 7, 1), 50_000_000.0, "P3"),
        _create_mock_transfer("t4", date(2024, 1, 1), 70_000_000.0, "P4"),
    ]

    res = evaluate_temporal_baseline(train_transfers + test_transfers, split_date=split_date)
    assert res["status"] == "EVALUATED"
    assert res["train_size"] == 2
    assert res["test_size"] == 2

    # Now add massive future transfers to test pool; training size and median must remain unchanged
    huge_future = [
        _create_mock_transfer("t_huge", date(2025, 1, 1), 250_000_000.0, "P_Huge"),
    ]
    res_after = evaluate_temporal_baseline(train_transfers + test_transfers + huge_future, split_date=split_date)
    assert res_after["train_size"] == 2
    assert res_after["test_size"] == 3
