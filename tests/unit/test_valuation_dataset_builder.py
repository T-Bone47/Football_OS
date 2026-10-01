"""Unit tests for Valuation Training Dataset Builder & Temporal Safety (Phase 4.1B).
"""
from datetime import date
import pytest

from app.market.dataset import (
    ValuationDatasetBuilder,
    ValuationTrainingRow,
    is_eligible_training_target,
)
from app.market.merging import MergedTransfer
from app.market.taxonomy import TransferFeeStatus


def _create_mock_merged_transfer(
    canonical_key: str,
    player_id: str,
    player_name: str,
    transfer_date: date,
    fee_eur: float | None,
    fee_status: str = TransferFeeStatus.KNOWN_FEE.value,
    is_loan: bool = False,
    is_permanent: bool = True,
    position: str = "MID",
    age: float = 24.0,
) -> MergedTransfer:
    return MergedTransfer(
        canonical_key=canonical_key,
        provider_player_id=player_id,
        player_name=player_name,
        from_provider_club_id="club_a",
        from_club_name="Club A",
        to_provider_club_id="club_b",
        to_club_name="Club B",
        transfer_date=transfer_date,
        transfer_type="Loan" if is_loan else "Permanent",
        fee_value=fee_eur,
        fee_currency="EUR",
        fee_status=fee_status,
        fee_eur_normalized=fee_eur,
        is_loan=is_loan,
        is_permanent=is_permanent,
        position_group=position,
        player_age_at_transfer=age,
        primary_source="api-football",
        sources=[{"provider": "api-football"}],
    )


def test_is_eligible_training_target():
    """Validates training target policy for supervised learning."""
    # Known fee -> eligible
    is_tgt, reason = is_eligible_training_target(TransferFeeStatus.KNOWN_FEE.value, False, 50_000_000.0)
    assert is_tgt is True
    assert reason == "ELIGIBLE"

    # Reported fee -> eligible
    is_tgt, reason = is_eligible_training_target(TransferFeeStatus.REPORTED_FEE.value, False, 30_000_000.0)
    assert is_tgt is True

    # Estimated fee -> excluded
    is_tgt, reason = is_eligible_training_target(TransferFeeStatus.ESTIMATED_FEE.value, False, 40_000_000.0)
    assert is_tgt is False
    assert "ESTIMATED_FEE_EXCLUDED" in reason

    # Unknown / Undisclosed -> excluded
    is_tgt, reason = is_eligible_training_target(TransferFeeStatus.UNKNOWN_FEE.value, False, None)
    assert is_tgt is False
    is_tgt, reason = is_eligible_training_target(TransferFeeStatus.UNDISCLOSED.value, False, None)
    assert is_tgt is False

    # Loan -> excluded from permanent fee regression
    is_tgt, reason = is_eligible_training_target(TransferFeeStatus.KNOWN_FEE.value, True, 5_000_000.0)
    assert is_tgt is False
    assert "LOANS_EXCLUDED" in reason

    # Free transfer -> excluded from fee regression
    is_tgt, reason = is_eligible_training_target(TransferFeeStatus.FREE_TRANSFER.value, False, 0.0)
    assert is_tgt is False
    assert "FREE_TRANSFERS" in reason


def test_dataset_builder_temporal_cutoff():
    """Builder filters out any transfer dated strictly after as_of_date."""
    cutoff = date(2023, 1, 1)
    transfers = [
        _create_mock_merged_transfer("k1", "p1", "Player 1", date(2022, 6, 1), 20_000_000.0),
        _create_mock_merged_transfer("k2", "p2", "Player 2", date(2022, 12, 31), 35_000_000.0),
        _create_mock_merged_transfer("k3", "p3", "Player 3", date(2023, 1, 2), 50_000_000.0),  # After cutoff
    ]

    builder = ValuationDatasetBuilder(as_of_date=cutoff)
    rows = builder.build_dataset(transfers)

    assert len(rows) == 2
    keys = [r.canonical_key for r in rows]
    assert keys == ["k1", "k2"]
    for r in rows:
        assert r.feature_as_of <= r.transfer_date


def test_future_data_injection_invariance_on_dataset_builder():
    """Injecting future transfers into builder must produce bit-for-bit identical training rows."""
    cutoff = date(2022, 9, 1)
    baseline_transfers = [
        _create_mock_merged_transfer("k1", "p1", "P1", date(2021, 7, 1), 15_000_000.0),
        _create_mock_merged_transfer("k2", "p2", "P2", date(2022, 8, 15), 25_000_000.0),
    ]

    builder = ValuationDatasetBuilder(as_of_date=cutoff)
    rows_before = builder.build_dataset(baseline_transfers)
    assert len(rows_before) == 2

    # Inject future transfers
    future_transfers = [
        _create_mock_merged_transfer("k_fut_1", "pf1", "Future 1", date(2023, 1, 1), 100_000_000.0),
        _create_mock_merged_transfer("k_fut_2", "pf2", "Future 2", date(2024, 7, 1), 150_000_000.0),
    ]
    rows_after = builder.build_dataset(baseline_transfers + future_transfers)

    assert len(rows_after) == len(rows_before)
    assert [r.canonical_key for r in rows_after] == [r.canonical_key for r in rows_before]
    assert [r.fee_target_eur for r in rows_after] == [r.fee_target_eur for r in rows_before]
    assert [r.transfer_date for r in rows_after] == [r.transfer_date for r in rows_before]
