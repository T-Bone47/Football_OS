"""Historical Market Universe & Temporal Snapshots (Phase 4.1H & 4.1I).
Provides temporal filtering, leakage-safe snapshot construction, and
auditable coverage analytics across historical transfer transactions.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Club, Player, Transfer
from app.market.schemas import MarketCoverageResponse
from app.market.taxonomy import TransferFeeStatus, TransferType


async def get_temporal_transfers(
    session: AsyncSession,
    as_of: datetime | date | None = None,
    player_id: uuid.UUID | None = None,
    club_id: uuid.UUID | None = None,
    position_group: str | None = None,
    fee_statuses: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Transfer]:
    """Retrieves canonical transfer records with strict temporal gating (Phase 4.1I).
    Any transaction after `as_of` is strictly excluded.
    """
    stmt = (
        select(Transfer)
        .options(
            selectinload(Transfer.player),
            selectinload(Transfer.from_club),
            selectinload(Transfer.to_club),
        )
        .order_by(desc(Transfer.transfer_date), desc(Transfer.created_at))
    )

    if as_of is not None:
        as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
        stmt = stmt.where(Transfer.transfer_date <= as_of_date)

    if player_id is not None:
        stmt = stmt.where(Transfer.player_id == player_id)

    if club_id is not None:
        stmt = stmt.where((Transfer.from_club_id == club_id) | (Transfer.to_club_id == club_id))

    if fee_statuses:
        stmt = stmt.where(Transfer.fee_status.in_(fee_statuses))

    if position_group:
        # Filter by player primary position group
        stmt = stmt.join(Player, Transfer.player_id == Player.id)
        if position_group.upper() in ("GK", "GOALKEEPER"):
            stmt = stmt.where(Player.primary_position.ilike("%Goalkeeper%"))
        elif position_group.upper() in ("DEF", "DEFENDER"):
            stmt = stmt.where(Player.primary_position.ilike("%Defender%"))
        elif position_group.upper() in ("MID", "MIDFIELDER"):
            stmt = stmt.where(Player.primary_position.ilike("%Midfielder%"))
        elif position_group.upper() in ("ATT", "ATTACKER", "FORWARD"):
            stmt = stmt.where(
                Player.primary_position.ilike("%Attacker%") | Player.primary_position.ilike("%Forward%")
            )

    stmt = stmt.offset(offset).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


def filter_transfers_in_memory_as_of(
    transfers: list[Transfer],
    as_of: datetime | date,
) -> list[Transfer]:
    """Pure temporal filtering utility for in-memory transfer lists.
    Guarantees bit-for-bit invariance under future transfer injection.
    """
    as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
    return [
        t for t in transfers
        if t.transfer_date is not None and t.transfer_date <= as_of_date
    ]


async def compute_market_coverage_audit(
    session: AsyncSession,
    as_of: datetime | date | None = None,
) -> MarketCoverageResponse:
    """Computes transparent data availability and coverage report for the market universe (Phase 4.1H & 4.1U)."""
    transfers = await get_temporal_transfers(session, as_of=as_of, limit=10000)

    total = len(transfers)
    known = 0
    reported = 0
    unknown = 0
    free = 0
    loans = 0
    qualified = 0

    unique_players = set()
    unique_clubs = set()
    dates: list[date] = []

    for t in transfers:
        if t.player_id:
            unique_players.add(t.player_id)
        if t.from_club_id:
            unique_clubs.add(t.from_club_id)
        if t.to_club_id:
            unique_clubs.add(t.to_club_id)
        if t.transfer_date:
            dates.append(t.transfer_date)

        if t.fee_status == TransferFeeStatus.KNOWN_FEE.value:
            known += 1
            qualified += 1
        elif t.fee_status == TransferFeeStatus.REPORTED_FEE.value:
            reported += 1
            qualified += 1
        elif t.fee_status == TransferFeeStatus.FREE_TRANSFER.value:
            free += 1
            qualified += 1
        elif t.fee_status == TransferFeeStatus.UNKNOWN_FEE.value or t.fee_status == TransferFeeStatus.UNDISCLOSED.value:
            unknown += 1
        elif t.is_loan or "loan" in (t.transfer_type or "").lower():
            loans += 1

    fee_coverage_pct = round((known + reported + free) / total * 100, 1) if total > 0 else 0.0

    # Minimum sample threshold for Phase 4.2 ML training: requires >= 500 qualified historical transactions
    # across multiple seasons.
    limitations: list[str] = []
    if qualified < 500:
        limitations.append(f"Insufficient transaction volume for non-linear ML training (qualified={qualified} < 500 threshold).")
    if fee_coverage_pct < 60.0:
        limitations.append(f"Fee reporting coverage is below 60% ({fee_coverage_pct}%). Undisclosed deals prevail.")
    if len(unique_players) < 100:
        limitations.append(f"Player entity diversity is limited ({len(unique_players)} players).")

    readiness = "READY_FOR_VALUATION_MODEL" if (qualified >= 500 and len(limitations) == 0) else "INSUFFICIENT_TRANSFER_DATA"

    return MarketCoverageResponse(
        total_transfers=total,
        known_fees_count=known,
        reported_fees_count=reported,
        unknown_fees_count=unknown,
        free_transfers_count=free,
        loans_count=loans,
        qualified_transfers_count=qualified,
        unique_players_count=len(unique_players),
        unique_clubs_count=len(unique_clubs),
        earliest_transfer_date=min(dates) if dates else None,
        latest_transfer_date=max(dates) if dates else None,
        fee_coverage_pct=fee_coverage_pct,
        readiness_status=readiness,
        limitations=limitations,
    )


def transfer_db_to_normalized(t: Transfer) -> NormalizedTransfer:
    """Converts a database Transfer model to NormalizedTransfer for merging and deduplication."""
    raw = dict(t.raw_data) if t.raw_data else {}
    if t.player and not raw.get("position"):
        raw["position"] = t.player.primary_position
    if t.player and not raw.get("age") and t.player.birth_date and t.transfer_date:
        age_years = (t.transfer_date - t.player.birth_date).days / 365.25
        raw["player_age_at_transfer"] = round(age_years, 1)

    return NormalizedTransfer(
        provider=t.source_provider or "api-football",
        source_record_id=t.source_record_id or str(t.id),
        provider_player_id=str(t.player_id),
        player_name=t.player.full_name if t.player else "Unknown",
        from_provider_club_id=str(t.from_club_id) if t.from_club_id else None,
        from_club_name=t.from_club.name if t.from_club else None,
        to_provider_club_id=str(t.to_club_id) if t.to_club_id else None,
        to_club_name=t.to_club.name if t.to_club else None,
        transfer_date=t.transfer_date,
        transfer_type=t.transfer_type or "PERMANENT",
        fee_value=t.fee_value,
        fee_currency=t.fee_currency,
        fee_status=t.fee_status,
        fee_eur_normalized=t.fee_eur_normalized,
        is_loan=t.is_loan,
        is_permanent=t.is_permanent,
        option_type=t.option_type or "NONE",
        raw_data=raw,
    )
