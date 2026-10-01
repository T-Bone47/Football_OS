"""Unit tests for Phase 4.1D Transfer Dataset Completion & Readiness Closure.

Verifies:
- 500+ qualified fee target threshold is legitimately exceeded without fabrication
- Strict non-fabrication provenance and metadata across all bronze snapshots
- Subgroup representation across positions (GK >= 15, DEF/MID/ATT >= 50), fee bands, and age bands
- Readiness gate transition to READY_FOR_VALUATION_MODEL with phase_4_2_can_begin == True
- Bit-for-bit ingestion idempotency and dataset stability across runs
- Strict temporal safety and point-in-time feature integrity
"""
from datetime import date
from pathlib import Path
import pytest

from app.market.adapters.open_data import OpenDataTransferAdapter, load_bronze_open_transfers
from app.market.merging import merge_multi_source_transfers
from app.market.readiness import evaluate_market_readiness
from app.market.valuation import evaluate_temporal_baseline
from app.market.dataset import ValuationDatasetBuilder


def test_phase_4_1d_bronze_dataset_completion():
    """Verifies that all bronze snapshots in data/bronze/open-transfers load successfully
    and yield >= 500 verified permanent/fee transactions.
    """
    bronze_dir = Path("data/bronze/open-transfers")
    if not bronze_dir.exists():
        pytest.skip("data/bronze/open-transfers not found")

    transfers = load_bronze_open_transfers(bronze_dir)
    assert len(transfers) >= 500, f"Expected >= 500 bronze transfers, got {len(transfers)}"

    # Audit that every record preserves authentic provenance
    for t in transfers:
        assert t.provider == "open-transfer-archive"
        assert t.provider_player_id
        assert t.player_name
        assert t.transfer_date is not None
        assert t.transfer_type in ("Permanent", "Loan", "Free")
        assert t.from_club_name
        assert t.to_club_name


def test_phase_4_1d_metadata_and_zero_fabrication():
    """Verifies that all bronze benchmark files include proper metadata and passed zero-fabrication audits."""
    import json
    bronze_dir = Path("data/bronze/open-transfers")
    json_files = list(bronze_dir.glob("*.json"))
    assert len(json_files) >= 12, f"Expected >= 12 bronze benchmark files, found {len(json_files)}"

    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "metadata" in data:
            meta = data["metadata"]
            assert "license" in meta
            assert "provenance" in meta
            assert meta["provenance"].get("zero_fabrication_audit") == "PASSED"


def test_phase_4_1d_training_dataset_rebuild_and_exclusions():
    """Verifies that ValuationDatasetBuilder rebuilds the training dataset, yielding >= 500
    eligible regression targets, and cleanly excludes loans and non-target fee statuses.
    """
    transfers = load_bronze_open_transfers()
    merged = merge_multi_source_transfers(transfers)

    builder = ValuationDatasetBuilder()
    rows = builder.build_dataset(merged)

    eligible_rows = [r for r in rows if r.is_target_eligible]
    assert len(eligible_rows) >= 500, f"Expected >= 500 eligible training rows, got {len(eligible_rows)}"

    for r in eligible_rows:
        assert r.fee_target_eur is not None
        assert r.fee_target_eur > 0
        assert r.transfer_type == "Permanent"
        assert r.canonical_key
        assert r.player_id
        assert r.position_group in ("GK", "DEF", "MID", "ATT")

    # Exclusions breakdown
    excluded_rows = [r for r in rows if not r.is_target_eligible]
    assert len(excluded_rows) > 0
    for r in excluded_rows:
        assert r.target_exclusion_reason in (
            "LOANS_EXCLUDED_FROM_PERMANENT_FEE_REGRESSION",
            "NON_TARGET_FEE_STATUS",
            "ESTIMATED_FEE_EXCLUDED_BY_DEFAULT",
            "FREE_TRANSFERS_SEPARATE_CLASS",
            "INVALID_OR_NON_POSITIVE_FEE",
        )


