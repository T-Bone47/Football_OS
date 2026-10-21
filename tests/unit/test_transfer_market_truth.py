"""Truthful transfer-market tests.

The previous Phase 4.1D suite asserted that a 500+ row "verified" benchmark
existed under ``data/bronze/open-transfers``. That directory was never in the
repository, and the only thing able to create it was a hand-typed curator
script that also wrote its own ``zero_fabrication_audit: PASSED`` metadata —
i.e. a self-certified fixture, not evidence. Those assertions were removed.

These tests instead pin the behaviour that matters:

* an absent benchmark is empty, and the readiness gate stays blocked;
* provider fee strings are parsed without turning unknown fees into zero;
* the readiness report measures competition coverage instead of assuming
  five leagues;
* a temporal baseline refuses to evaluate without both partitions.

The ``MergedTransfer`` objects below are isolated unit fixtures for the gate's
arithmetic; they are not presented as ingested production data.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.market.adapters.open_data import load_bronze_open_transfers
from app.market.merging import MergedTransfer
from app.market.normalizer import transform_api_football_transfers
from app.market.readiness import evaluate_market_readiness
from app.market.taxonomy import TransferFeeStatus
from app.market.valuation import evaluate_temporal_baseline


def _payload() -> dict:
    return {
        "get": "transfers",
        "parameters": {"player": "5"},
        "errors": [],
        "results": 1,
        "paging": {"current": 1, "total": 1},
        "response": [
            {
                "player": {"id": 5, "name": "M. Akanji"},
                "transfers": [
                    {
                        "date": "2022-09-01",
                        "type": "\u20ac 17.5M",
                        "teams": {
                            "in": {"id": 50, "name": "Manchester City"},
                            "out": {"id": 165, "name": "Borussia Dortmund"},
                        },
                    },
                    {
                        "date": "2025-09-01",
                        "type": "Loan",
                        "teams": {
                            "in": {"id": 505, "name": "Internazionale"},
                            "out": {"id": 50, "name": "Manchester City"},
                        },
                    },
                    {
                        "date": "2017-07-01",
                        "type": "N/A",
                        "teams": {
                            "in": {"id": 551, "name": "FC Basel 1893"},
                            "out": {"id": 0, "name": "Unknown"},
                        },
                    },
                    {
                        "date": "2021-07-01",
                        "type": "Free",
                        "teams": {
                            "in": {"id": 50, "name": "Manchester City"},
                            "out": {"id": 551, "name": "FC Basel 1893"},
                        },
                    },
                ],
            }
        ],
    }


def test_missing_benchmark_is_empty_and_readiness_stays_blocked(tmp_path: Path):
    transfers = load_bronze_open_transfers(tmp_path / "absent")
    assert transfers == []

    report = evaluate_market_readiness(transfers)
    assert report.status == "INSUFFICIENT_TRANSFER_DATA"
    assert report.phase_4_2_can_begin is False
    assert report.total_transactions == 0
    assert report.competitions_count == 0
    assert report.temporal_joins_leakage_safe is False


def test_provider_fee_strings_preserve_unknown_not_zero():
    parsed = transform_api_football_transfers(_payload())
    assert len(parsed) == 4

    permanent = parsed[0]
    assert permanent.fee_status == TransferFeeStatus.REPORTED_FEE.value
    assert permanent.fee_value == 17_500_000.0
    assert permanent.fee_eur_normalized == 17_500_000.0
    assert permanent.is_permanent is True

    loan = parsed[1]
    assert loan.is_loan is True
    assert loan.fee_status == TransferFeeStatus.LOAN.value
    assert loan.fee_value is None

    unknown = parsed[2]
    assert unknown.fee_status == TransferFeeStatus.UNKNOWN_FEE.value
    assert unknown.fee_value is None, "unknown fee must never become 0"

    free = parsed[3]
    assert free.fee_status == TransferFeeStatus.FREE_TRANSFER.value
    assert free.fee_value == 0.0


def test_loader_reads_only_well_formed_snapshot_files(tmp_path: Path):
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    open_payload = {
        "transfers": [
            {
                "player_id": "open_1",
                "player_name": "Example Player",
                "from_club_name": "Club A",
                "to_club_name": "Club B",
                "transfer_date": "2022-09-01",
                "fee_value": 1_000_000,
                "fee_currency": "EUR",
                "fee_status": "KNOWN_FEE",
                "transfer_type": "Permanent",
            }
        ]
    }
    (bronze / "good.json").write_text(json.dumps(open_payload), encoding="utf-8")
    (bronze / "broken.json").write_text("{not json", encoding="utf-8")

    transfers = load_bronze_open_transfers(bronze)
    assert len(transfers) == 1
    assert transfers[0].provider == "open-transfer-archive"
    assert transfers[0].fee_eur_normalized == 1_000_000


def _merged(idx: int) -> MergedTransfer:
    return MergedTransfer(
        canonical_key=f"key_{idx}",
        provider_player_id=f"p_{idx}",
        player_name=f"Player {idx}",
        from_provider_club_id=f"c_from_{idx % 10}",
        from_club_name=f"Club From {idx % 10}",
        to_provider_club_id=f"c_to_{idx % 10}",
        to_club_name=f"Club To {idx % 10}",
        transfer_date=date(2022, 1, 1),
        transfer_type="Permanent",
        fee_value=25_000_000.0,
        fee_currency="EUR",
        fee_status=TransferFeeStatus.KNOWN_FEE.value,
        fee_eur_normalized=25_000_000.0,
        is_loan=False,
        is_permanent=True,
        position_group="MID",
        player_age_at_transfer=24.0,
        primary_source="api-football",
        sources=[{"provider": "api-football"}],
    )


def test_competition_count_is_zero_when_provider_gives_no_context():
    """API-Football /transfers carries no competition field; the gate must not
    claim five leagues it did not observe."""
    transfers = [_merged(i) for i in range(10)]
    assert evaluate_market_readiness(transfers).competitions_count == 0


def test_temporal_baseline_refuses_to_evaluate_without_both_partitions():
    result = evaluate_temporal_baseline([], split_date=date(2023, 1, 1))
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["mae"] is None
    assert result["rmse"] is None


def test_db_transfer_adapter_uses_the_real_player_columns(monkeypatch):
    """Regression: the adapter referenced Player.birth_date/full_name, neither
    of which exists, so /market/readiness answered 500 for any stored transfer."""
    from types import SimpleNamespace

    from app.market.universe import transfer_db_to_normalized

    transfer = SimpleNamespace(
        raw_data={},
        player=SimpleNamespace(
            primary_position="Defender",
            date_of_birth=date(1995, 1, 1),
            name="Test Player",
        ),
        source_provider="api-football",
        source_record_id="rec-1",
        player_id="11111111-1111-1111-1111-111111111111",
        from_club_id=None,
        from_club=None,
        to_club_id=None,
        to_club=None,
        transfer_date=date(2023, 1, 1),
        transfer_type="PERMANENT",
        fee_value=1_000_000.0,
        fee_currency="EUR",
        fee_status="KNOWN_FEE",
        fee_eur_normalized=1_000_000.0,
        is_loan=False,
        is_permanent=True,
        option_type="NONE",
        id="22222222-2222-2222-2222-222222222222",
    )

    normalized = transfer_db_to_normalized(transfer)

    assert normalized.player_name == "Test Player"
    assert normalized.raw_data["player_age_at_transfer"] == 28.0


def test_intelligence_coverage_counts_distinct_players():
    """A player with several transfers used to be counted once per row, so the
    reported coverage exceeded 100%."""
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(
            provider_player_id="p1",
            from_provider_club_id="c1",
            to_provider_club_id="c2",
            transfer_date=date(2023, 1, 1),
            transfer_type="PERMANENT",
            fee_value=10_000_000.0,
            fee_eur_normalized=10_000_000.0,
            fee_status=TransferFeeStatus.KNOWN_FEE.value,
            is_loan=False,
            position_group="MID",
        )
        for _ in range(3)
    ]

    report = evaluate_market_readiness(rows, player_intel_player_ids={"p1"})

    assert report.unique_players == 1
    assert report.player_intelligence_coverage_pct == 100.0
