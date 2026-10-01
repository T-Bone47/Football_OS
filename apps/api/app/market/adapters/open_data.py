"""Open Data / Benchmark Transfer Adapter (Phase 4.1B).
Adapts verified open-access and public domain transfer archives (e.g. CC0-1.0 / Open Football benchmarks).
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from app.market.adapters.base import TransferSourceAdapter
from app.market.schemas import NormalizedTransfer
from app.market.taxonomy import (
    OptionType,
    TransferFeeStatus,
    TransferType,
    normalize_currency,
    parse_fee_string,
)


class OpenDataTransferAdapter(TransferSourceAdapter):
    """Adapter for open-license historical transfer benchmark payloads."""

    def __init__(self, provider_name: str = "open-transfer-archive", license_type: str = "UNVERIFIED") -> None:
        # Phase 18 (R21): the curated lists carry no verifiable licence or origin.
        self._provider_name = provider_name
        self._license_type = license_type

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def license_type(self) -> str:
        return self._license_type

    def transform(self, payload: dict[str, Any] | list[dict[str, Any]]) -> list[NormalizedTransfer]:
        """Transforms open-data records list into NormalizedTransfer items."""
        items = payload if isinstance(payload, list) else payload.get("transfers") or payload.get("data") or []
        results: list[NormalizedTransfer] = []

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            provider_player_id = str(item.get("player_id") or item.get("provider_player_id") or "")
            player_name = str(item.get("player_name") or "Unknown Player")
            if not provider_player_id and not player_name:
                continue

            raw_date = item.get("transfer_date") or item.get("date")
            t_date = self._parse_date(raw_date)

            from_club_id = str(item.get("from_club_id") or "") if item.get("from_club_id") is not None else None
            from_club_name = item.get("from_club_name")
            to_club_id = str(item.get("to_club_id") or "") if item.get("to_club_id") is not None else None
            to_club_name = item.get("to_club_name")

            raw_fee = item.get("fee_value") or item.get("fee") or item.get("fee_eur")
            currency = str(item.get("fee_currency") or item.get("currency") or "EUR").upper()
            fee_status_str = str(item.get("fee_status") or "").upper()

            is_loan = bool(item.get("is_loan", False))
            is_permanent = bool(item.get("is_permanent", not is_loan))
            transfer_type_str = str(item.get("transfer_type") or ("Loan" if is_loan else "Permanent"))

            # Determine fee semantics
            fee_val: float | None = None
            fee_status = TransferFeeStatus.UNKNOWN_FEE
            fee_eur: float | None = None

            if isinstance(raw_fee, (int, float)):
                if raw_fee > 0:
                    fee_val = float(raw_fee)
                    fee_status = TransferFeeStatus[fee_status_str] if fee_status_str in TransferFeeStatus.__members__ else TransferFeeStatus.REPORTED_FEE
                    fee_eur = normalize_currency(fee_val, currency)
                elif raw_fee == 0:
                    fee_val = 0.0
                    fee_status = TransferFeeStatus.FREE_TRANSFER if "FREE" in fee_status_str or not is_loan else TransferFeeStatus.REPORTED_FEE
                    fee_eur = 0.0
            elif isinstance(raw_fee, str):
                parsed = parse_fee_string(raw_fee)
                fee_val = parsed.fee_value
                currency = parsed.fee_currency or currency
                fee_status = parsed.fee_status
                fee_eur = parsed.fee_eur_normalized
                if parsed.is_loan:
                    is_loan = True
                    is_permanent = False

            # Deterministic source record signature
            rec_sig = f"{self.provider_name}_{provider_player_id}_{from_club_id}_{to_club_id}_{t_date}_{idx}"
            source_rec_id = hashlib.sha256(rec_sig.encode()).hexdigest()[:24]

            norm = NormalizedTransfer(
                provider=self.provider_name,
                source_record_id=source_rec_id,
                provider_player_id=provider_player_id,
                player_name=player_name,
                from_provider_club_id=from_club_id,
                from_club_name=from_club_name,
                to_provider_club_id=to_club_id,
                to_club_name=to_club_name,
                transfer_date=t_date,
                transfer_type=transfer_type_str,
                fee_value=fee_val,
                fee_currency=currency if fee_val is not None else None,
                fee_status=fee_status.value,
                fee_eur_normalized=fee_eur,
                is_loan=is_loan,
                is_permanent=is_permanent,
                option_type=OptionType.NONE.value,
                raw_data=item,
            )
            results.append(norm)

        return results

    @staticmethod
    def _parse_date(val: Any) -> date | None:
        if not val:
            return None
        if isinstance(val, date):
            return val
        if isinstance(val, datetime):
            return val.date()
        val_str = str(val).strip()
        try:
            return datetime.strptime(val_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
        try:
            return datetime.strptime(val_str[:7], "%Y-%m").date()
        except (ValueError, TypeError):
            pass
        return None


def load_bronze_open_transfers(bronze_dir: str | Path | None = None) -> list[NormalizedTransfer]:
    """Scans and loads all verified open benchmark bronze snapshots."""
    target_dir: Path | None = None
    if bronze_dir:
        p = Path(bronze_dir)
        if p.is_dir():
            target_dir = p
    if not target_dir:
        candidates = [
            Path("data/bronze/open-transfers"),
            Path("../data/bronze/open-transfers"),
            Path("../../data/bronze/open-transfers"),
            Path(__file__).resolve().parents[5] / "data" / "bronze" / "open-transfers",
        ]
        for c in candidates:
            if c.is_dir():
                target_dir = c
                break

    if not target_dir or not target_dir.exists():
        return []

    adapter = OpenDataTransferAdapter()
    loaded: list[NormalizedTransfer] = []
    for json_file in sorted(target_dir.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded.extend(adapter.transform(data))
        except Exception:
            continue
    return loaded
