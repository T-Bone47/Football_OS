"""Deterministic Transfer Normalization and Data Quality Engine (Phase 4.1F & 4.1G).
Transforms provider transfer envelopes into typed NormalizedTransfer models,
validates integrity, and assigns explicit data quality states without fabricated confidences.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from typing import Any

from app.market.schemas import NormalizedTransfer
from app.market.taxonomy import (
    DataQualityStatus,
    TransferFeeStatus,
    parse_fee_string,
)


def transform_api_football_transfers(payload: dict[str, Any]) -> list[NormalizedTransfer]:
    """Pure transformation of API-Football /transfers response into NormalizedTransfer items."""
    results: list[NormalizedTransfer] = []
    response = payload.get("response")
    if not isinstance(response, list):
        return results

    for item in response:
        if not isinstance(item, dict):
            continue
        player_obj = item.get("player") or {}
        provider_player_id = str(player_obj.get("id") or "")
        player_name = str(player_obj.get("name") or "Unknown Player")
        if not provider_player_id:
            continue

        transfer_list = item.get("transfers") or []
        for idx, t in enumerate(transfer_list):
            if not isinstance(t, dict):
                continue
            raw_date = t.get("date")
            t_date = _parse_date(raw_date)

            teams = t.get("teams") or {}
            team_in = teams.get("in") or {}
            team_out = teams.get("out") or {}

            to_id = str(team_in.get("id")) if team_in.get("id") is not None else None
            to_name = team_in.get("name")
            from_id = str(team_out.get("id")) if team_out.get("id") is not None else None
            from_name = team_out.get("name")

            raw_type = t.get("type")
            parsed = parse_fee_string(raw_type)

            # Deterministic source record id
            rec_sig = f"api-football_{provider_player_id}_{from_id}_{to_id}_{raw_date}_{parsed.transfer_type}_{idx}"
            source_rec_id = hashlib.sha256(rec_sig.encode()).hexdigest()[:24]

            norm = NormalizedTransfer(
                provider="api-football",
                source_record_id=source_rec_id,
                provider_player_id=provider_player_id,
                player_name=player_name,
                from_provider_club_id=from_id,
                from_club_name=from_name,
                to_provider_club_id=to_id,
                to_club_name=to_name,
                transfer_date=t_date,
                transfer_type=parsed.transfer_type.value,
                fee_value=parsed.fee_value,
                fee_currency=parsed.fee_currency,
                fee_status=parsed.fee_status.value,
                fee_eur_normalized=parsed.fee_eur_normalized,
                is_loan=parsed.is_loan,
                is_permanent=parsed.is_permanent,
                option_type=parsed.option_type.value,
                raw_data=t,
            )
            results.append(norm)

    return results


def validate_transfer(transfer: NormalizedTransfer) -> tuple[bool, list[str]]:
    """Validates structural correctness of a normalized transfer."""
    errors: list[str] = []
    if not transfer.provider_player_id:
        errors.append("missing_provider_player_id")
    if not transfer.to_provider_club_id and not transfer.from_provider_club_id:
        errors.append("missing_both_clubs")
    if transfer.fee_value is not None and transfer.fee_value < 0:
        errors.append("negative_fee_value")
    return len(errors) == 0, errors


def assess_transfer_quality(
    transfer: NormalizedTransfer,
    player_resolved: bool,
    from_club_resolved: bool,
    to_club_resolved: bool,
) -> tuple[str, list[str]]:
    """Assigns multi-dimensional data quality state and explicit failure reasons.
    Avoids fabricated numerical confidence values (Phase 4.1G).
    """
    reasons: list[str] = []

    # 1. Identity Resolution quality
    if not player_resolved:
        reasons.append("player_unresolved")
    if transfer.from_provider_club_id and not from_club_resolved:
        reasons.append("from_club_unresolved")
    if transfer.to_provider_club_id and not to_club_resolved:
        reasons.append("to_club_unresolved")

    # 2. Date quality
    if transfer.transfer_date is None:
        reasons.append("date_uncertain")

    # 3. Fee quality
    if transfer.fee_status in (TransferFeeStatus.UNKNOWN_FEE.value, TransferFeeStatus.UNDISCLOSED.value):
        reasons.append("fee_undisclosed")
    elif transfer.fee_status == TransferFeeStatus.ESTIMATED_FEE.value:
        reasons.append("source_estimated")

    # Determine state
    if not player_resolved or (transfer.to_provider_club_id and not to_club_resolved and not from_club_resolved):
        return DataQualityStatus.INSUFFICIENT_DATA.value, reasons

    if "player_unresolved" in reasons or ("from_club_unresolved" in reasons and "to_club_unresolved" in reasons):
        return DataQualityStatus.LOW.value, reasons

    if (
        len(reasons) > 1
        or "fee_undisclosed" in reasons
        or "source_estimated" in reasons
        or "from_club_unresolved" in reasons
        or "to_club_unresolved" in reasons
    ):
        return DataQualityStatus.MEDIUM.value, reasons

    return DataQualityStatus.HIGH.value, reasons


def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    val_str = str(val).strip()
    # Try YYYY-MM-DD
    try:
        return datetime.strptime(val_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        pass
    # Try YYYY-MM
    try:
        return datetime.strptime(val_str[:7], "%Y-%m").date()
    except (ValueError, TypeError):
        pass
    return None
