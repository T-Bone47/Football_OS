"""Unit tests for Transfer Normalization, Schema Validation, and Quality Engine (Phase 4.1F & 4.1G).
"""
import json
from pathlib import Path
import pytest

from app.market.normalizer import (
    assess_transfer_quality,
    transform_api_football_transfers,
    validate_transfer,
)
from app.market.schemas import NormalizedTransfer
from app.market.taxonomy import DataQualityStatus, TransferFeeStatus


@pytest.fixture
def sample_payload():
    snapshot_path = Path("data/bronze/api-football/transfers/b0beb3a6793a7c02d9ada731a6edcd2e2e1b9ed78f425735a154688de94eabf6.json")
    return json.loads(snapshot_path.read_bytes())


def test_transform_api_football_transfers(sample_payload):
    transfers = transform_api_football_transfers(sample_payload)
    assert len(transfers) > 30

    # Test Manuel Akanji transfer to Manchester City
    akanji_mci = next((t for t in transfers if t.provider_player_id == "5" and t.to_provider_club_id == "50"), None)
    assert akanji_mci is not None
    assert akanji_mci.player_name == "M. Akanji"
    assert akanji_mci.fee_value == 17_500_000.0
    assert akanji_mci.fee_currency == "EUR"
    assert akanji_mci.fee_status == TransferFeeStatus.REPORTED_FEE.value
    assert akanji_mci.is_permanent is True
    assert akanji_mci.is_loan is False

    # Test Jadon Sancho loan to Dortmund
    sancho_loan = next((t for t in transfers if t.provider_player_id == "18" and t.to_provider_club_id == "165" and t.is_loan), None)
    assert sancho_loan is not None
    assert sancho_loan.fee_value == 4_000_000.0
    assert sancho_loan.is_loan is True

    # Test Dahoud free transfer to Brighton
    dahoud_free = next((t for t in transfers if t.provider_player_id == "14" and t.to_provider_club_id == "51"), None)
    assert dahoud_free is not None
    assert dahoud_free.fee_status == TransferFeeStatus.FREE_TRANSFER.value
    assert dahoud_free.fee_value == 0.0


def test_validate_transfer():
    valid = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_1",
        provider_player_id="5",
        player_name="M. Akanji",
        to_provider_club_id="50",
    )
    is_valid, errors = validate_transfer(valid)
    assert is_valid is True
    assert len(errors) == 0

    # Missing player id
    invalid_no_player = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_2",
        provider_player_id="",
        player_name="Unknown",
        to_provider_club_id="50",
    )
    is_valid, errors = validate_transfer(invalid_no_player)
    assert is_valid is False
    assert "missing_provider_player_id" in errors

    # Missing both clubs
    invalid_no_clubs = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_3",
        provider_player_id="5",
        player_name="M. Akanji",
    )
    is_valid, errors = validate_transfer(invalid_no_clubs)
    assert is_valid is False
    assert "missing_both_clubs" in errors


from datetime import date


def test_assess_transfer_quality():
    norm = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_1",
        provider_player_id="5",
        player_name="M. Akanji",
        from_provider_club_id="165",
        to_provider_club_id="50",
        fee_status="REPORTED_FEE",
        transfer_date=date(2022, 9, 1),
    )

    # 1. All resolved, reported fee -> HIGH
    q_state, reasons = assess_transfer_quality(norm, player_resolved=True, from_club_resolved=True, to_club_resolved=True)
    assert q_state == DataQualityStatus.HIGH.value
    assert len(reasons) == 0

    # 2. Player unresolved -> INSUFFICIENT_DATA
    q_state, reasons = assess_transfer_quality(norm, player_resolved=False, from_club_resolved=True, to_club_resolved=True)
    assert q_state == DataQualityStatus.INSUFFICIENT_DATA.value
    assert "player_unresolved" in reasons

    # 3. Fee undisclosed -> MEDIUM
    norm_undisc = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_2",
        provider_player_id="5",
        player_name="M. Akanji",
        from_provider_club_id="165",
        to_provider_club_id="50",
        fee_status="UNDISCLOSED",
        transfer_date=date(2022, 9, 1),
    )
    q_state, reasons = assess_transfer_quality(norm_undisc, player_resolved=True, from_club_resolved=True, to_club_resolved=True)
    assert q_state == DataQualityStatus.MEDIUM.value
    assert "fee_undisclosed" in reasons


def test_normalization_idempotency(sample_payload):
    """Normalization must be deterministic and pure."""
    run1 = transform_api_football_transfers(sample_payload)
    run2 = transform_api_football_transfers(sample_payload)

    assert len(run1) == len(run2)
    for t1, t2 in zip(run1, run2):
        assert t1.source_record_id == t2.source_record_id
        assert t1.fee_status == t2.fee_status
        assert t1.fee_eur_normalized == t2.fee_eur_normalized
        assert t1.transfer_date == t2.transfer_date
