"""Player Market Context Representation (Phase 4.1J).
Compiles a point-in-time snapshot of player profile, tactical role, performance,
contribution, and historical transactions with strict temporal leakage safety.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import (
    Club,
    Player,
    PlayerContributionSnapshot,
    PlayerIntelligenceSnapshot,
    PlayerRoleProfile,
    Transfer,
)
from app.market.schemas import MarketContextResponse
from app.roles.registry import map_position_to_group


async def build_player_market_context(
    session: AsyncSession,
    player_id: uuid.UUID,
    as_of: datetime | date | None = None,
) -> MarketContextResponse | None:
    """Builds a leakage-safe market context representation for a player as of a target timestamp."""
    eval_time = as_of or datetime.now(timezone.utc)
    eval_date = eval_time.date() if isinstance(eval_time, datetime) else eval_time
    eval_datetime = eval_time if isinstance(eval_time, datetime) else datetime.combine(eval_time, datetime.min.time(), tzinfo=timezone.utc)

    # 1. Fetch Player
    player = (await session.execute(select(Player).where(Player.id == player_id))).scalar_one_or_none()
    if not player:
        return None

    # Calculate age as of evaluation date
    age_at_as_of = None
    if player.date_of_birth:
        days = (eval_date - player.date_of_birth).days
        age_at_as_of = round(days / 365.25, 1)

    pos_group = map_position_to_group(player.primary_position).value if player.primary_position else "MID"

    # 2. Query historical transfers strictly on or before eval_date
    t_stmt = (
        select(Transfer)
        .options(selectinload(Transfer.to_club), selectinload(Transfer.from_club))
        .where(
            Transfer.player_id == player_id,
            Transfer.transfer_date <= eval_date,
        )
        .order_by(desc(Transfer.transfer_date), desc(Transfer.created_at))
    )
    transfers = list((await session.execute(t_stmt)).scalars().all())

    total_transfers = len(transfers)
    last_transfer = transfers[0] if transfers else None

    current_club_id = last_transfer.to_club_id if last_transfer else None
    current_club_name = last_transfer.to_club.name if (last_transfer and last_transfer.to_club) else None

    # 3. Query role profile strictly on or before eval_datetime
    role_stmt = (
        select(PlayerRoleProfile)
        .where(
            PlayerRoleProfile.player_id == player_id,
            PlayerRoleProfile.as_of <= eval_datetime,
        )
        .order_by(desc(PlayerRoleProfile.as_of))
        .limit(1)
    )
    role_prof = (await session.execute(role_stmt)).scalar_one_or_none()
    role_archetype = role_prof.primary_archetype if role_prof else None

    # 4. Query contribution snapshot strictly on or before eval_datetime
    contrib_stmt = (
        select(PlayerContributionSnapshot)
        .where(
            PlayerContributionSnapshot.player_id == player_id,
            PlayerContributionSnapshot.as_of <= eval_datetime,
        )
        .order_by(desc(PlayerContributionSnapshot.as_of))
        .limit(1)
    )
    contrib_snap = (await session.execute(contrib_stmt)).scalar_one_or_none()

    contrib_scores = contrib_snap.dimension_scores if contrib_snap else {}
    sample_mins = contrib_snap.sample_minutes if contrib_snap else 0
    sample_matches = contrib_snap.sample_matches if contrib_snap else 0

    return MarketContextResponse(
        player_id=player.id,
        as_of=eval_datetime,
        age_at_as_of=age_at_as_of,
        position_group=pos_group,
        primary_position=player.primary_position,
        current_club_id=current_club_id,
        current_club_name=current_club_name,
        role_archetype=role_archetype,
        contribution_scores=contrib_scores,
        sample_minutes=sample_mins,
        sample_matches=sample_matches,
        total_career_transfers=total_transfers,
        last_transfer_date=last_transfer.transfer_date if last_transfer else None,
        last_transfer_fee_eur=last_transfer.fee_eur_normalized if last_transfer else None,
        last_fee_status=last_transfer.fee_status if last_transfer else None,
    )
