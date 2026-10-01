"""Multi-Source Transfer Deduplication and Fee Reconciliation Engine (Phase 4.1B).
Merges transfer records across heterogeneous sources using deterministic composite keys,
detects discrepancies, preserves multi-source provenance, and enforces explicit reconciliation policies
without silent overwriting, arbitrary averaging, or zero coercion.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from pydantic import BaseModel, Field

from app.market.schemas import NormalizedTransfer
from app.market.taxonomy import TransferFeeStatus


class SourceDiscrepancy(BaseModel):
    """Explicit audit record of a conflict between two data providers."""
    field_name: str
    source_a: str
    value_a: Any
    source_b: str
    value_b: Any
    relative_diff_pct: float | None = None
    resolution_policy: str
    resolved_value: Any
    is_uncertain: bool = False


class MergedTransfer(BaseModel):
    """Canonical transfer entity merged across one or more source providers."""
    canonical_key: str
    provider_player_id: str
    player_name: str
    from_provider_club_id: str | None = None
    from_club_name: str | None = None
    to_provider_club_id: str | None = None
    to_club_name: str | None = None
    transfer_date: date | None = None
    transfer_type: str
    fee_value: float | None = None
    fee_currency: str | None = None
    fee_status: str
    fee_eur_normalized: float | None = None
    is_loan: bool = False
    is_permanent: bool = True
    option_type: str = "NONE"
    position_group: str | None = None
    player_age_at_transfer: float | None = None

    # Multi-source provenance
    primary_source: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    has_conflict: bool = False
    conflicts: list[SourceDiscrepancy] = Field(default_factory=list)
    data_quality_status: str = "MEDIUM"


def merge_multi_source_transfers(
    transfers: list[NormalizedTransfer],
    primary_provider: str = "api-football",
    fee_discrepancy_threshold: float = 0.03,  # 3% relative discrepancy triggers conflict
) -> list[MergedTransfer]:
    """Deterministically deduplicates and merges transfers across multiple providers."""
    groups: dict[str, list[NormalizedTransfer]] = {}

    for t in transfers:
        key = _build_composite_key(t)
        if key not in groups:
            groups[key] = []
        groups[key].append(t)

    merged_results: list[MergedTransfer] = []

    for key, group in groups.items():
        if len(group) == 1:
            # Single-source transfer
            t = group[0]
            merged = MergedTransfer(
                canonical_key=key,
                provider_player_id=t.provider_player_id,
                player_name=t.player_name,
                from_provider_club_id=t.from_provider_club_id,
                from_club_name=t.from_club_name,
                to_provider_club_id=t.to_provider_club_id,
                to_club_name=t.to_club_name,
                transfer_date=t.transfer_date,
                transfer_type=t.transfer_type,
                fee_value=t.fee_value,
                fee_currency=t.fee_currency,
                fee_status=t.fee_status,
                fee_eur_normalized=t.fee_eur_normalized,
                is_loan=t.is_loan,
                is_permanent=t.is_permanent,
                option_type=t.option_type,
                position_group=_normalize_position(t.raw_data.get("position") or t.raw_data.get("position_group") if t.raw_data else None),
                player_age_at_transfer=_extract_age(t.raw_data),
                primary_source=t.provider,
                sources=[_extract_source_meta(t)],
                has_conflict=False,
                conflicts=[],
            )
            merged_results.append(merged)
            continue

        # Multi-source transfer: reconcile records
        primary_record = next((t for t in group if t.provider == primary_provider), group[0])
        other_records = [t for t in group if t != primary_record]

        sources_meta = [_extract_source_meta(primary_record)]
        conflicts: list[SourceDiscrepancy] = []

        resolved_fee = primary_record.fee_value
        resolved_fee_eur = primary_record.fee_eur_normalized
        resolved_fee_status = primary_record.fee_status
        resolved_currency = primary_record.fee_currency

        for other in other_records:
            sources_meta.append(_extract_source_meta(other))

            # Reconcile Fee Discrepancy
            if primary_record.fee_eur_normalized is not None and other.fee_eur_normalized is not None:
                fa = primary_record.fee_eur_normalized
                fb = other.fee_eur_normalized
                max_f = max(abs(fa), abs(fb))
                diff_pct = abs(fa - fb) / max_f if max_f > 0 else 0.0

                if diff_pct > fee_discrepancy_threshold:
                    # Fee disagreement detected
                    # Decision policy:
                    # 1. If one is KNOWN_FEE and other is REPORTED_FEE, KNOWN_FEE wins.
                    # 2. Otherwise preserve PRIMARY source, flag uncertainty if diff > 15%.
                    if primary_record.fee_status == TransferFeeStatus.KNOWN_FEE.value:
                        policy = "STATUTORY_KNOWN_FEE_PRIORITY"
                        chosen = fa
                        chosen_status = primary_record.fee_status
                    elif other.fee_status == TransferFeeStatus.KNOWN_FEE.value:
                        policy = "STATUTORY_KNOWN_FEE_PRIORITY"
                        chosen = fb
                        chosen_status = other.fee_status
                        resolved_fee = other.fee_value
                        resolved_fee_eur = other.fee_eur_normalized
                        resolved_fee_status = other.fee_status
                        resolved_currency = other.fee_currency
                    else:
                        policy = "PRIMARY_SOURCE_PRIORITY_NO_AVERAGING"
                        chosen = fa
                        chosen_status = primary_record.fee_status

                    is_uncertain = diff_pct > 0.15

                    conflicts.append(
                        SourceDiscrepancy(
                            field_name="fee_eur_normalized",
                            source_a=primary_record.provider,
                            value_a=fa,
                            source_b=other.provider,
                            value_b=fb,
                            relative_diff_pct=round(diff_pct * 100, 2),
                            resolution_policy=policy,
                            resolved_value=chosen,
                            is_uncertain=is_uncertain,
                        )
                    )
            elif primary_record.fee_eur_normalized is None and other.fee_eur_normalized is not None:
                # Primary was unknown, secondary reported a fee
                conflicts.append(
                    SourceDiscrepancy(
                        field_name="fee_eur_normalized",
                        source_a=primary_record.provider,
                        value_a=None,
                        source_b=other.provider,
                        value_b=other.fee_eur_normalized,
                        resolution_policy="COMPLEMENTARY_SOURCE_UPGRADE",
                        resolved_value=other.fee_eur_normalized,
                        is_uncertain=False,
                    )
                )
                resolved_fee = other.fee_value
                resolved_fee_eur = other.fee_eur_normalized
                resolved_fee_status = other.fee_status
                resolved_currency = other.fee_currency

        has_conflict = len(conflicts) > 0

        # Position & Age across multi-source group
        resolved_pos = None
        resolved_age = None
        for r in group:
            if not resolved_pos and r.raw_data:
                resolved_pos = _normalize_position(r.raw_data.get("position") or r.raw_data.get("position_group"))
            if resolved_age is None and r.raw_data:
                resolved_age = _extract_age(r.raw_data)

        merged = MergedTransfer(
            canonical_key=key,
            provider_player_id=primary_record.provider_player_id,
            player_name=primary_record.player_name,
            from_provider_club_id=primary_record.from_provider_club_id,
            from_club_name=primary_record.from_club_name,
            to_provider_club_id=primary_record.to_provider_club_id,
            to_club_name=primary_record.to_club_name,
            transfer_date=primary_record.transfer_date,
            transfer_type=primary_record.transfer_type,
            fee_value=resolved_fee,
            fee_currency=resolved_currency,
            fee_status=resolved_fee_status,
            fee_eur_normalized=resolved_fee_eur,
            is_loan=primary_record.is_loan,
            is_permanent=primary_record.is_permanent,
            option_type=primary_record.option_type,
            position_group=resolved_pos,
            player_age_at_transfer=resolved_age,
            primary_source=primary_record.provider,
            sources=sources_meta,
            has_conflict=has_conflict,
            conflicts=conflicts,
        )
        merged_results.append(merged)

    return merged_results


def _normalize_position(pos: Any) -> str | None:
    if not pos or not isinstance(pos, str):
        return None
    p = pos.upper()
    if "GK" in p or "GOAL" in p:
        return "GK"
    if "DEF" in p or "BACK" in p:
        return "DEF"
    if "ATT" in p or "FORW" in p or "WINGER" in p or "STRIKER" in p:
        return "ATT"
    if "MID" in p:
        return "MID"
    return "MID"


def _extract_age(raw: dict[str, Any] | None) -> float | None:
    if not raw or not isinstance(raw, dict):
        return None
    for k in ("player_age_at_transfer", "age_at_transfer", "age", "player_age"):
        val = raw.get(k)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def _build_composite_key(t: NormalizedTransfer) -> str:
    """Builds deterministic composite deduplication signature (Principle 5).
    Keyed by: player identity, transfer date, from club identity, to club identity, transfer type.
    """
    p_id = t.provider_player_id or t.player_name.strip().lower()
    from_id = t.from_provider_club_id or (t.from_club_name or "none").strip().lower()
    to_id = t.to_provider_club_id or (t.to_club_name or "none").strip().lower()
    date_str = str(t.transfer_date or "undated")
    t_type = (t.transfer_type or "permanent").strip().lower()
    return f"{p_id}::{from_id}::{to_id}::{date_str}::{t_type}"


def _extract_source_meta(t: NormalizedTransfer) -> dict[str, Any]:
    return {
        "provider": t.provider,
        "source_record_id": t.source_record_id,
        "fee_value": t.fee_value,
        "fee_currency": t.fee_currency,
        "fee_status": t.fee_status,
        "fee_eur_normalized": t.fee_eur_normalized,
        "raw_record": t.raw_data,
    }
