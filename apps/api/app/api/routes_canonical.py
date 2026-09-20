from __future__ import annotations

from datetime import date, datetime, timezone
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
    CompetitionSeason,
    Match,
    MatchTeam,
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


class ClubSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str | None = None
    country: str
    logo_url: str | None = None


class MatchTeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    club_id: uuid.UUID
    opponent_club_id: uuid.UUID
    is_home: bool
    result: str | None = None
    goals_for: int | None = None
    goals_against: int | None = None
    points: int | None = None


class MatchScoreResponse(BaseModel):
    home: int | None = None
    away: int | None = None
    halftime_home: int | None = None
    halftime_away: int | None = None
    fulltime_home: int | None = None
    fulltime_away: int | None = None
    extratime_home: int | None = None
    extratime_away: int | None = None
    penalty_home: int | None = None
    penalty_away: int | None = None


class MatchListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    provider_fixture_id: str | None = None
    competition_season_id: uuid.UUID
    date: datetime
    status: str
    status_detail: str | None = None
    round: str | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    home_club_id: uuid.UUID
    home_club_name: str | None = None
    away_club_id: uuid.UUID
    away_club_name: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    winner_club_id: uuid.UUID | None = None


class MatchDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    provider_fixture_id: str | None = None
    competition_season_id: uuid.UUID
    date: datetime
    status: str
    status_detail: str | None = None
    round: str | None = None
    stage: str | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    referee: str | None = None
    home_club: ClubSummaryResponse
    away_club: ClubSummaryResponse
    winner_club_id: uuid.UUID | None = None
    score: MatchScoreResponse
    teams: list[MatchTeamResponse] = []
    snapshot_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


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


@router.get("/matches", response_model=list[MatchListResponse])
async def list_matches(
    competition_id: uuid.UUID | None = Query(None),
    season_id: uuid.UUID | None = Query(None),
    competition_season_id: uuid.UUID | None = Query(None),
    club_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[MatchListResponse]:
    stmt = (
        select(Match)
        .options(
            selectinload(Match.home_club),
            selectinload(Match.away_club),
            selectinload(Match.competition_season),
        )
        .order_by(Match.date.desc())
        .offset(offset)
        .limit(limit)
    )
    if competition_season_id:
        stmt = stmt.where(Match.competition_season_id == competition_season_id)
    if competition_id:
        stmt = stmt.join(CompetitionSeason, Match.competition_season_id == CompetitionSeason.id).where(
            CompetitionSeason.competition_id == competition_id
        )
    if season_id:
        stmt = stmt.join(CompetitionSeason, Match.competition_season_id == CompetitionSeason.id).where(
            CompetitionSeason.season_id == season_id
        )
    if club_id:
        stmt = stmt.where((Match.home_club_id == club_id) | (Match.away_club_id == club_id))
    if status:
        stmt = stmt.where(Match.status == status.upper())
    if date_from:
        stmt = stmt.where(Match.date >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(Match.date <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc))

    matches = (await session.execute(stmt)).scalars().all()
    results: list[MatchListResponse] = []
    for m in matches:
        results.append(
            MatchListResponse(
                id=m.id,
                provider=m.provider,
                provider_fixture_id=m.provider_fixture_id,
                competition_season_id=m.competition_season_id,
                date=m.date,
                status=m.status,
                status_detail=m.status_detail,
                round=m.round,
                venue_name=m.venue_name,
                venue_city=m.venue_city,
                home_club_id=m.home_club_id,
                home_club_name=m.home_club.name if m.home_club else None,
                away_club_id=m.away_club_id,
                away_club_name=m.away_club.name if m.away_club else None,
                home_score=m.home_score,
                away_score=m.away_score,
                winner_club_id=m.winner_club_id,
            )
        )
    return results


@router.get("/matches/{match_id}", response_model=MatchDetailResponse)
async def get_match(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MatchDetailResponse:
    stmt = (
        select(Match)
        .options(
            selectinload(Match.home_club),
            selectinload(Match.away_club),
            selectinload(Match.teams),
            selectinload(Match.competition_season),
        )
        .where(Match.id == match_id)
    )
    match = (await session.execute(stmt)).scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    score_resp = MatchScoreResponse(
        home=match.home_score,
        away=match.away_score,
        halftime_home=match.halftime_home_score,
        halftime_away=match.halftime_away_score,
        fulltime_home=match.fulltime_home_score,
        fulltime_away=match.fulltime_away_score,
        extratime_home=match.extratime_home_score,
        extratime_away=match.extratime_away_score,
        penalty_home=match.penalty_home_score,
        penalty_away=match.penalty_away_score,
    )

    teams_resp = [MatchTeamResponse.model_validate(t) for t in match.teams]

    return MatchDetailResponse(
        id=match.id,
        provider=match.provider,
        provider_fixture_id=match.provider_fixture_id,
        competition_season_id=match.competition_season_id,
        date=match.date,
        status=match.status,
        status_detail=match.status_detail,
        round=match.round,
        stage=match.stage,
        venue_name=match.venue_name,
        venue_city=match.venue_city,
        referee=match.referee,
        home_club=ClubSummaryResponse.model_validate(match.home_club),
        away_club=ClubSummaryResponse.model_validate(match.away_club),
        winner_club_id=match.winner_club_id,
        score=score_resp,
        teams=teams_resp,
        snapshot_id=match.snapshot_id,
        created_at=match.created_at,
        updated_at=match.updated_at,
    )


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
