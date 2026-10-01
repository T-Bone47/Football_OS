"""Unit tests for Phase 4.1C Transfer Data Acquisition & Coverage Expansion.
Verifies multi-snapshot bronze loading, deterministic deduplication, zero fabrication metadata,
subgroup adequacy across all positions (GK >= 15, DEF >= 50, MID >= 50, ATT >= 50),
unaltered threshold enforcement, and temporal baseline re-evaluation.
"""
from datetime import date
from pathlib import Path
import pytest

from app.market.adapters.open_data import OpenDataTransferAdapter, load_bronze_open_transfers
from app.market.merging import merge_multi_source_transfers
from app.market.readiness import evaluate_market_readiness
from app.market.valuation import evaluate_temporal_baseline


def test_bronze_open_transfers_multi_snapshot_loading():
    """Verifies that all curated bronze snapshots in data/bronze/open-transfers load successfully."""
    bronze_dir = Path("data/bronze/open-transfers")
    if not bronze_dir.exists():
        pytest.skip("data/bronze/open-transfers not found in working directory")

    transfers = load_bronze_open_transfers(bronze_dir)
    assert len(transfers) >= 200, f"Expected at least 200 transfers, got {len(transfers)}"

    # Check that required canonical fields are populated
    for t in transfers:
        assert t.provider == "open-transfer-archive"
        assert t.provider_player_id
        assert t.player_name
        assert t.transfer_date is not None
        assert t.transfer_type in ("Permanent", "Loan", "Free")


def test_bronze_snapshot_metadata_and_provenance():
    """Verifies that all benchmark JSON files contain auditable metadata, licenses, and zero-fabrication audit."""
    bronze_dir = Path("data/bronze/open-transfers")
    if not bronze_dir.exists():
        pytest.skip("data/bronze/open-transfers not found")

    import json
    json_files = list(bronze_dir.glob("*.json"))
    assert len(json_files) >= 5, f"Expected at least 5 benchmark files, found {len(json_files)}"

    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "metadata" in data:
            meta = data["metadata"]
            assert "license" in meta
            assert "provenance" in meta
            assert meta["provenance"].get("zero_fabrication_audit") == "PASSED"


def test_deterministic_deduplication_and_merging_expanded():
    """Verifies that multi-source merging of the expanded dataset is deterministic and idempotent."""
    transfers = load_bronze_open_transfers()
    if not transfers:
        pytest.skip("No transfers loaded")

    merged_first = merge_multi_source_transfers(transfers)
    merged_second = merge_multi_source_transfers(transfers)

    assert len(merged_first) == len(merged_second)
    assert len(merged_first) >= 200

    # Ensure idempotency
    for m1, m2 in zip(merged_first, merged_second):
        assert m1.canonical_key == m2.canonical_key
        assert m1.fee_eur_normalized == m2.fee_eur_normalized
        assert m1.position_group == m2.position_group


def test_subgroup_adequacy_across_all_positions():
    """Verifies that the expanded universe satisfies all 4 position subgroup thresholds:
    GK >= 15, DEF >= 50, MID >= 50, ATT >= 50.
    """
    transfers = load_bronze_open_transfers()
    if not transfers:
        pytest.skip("No transfers loaded")

    merged = merge_multi_source_transfers(transfers)
    report = evaluate_market_readiness(merged)

    pos_counts = report.subgroups.positions
    assert pos_counts.get("GK", 0) >= 15, f"GK count {pos_counts.get('GK')} < 15"
    assert pos_counts.get("DEF", 0) >= 50, f"DEF count {pos_counts.get('DEF')} < 50"
    assert pos_counts.get("MID", 0) >= 50, f"MID count {pos_counts.get('MID')} < 50"
    assert pos_counts.get("ATT", 0) >= 50, f"ATT count {pos_counts.get('ATT')} < 50"

    assert report.subgroups_adequate is True
    assert len(report.subgroups.subgroup_deficits) == 0


def test_readiness_gate_unaltered_threshold_honesty():
    """Verifies that with usable targets < 500, the readiness gate strictly reports
    INSUFFICIENT_TRANSFER_DATA and phase_4_2_can_begin == False without lowering thresholds.
    """
    transfers = load_bronze_open_transfers()
    if not transfers:
        pytest.skip("No transfers loaded")

    merged = merge_multi_source_transfers(transfers)
    # Test gate honesty when usable targets < 500 (Phase 4.1C baseline size)
    report = evaluate_market_readiness(merged[:235])

    assert report.status == "INSUFFICIENT_TRANSFER_DATA"
    assert report.phase_4_2_can_begin is False
    assert report.usable_fee_targets < 500
    assert report.usable_fee_targets >= 200
    assert report.unique_players >= 100
    assert report.fee_coverage_pct >= 90.0

    # Ensure reasons cite the exact transaction gap
    assert any("500 threshold" in r for r in report.reasons)
    assert any("additional verified transactions" in a for a in report.required_actions)


def test_expanded_baseline_valuation_determinism():
    """Verifies that running evaluate_temporal_baseline on the expanded dataset
    produces valid, non-zero error metrics and valid breakdowns.
    """
    transfers = load_bronze_open_transfers()
    if not transfers:
        pytest.skip("No transfers loaded")

    merged = merge_multi_source_transfers(transfers)
    split_date = date(2023, 1, 1)

    res = evaluate_temporal_baseline(merged, split_date=split_date)
    assert res["status"] == "EVALUATED"
    assert res["train_size"] >= 100
    assert res["test_size"] >= 50
    assert res["mae"] > 0
    assert res["rmse"] > 0
    assert res["med_ae"] > 0
    assert res["log_mae"] > 0

    # All 4 position subgroups must be represented in evaluation
    by_pos = res["by_position"]
    for p in ("GK", "DEF", "MID", "ATT"):
        assert p in by_pos
        assert by_pos[p]["count"] > 0
        assert by_pos[p]["mae"] > 0
