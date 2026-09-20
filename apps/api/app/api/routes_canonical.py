from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import (
    Club,
    ClubIdentity,
    Competition,
    Player,
    PlayerIdentity,
    PlayerSeasonStats,
)
from app.db.session import get_session
from app.normalization.service import NormalizationService

router = APIRouter(prefix="/api/v1", tags=["canonical"])


class CompetitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country: str
    code: str | None = None
    type: str


class ClubIdentityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    provider_club_id: str
    confidence: float
    resolution_method: str


class ClubResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str | None = None
    country: str
    founded: int | None = None
    venue_name: str | None = None
    venue_capacity: int | None = None
    logo_url: str | None = None
    identities: list[ClubIdentityResponse] = []


class PlayerIdentityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    provider_player_id: str
    confidence: float
    resolution_method: str


class PlayerSeasonStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    club_id: uuid.UUID | None
    competition_season_id: uuid.UUID
    snapshot_id: uuid.UUID | None
    appearances: int
    lineups: int
    minutes: int
    position: str | None
    rating: float | None
    goals: int
    assists: int
    conceded: int


class PlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    first_name: str | None = None
    last_name: str | None = None
    nationality: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    primary_position: str | None = None
    photo_url: str | None = None
    identities: list[PlayerIdentityResponse] = []
    season_stats: list[PlayerSeasonStatsResponse] = []


@router.get("/competitions", response_model=list[CompetitionResponse])
async def list_competitions(
    session: AsyncSession = Depends(get_session),
) -> list[CompetitionResponse]:
    stmt = select(Competition).order_by(Competition.name)
    comps = (await session.execute(stmt)).scalars().all()
    return [CompetitionResponse.model_validate(c) for c in comps]


@router.get("/clubs", response_model=list[ClubResponse])
async def list_clubs(
    country: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> list[ClubResponse]:
    stmt = select(Club).options(selectinload(Club.identities)).order_by(Club.name)
    if country:
        stmt = stmt.where(Club.country == country)
    clubs = (await session.execute(stmt)).scalars().all()
    return [ClubResponse.model_validate(c) for c in clubs]


@router.get("/clubs/{club_id}", response_model=ClubResponse)
async def get_club(
    club_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ClubResponse:
    stmt = (
        select(Club)
        .options(selectinload(Club.identities))
        .where(Club.id == club_id)
    )
    club = (await session.execute(stmt)).scalar_one_or_none()
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return ClubResponse.model_validate(club)


@router.get("/players", response_model=list[PlayerResponse])
async def list_players(
    position: str | None = Query(None),
    nationality: str | None = Query(None),
    limit: int = Query(50, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[PlayerResponse]:
    stmt = (
        select(Player)
        .options(selectinload(Player.identities), selectinload(Player.season_stats))
        .order_by(Player.name)
        .limit(limit)
    )
    if position:
        stmt = stmt.where(Player.primary_position == position)
    if nationality:
        stmt = stmt.where(Player.nationality == nationality)
    players = (await session.execute(stmt)).scalars().all()
    return [PlayerResponse.model_validate(p) for p in players]


@router.get("/players/{player_id}", response_model=PlayerResponse)
async def get_player(
    player_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PlayerResponse:
    stmt = (
        select(Player)
        .options(selectinload(Player.identities), selectinload(Player.season_stats))
        .where(Player.id == player_id)
    )
    player = (await session.execute(stmt)).scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return PlayerResponse.model_validate(player)


@router.post("/normalization/snapshots/{snapshot_id}")
async def normalize_snapshot(
    snapshot_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = NormalizationService(session)
    try:
        result = await service.normalize_snapshot(snapshot_id)
        return {"status": "SUCCESS", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