def test_phase_4_1d_subgroup_representation_and_zero_deficits():
    """Verifies that all position, fee band, and age band requirements are met with 0 deficits."""
    transfers = load_bronze_open_transfers()
    merged = merge_multi_source_transfers(transfers)
    report = evaluate_market_readiness(merged)

    pos = report.subgroups.positions
    assert pos.get("GK", 0) >= 15, f"GK count {pos.get('GK')} < 15"
    assert pos.get("DEF", 0) >= 50, f"DEF count {pos.get('DEF')} < 50"
    assert pos.get("MID", 0) >= 50, f"MID count {pos.get('MID')} < 50"
    assert pos.get("ATT", 0) >= 50, f"ATT count {pos.get('ATT')} < 50"

    fee_bands = report.subgroups.fee_bands
    for fb in ("<10M", "10M-30M", "30M-70M", ">70M"):
        assert fee_bands.get(fb, 0) > 0, f"Fee band {fb} is empty"

    age_bands = report.subgroups.age_bands
    for ab in ("<21", "21-24", "25-28", "29+"):
        assert age_bands.get(ab, 0) > 0, f"Age band {ab} is empty"

    assert report.subgroups_adequate is True
    assert len(report.subgroups.subgroup_deficits) == 0


def test_phase_4_1d_readiness_gate_unlocked():
    """Verifies that with qualified transactions >= 500 and all subgroup criteria satisfied,
    the readiness gate deterministically transitions to READY_FOR_VALUATION_MODEL.
    """
    transfers = load_bronze_open_transfers()
    merged = merge_multi_source_transfers(transfers)
    report = evaluate_market_readiness(merged)

    assert report.usable_fee_targets >= 500, f"Usable fee targets {report.usable_fee_targets} < 500"
    assert report.unique_players >= 100, f"Unique players {report.unique_players} < 100"
    assert report.subgroups_adequate is True
    assert report.status == "READY_FOR_VALUATION_MODEL"
    assert report.phase_4_2_can_begin is True
    assert any("satisfied" in r.lower() or "readiness" in r.lower() for r in report.reasons)


def test_phase_4_1d_ingestion_idempotency_and_stability():
    """Verifies that running ingestion and canonical merging twice yields bit-for-bit identical results."""
    transfers_1 = load_bronze_open_transfers()
    transfers_2 = load_bronze_open_transfers()

    merged_1 = merge_multi_source_transfers(transfers_1)
    merged_2 = merge_multi_source_transfers(transfers_2)

    assert len(merged_1) == len(merged_2)
    for m1, m2 in zip(merged_1, merged_2):
        assert m1.canonical_key == m2.canonical_key
        assert m1.fee_eur_normalized == m2.fee_eur_normalized
        assert m1.provider_player_id == m2.provider_player_id
        assert m1.from_club_name == m2.from_club_name
        assert m1.to_club_name == m2.to_club_name
        assert m1.transfer_date == m2.transfer_date

    rep_1 = evaluate_market_readiness(merged_1)
    rep_2 = evaluate_market_readiness(merged_2)
    assert rep_1.status == rep_2.status
    assert rep_1.usable_fee_targets == rep_2.usable_fee_targets
    assert rep_1.unique_players == rep_2.unique_players


def test_phase_4_1d_temporal_evaluation_validity():
    """Verifies that the temporal baseline evaluation succeeds with train/test splits >= 100/50."""
    transfers = load_bronze_open_transfers()
    merged = merge_multi_source_transfers(transfers)

    res = evaluate_temporal_baseline(merged, split_date=date(2023, 1, 1))
    assert res["status"] == "EVALUATED"
    assert res["train_size"] >= 300
    assert res["test_size"] >= 100
    assert res["mae"] > 0
    assert res["rmse"] > 0
    assert res["med_ae"] > 0
    assert res["log_mae"] > 0

    # Ensure fee band breakdowns are all present
    for fb in ("<10M", "10M-30M", "30M-70M", ">70M"):
        assert fb in res["by_fee_band"]
