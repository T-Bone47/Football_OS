"""Unit tests for Baseline Valuation Re-evaluation on Expanded Dataset (Phase 4.1B).
"""
from datetime import date
import pytest

from app.market.merging import MergedTransfer
from app.market.valuation import evaluate_temporal_baseline


def _create_mock_transfer(
    idx: int,
    t_date: date,
    fee: float,
    pos: str = "MID",
) -> MergedTransfer:
    return MergedTransfer(
        canonical_key=f"key_{idx}",
        provider_player_id=f"p_{idx}",
        player_name=f"Player {idx}",
        from_provider_club_id="c_from",
        from_club_name="From Club",
        to_provider_club_id="c_to",
        to_club_name="To Club",
        transfer_date=t_date,
        transfer_type="Permanent",
        fee_value=fee,
        fee_currency="EUR",
        fee_status="KNOWN_FEE",
        fee_eur_normalized=fee,
        is_loan=False,
        is_permanent=True,
        position_group=pos,
        player_age_at_transfer=24.0,
        primary_source="open-data",
        sources=[{"provider": "open-data"}],
    )


def test_baseline_evaluation_on_expanded_dataset():
    """Evaluates deterministic baseline on expanded multi-position dataset across temporal split."""
    split_date = date(2023, 1, 1)

    # Train pool: 2021-2022
    train = [
        _create_mock_transfer(1, date(2021, 7, 1), 15_000_000.0, "GK"),
        _create_mock_transfer(2, date(2021, 8, 1), 25_000_000.0, "DEF"),
        _create_mock_transfer(3, date(2022, 1, 10), 35_000_000.0, "MID"),
        _create_mock_transfer(4, date(2022, 7, 15), 60_000_000.0, "ATT"),
        _create_mock_transfer(5, date(2022, 8, 20), 40_000_000.0, "MID"),
    ]

    # Test pool: 2023-2024
    test = [
        _create_mock_transfer(6, date(2023, 1, 15), 18_000_000.0, "GK"),
        _create_mock_transfer(7, date(2023, 7, 1), 30_000_000.0, "DEF"),
        _create_mock_transfer(8, date(2023, 8, 10), 42_000_000.0, "MID"),
        _create_mock_transfer(9, date(2024, 1, 5), 75_000_000.0, "ATT"),
    ]

    res = evaluate_temporal_baseline(train + test, split_date=split_date)

    assert res["status"] == "EVALUATED"
    assert res["train_size"] == 5
    assert res["test_size"] == 4
    assert res["mae"] > 0
    assert res["rmse"] > 0
    assert res["med_ae"] > 0
    assert res["log_mae"] > 0

    # Subgroup breakdowns
    assert "by_position" in res
    assert "GK" in res["by_position"]
    assert "DEF" in res["by_position"]
    assert "MID" in res["by_position"]
    assert "ATT" in res["by_position"]

    assert "by_fee_band" in res
    assert len(res["by_fee_band"]) > 0


def test_baseline_comparison_phase_4_1_vs_expanded():
    """Baseline metrics can be compared between initial and expanded cohorts."""
    split_date = date(2023, 1, 1)

    initial_set = [
        _create_mock_transfer(1, date(2022, 6, 1), 30_000_000.0, "MID"),
        _create_mock_transfer(2, date(2023, 6, 1), 32_000_000.0, "MID"),
    ]
    res_initial = evaluate_temporal_baseline(initial_set, split_date=split_date)
    assert res_initial["train_size"] == 1
    assert res_initial["test_size"] == 1

    expanded_set = initial_set + [
        _create_mock_transfer(3, date(2022, 7, 1), 50_000_000.0, "ATT"),
        _create_mock_transfer(4, date(2023, 7, 1), 55_000_000.0, "ATT"),
    ]
    res_expanded = evaluate_temporal_baseline(expanded_set, split_date=split_date)
    assert res_expanded["train_size"] == 2
    assert res_expanded["test_size"] == 2
