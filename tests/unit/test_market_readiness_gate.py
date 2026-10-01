"""Unit tests for Market Readiness Gate & Subgroup Sample Analysis (Phase 4.1B).
"""
from datetime import date
import pytest

from app.market.readiness import (
    MarketReadinessReport,
    SubgroupSampleAnalysis,
    evaluate_market_readiness,
)
from app.market.merging import MergedTransfer
from app.market.taxonomy import TransferFeeStatus


def _create_dummy_merged(
    idx: int,
    fee: float = 25_000_000.0,
    pos: str = "MID",
    age: float = 24.0,
    is_loan: bool = False,
    fee_status: str = TransferFeeStatus.KNOWN_FEE.value,
) -> MergedTransfer:
    return MergedTransfer(
        canonical_key=f"key_{idx}",
        provider_player_id=f"p_{idx}",
        player_name=f"Player {idx}",
        from_provider_club_id=f"c_from_{idx % 10}",
        from_club_name=f"Club From {idx % 10}",
        to_provider_club_id=f"c_to_{idx % 10}",
        to_club_name=f"Club To {idx % 10}",
        transfer_date=date(2022, 1, 1),
        transfer_type="Loan" if is_loan else "Permanent",
        fee_value=fee,
        fee_currency="EUR",
        fee_status=fee_status,
        fee_eur_normalized=fee,
        is_loan=is_loan,
        is_permanent=not is_loan,
        position_group=pos,
        player_age_at_transfer=age,
        primary_source="api-football",
        sources=[{"provider": "api-football"}],
    )


def test_readiness_gate_insufficient_sample_size():
    """Universe with 50 transfers is flagged INSUFFICIENT_TRANSFER_DATA."""
    transfers = [_create_dummy_merged(i) for i in range(50)]
    report = evaluate_market_readiness(transfers)

    assert report.status == "INSUFFICIENT_TRANSFER_DATA"
    assert report.phase_4_2_can_begin is False
    assert report.total_transactions == 50
    assert report.usable_fee_targets == 50
    assert any("Insufficient transaction volume" in r for r in report.reasons)
    assert report.subgroups_adequate is False


def test_readiness_gate_subgroup_deficits():
    """Identifies specific subgroup deficits (GK, DEF, ATT, etc.)."""
    # 60 MID transfers, 0 GK, 0 DEF, 0 ATT
    transfers = [_create_dummy_merged(i, pos="MID") for i in range(60)]
    report = evaluate_market_readiness(
        transfers,
        min_qualified_threshold=50,
        min_player_threshold=30,
        min_position_subgroup=10,
        min_gk_subgroup=5,
    )

    assert report.subgroups.positions["MID"] == 60
    assert report.subgroups.positions["GK"] == 0
    assert report.subgroups.positions["DEF"] == 0
    assert report.subgroups_adequate is False
    assert any("GK" in d for d in report.subgroups.subgroup_deficits)


def test_readiness_gate_blocked_by_licensing():
    """Invalid or restricted licensing yields BLOCKED_BY_DATA_ACCESS."""
    transfers = [_create_dummy_merged(i) for i in range(500)]
    report = evaluate_market_readiness(transfers, licenses_valid=False)

    assert report.status == "BLOCKED_BY_DATA_ACCESS"
    assert report.phase_4_2_can_begin is False
    assert report.licenses_sufficient is False
    assert any("licensing" in r.lower() for r in report.reasons)


def test_readiness_gate_hypothetically_satisfied():
    """When volume, player diversity, subgroups, and licensing pass, gate opens."""
    # Build 520 diverse transfers
    transfers = []
    positions = ["GK"] * 25 + ["DEF"] * 165 + ["MID"] * 170 + ["ATT"] * 160
    for i, pos in enumerate(positions):
        transfers.append(
            _create_dummy_merged(
                i,
                pos=pos,
                age=20.0 + (i % 12),
                fee=15_000_000.0 + ((i % 5) * 15_000_000.0),
            )
        )

    intel_ids = {f"p_{i}" for i in range(300)}
    report = evaluate_market_readiness(
        transfers,
        player_intel_player_ids=intel_ids,
        min_qualified_threshold=500,
        min_player_threshold=100,
        min_position_subgroup=50,
        min_gk_subgroup=15,
        min_intel_coverage_pct=40.0,
        licenses_valid=True,
    )

    assert report.status == "READY_FOR_VALUATION_MODEL"
    assert report.phase_4_2_can_begin is True
    assert report.usable_fee_targets >= 500
    assert report.subgroups_adequate is True
