"""Unit tests for Multi-Source Transfer Deduplication and Discrepancy Reconciliation (Phase 4.1B).
"""
from datetime import date
import pytest

from app.market.merging import (
    MergedTransfer,
    SourceDiscrepancy,
    merge_multi_source_transfers,
)
from app.market.schemas import NormalizedTransfer
from app.market.taxonomy import TransferFeeStatus


def _create_normalized_transfer(
    provider: str = "api-football",
    player_id: str = "p_101",
    player_name: str = "Erling Haaland",
    from_club_id: str = "c_bvb",
    from_club_name: str = "Borussia Dortmund",
    to_club_id: str = "c_mci",
    to_club_name: str = "Manchester City",
    transfer_date: date = date(2022, 7, 1),
    transfer_type: str = "Permanent",
    fee_val: float | None = 60_000_000.0,
    fee_curr: str = "EUR",
    fee_status: str = TransferFeeStatus.REPORTED_FEE.value,
    fee_eur: float | None = 60_000_000.0,
    position: str = "Attacker",
    age: int = 21,
) -> NormalizedTransfer:
    return NormalizedTransfer(
        provider=provider,
        source_record_id=f"{provider}_{player_id}_{transfer_date}",
        provider_player_id=player_id,
        player_name=player_name,
        from_provider_club_id=from_club_id,
        from_club_name=from_club_name,
        to_provider_club_id=to_club_id,
        to_club_name=to_club_name,
        transfer_date=transfer_date,
        transfer_type=transfer_type,
        fee_value=fee_val,
        fee_currency=fee_curr,
        fee_status=fee_status,
        fee_eur_normalized=fee_eur,
        is_loan=False,
        is_permanent=True,
        option_type="NONE",
        raw_data={"position": position, "age": age},
    )


def test_single_source_merge_passthrough():
    """Single-source transfer creates MergedTransfer with clean provenance and extracted attributes."""
    t = _create_normalized_transfer()
    merged_list = merge_multi_source_transfers([t])

    assert len(merged_list) == 1
    m = merged_list[0]
    assert m.provider_player_id == "p_101"
    assert m.player_name == "Erling Haaland"
    assert m.fee_eur_normalized == 60_000_000.0
    assert m.has_conflict is False
    assert len(m.conflicts) == 0
    assert len(m.sources) == 1
    assert m.sources[0]["provider"] == "api-football"
    assert m.position_group == "ATT"
    assert m.player_age_at_transfer == 21.0


def test_deterministic_deduplication_identical_records():
    """Duplicate records for same transaction are merged into a single entity."""
    t1 = _create_normalized_transfer(provider="api-football", fee_eur=60_000_000.0)
    t2 = _create_normalized_transfer(provider="open-data", fee_eur=60_000_000.0)

    merged = merge_multi_source_transfers([t1, t2])
    assert len(merged) == 1
    m = merged[0]
    assert m.fee_eur_normalized == 60_000_000.0
    assert m.has_conflict is False
    assert len(m.sources) == 2
    providers = {s["provider"] for s in m.sources}
    assert providers == {"api-football", "open-data"}


def test_discrepancy_detection_minor_within_tolerance():
    """Fee difference within 3% tolerance does not trigger conflict."""
    t1 = _create_normalized_transfer(provider="api-football", fee_eur=100_000_000.0)
    # 102M vs 100M is 1.96% discrepancy (< 3%)
    t2 = _create_normalized_transfer(provider="open-data", fee_eur=102_000_000.0)

    merged = merge_multi_source_transfers([t1, t2], fee_discrepancy_threshold=0.03)
    assert len(merged) == 1
    assert merged[0].has_conflict is False
    assert len(merged[0].conflicts) == 0


def test_fee_conflict_statutory_known_fee_priority():
    """When source B has statutory KNOWN_FEE, it takes priority over REPORTED_FEE."""
    t1 = _create_normalized_transfer(
        provider="api-football",
        fee_eur=60_000_000.0,
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
    )
    t2 = _create_normalized_transfer(
        provider="open-data",
        fee_eur=75_000_000.0,
        fee_status=TransferFeeStatus.KNOWN_FEE.value,
    )

    merged = merge_multi_source_transfers([t1, t2])
    assert len(merged) == 1
    m = merged[0]
    assert m.has_conflict is True
    assert len(m.conflicts) == 1
    c = m.conflicts[0]
    assert c.resolution_policy == "STATUTORY_KNOWN_FEE_PRIORITY"
    assert c.resolved_value == 75_000_000.0
    assert m.fee_eur_normalized == 75_000_000.0
    assert m.fee_status == TransferFeeStatus.KNOWN_FEE.value


def test_fee_conflict_primary_source_priority_no_averaging():
    """When both sources are REPORTED_FEE, primary source is preserved without averaging."""
    t1 = _create_normalized_transfer(
        provider="api-football",
        fee_eur=85_000_000.0,
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
    )
    t2 = _create_normalized_transfer(
        provider="open-data",
        fee_eur=80_000_000.0,
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
    )

    merged = merge_multi_source_transfers([t1, t2], primary_provider="api-football")
    assert len(merged) == 1
    m = merged[0]
    assert m.has_conflict is True
    assert m.fee_eur_normalized == 85_000_000.0  # NOT averaged to 82.5M
    c = m.conflicts[0]
    assert c.resolution_policy == "PRIMARY_SOURCE_PRIORITY_NO_AVERAGING"
    assert c.is_uncertain is False  # 5.88% < 15%


def test_fee_conflict_high_discrepancy_uncertainty():
    """Discrepancies > 15% are marked uncertain."""
    t1 = _create_normalized_transfer(
        provider="api-football",
        fee_eur=100_000_000.0,
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
    )
    t2 = _create_normalized_transfer(
        provider="open-data",
        fee_eur=75_000_000.0,
        fee_status=TransferFeeStatus.REPORTED_FEE.value,
    )

    merged = merge_multi_source_transfers([t1, t2])
    assert len(merged) == 1
    assert merged[0].conflicts[0].is_uncertain is True
    assert merged[0].conflicts[0].relative_diff_pct == 25.0
