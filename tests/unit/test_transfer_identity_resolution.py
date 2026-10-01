"""Unit tests for Player & Club Identity Resolution in Transfer Ingestion (Phase 4.1E & 4.1G).
"""
from datetime import date
import pytest

from app.market.normalizer import assess_transfer_quality
from app.market.schemas import NormalizedTransfer
from app.market.taxonomy import DataQualityStatus, TransferFeeStatus


def test_identity_resolution_fully_resolved():
    """When player, from_club, and to_club all resolve, quality is HIGH (for known/reported fee)."""
    norm = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_akanji_mci",
        provider_player_id="5",
        player_name="M. Akanji",
        from_provider_club_id="165",
        from_club_name="Borussia Dortmund",
        to_provider_club_id="50",
        to_club_name="Manchester City",
        transfer_date=date(2022, 9, 1),
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
        fee_value=17500000.0,
        fee_currency="EUR",
        fee_eur_normalized=17500000.0,
        is_permanent=True,
    )

    quality, reasons = assess_transfer_quality(
        norm,
        player_resolved=True,
        from_club_resolved=True,
        to_club_resolved=True,
    )
    assert quality == DataQualityStatus.HIGH.value
    assert reasons == []


def test_identity_resolution_unresolved_player():
    """Unresolved player must cause quality to be INSUFFICIENT_DATA and flag player_unresolved."""
    norm = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_unknown_player",
        provider_player_id="999999",
        player_name="Unknown Prospect",
        from_provider_club_id="165",
        to_provider_club_id="50",
        transfer_date=date(2022, 9, 1),
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
    )

    quality, reasons = assess_transfer_quality(
        norm,
        player_resolved=False,
        from_club_resolved=True,
        to_club_resolved=True,
    )
    assert quality == DataQualityStatus.INSUFFICIENT_DATA.value
    assert "player_unresolved" in reasons


def test_identity_resolution_unresolved_club():
    """Unresolved clubs must be flagged with explicit reasons without guessing."""
    norm = NormalizedTransfer(
        provider="api-football",
        source_record_id="rec_unresolved_club",
        provider_player_id="5",
        player_name="M. Akanji",
        from_provider_club_id="99991",
        from_club_name="Unknown FC",
        to_provider_club_id="50",
        to_club_name="Manchester City",
        transfer_date=date(2022, 9, 1),
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
    )

    # Selling club unresolved
    quality, reasons = assess_transfer_quality(
        norm,
        player_resolved=True,
        from_club_resolved=False,
        to_club_resolved=True,
    )
    assert "from_club_unresolved" in reasons
    # If only 1 club is unresolved and fee is reported, quality drops to MEDIUM
    assert quality == DataQualityStatus.MEDIUM.value

    # Both clubs unresolved
    quality_both, reasons_both = assess_transfer_quality(
        norm,
        player_resolved=True,
        from_club_resolved=False,
        to_club_resolved=False,
    )
    assert "from_club_unresolved" in reasons_both
    assert "to_club_unresolved" in reasons_both
    assert quality_both in (DataQualityStatus.LOW.value, DataQualityStatus.INSUFFICIENT_DATA.value)
