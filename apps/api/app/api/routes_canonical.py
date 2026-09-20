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
    MatchEvent,
    MatchLineup,
    MatchStatistics,
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


class MatchEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    club_id: uuid.UUID
    club_name: str | None = None
    player_id: uuid.UUID | None = None
    player_name: str | None = None
    assist_player_id: uuid.UUID | None = None
    assist_player_name: str | None = None
    event_type: str
    event_detail: str | None = None
    minute: int
    extra_minute: int | None = None
    comments: str | None = None
    event_key: str
    provider_event_id: str | None = None
    snapshot_id: uuid.UUID | None = None
    created_at: datetime


class MatchLineupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    club_id: uuid.UUID
    club_name: str | None = None
    player_id: uuid.UUID
    player_name: str | None = None
    is_starter: bool
    jersey_number: int | None = None
    position: str | None = None
    formation_position: str | None = None
    formation: str | None = None
    is_captain: bool = False
    coach_name: str | None = None
    snapshot_id: uuid.UUID | None = None
    created_at: datetime


class MatchStatisticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    club_id: uuid.UUID
    club_name: str | None = None
    possession_pct: float | None = None
    shots_total: int | None = None
    shots_on_target: int | None = None
    shots_off_target: int | None = None
    blocked_shots: int | None = None
    shots_inside_box: int | None = None
    shots_outside_box: int | None = None
    fouls: int | None = None
    corners: int | None = None
    offsides: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    saves: int | None = None
    passes_total: int | None = None
    passes_accurate: int | None = None
    pass_accuracy_pct: float | None = None
    expected_goals: float | None = None
    free_kicks: int | None = None
    snapshot_id: uuid.UUID | None = None
    created_at: datetime


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


@router.get("/matches/{match_id}/events", response_model=list[MatchEventResponse])
async def get_match_events(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MatchEventResponse]:
    m_check = await session.execute(select(Match.id).where(Match.id == match_id))
    if m_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Match not found")

    stmt = (
        select(MatchEvent)
        .options(
            selectinload(MatchEvent.club),
            selectinload(MatchEvent.player),
            selectinload(MatchEvent.assist_player),
        )
        .where(MatchEvent.match_id == match_id)
        .order_by(MatchEvent.minute.asc(), MatchEvent.extra_minute.asc().nulls_first())
    )
    events = (await session.execute(stmt)).scalars().all()
    results: list[MatchEventResponse] = []
    for ev in events:
        results.append(
            MatchEventResponse(
                id=ev.id,
                match_id=ev.match_id,
                club_id=ev.club_id,
                club_name=ev.club.name if ev.club else None,
                player_id=ev.player_id,
                player_name=ev.player.name if ev.player else None,
                assist_player_id=ev.assist_player_id,
                assist_player_name=ev.assist_player.name if ev.assist_player else None,
                event_type=ev.event_type,
                event_detail=ev.event_detail,
                minute=ev.minute,
                extra_minute=ev.extra_minute,
                comments=ev.comments,
                event_key=ev.event_key,
                provider_event_id=ev.provider_event_id,
                snapshot_id=ev.snapshot_id,
                created_at=ev.created_at,
            )
        )
    return results


@router.get("/matches/{match_id}/lineups", response_model=list[MatchLineupResponse])
async def get_match_lineups(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MatchLineupResponse]:
    m_check = await session.execute(select(Match.id).where(Match.id == match_id))
    if m_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Match not found")

    stmt = (
        select(MatchLineup)
        .options(
            selectinload(MatchLineup.club),
            selectinload(MatchLineup.player),
        )
        .where(MatchLineup.match_id == match_id)
        .order_by(MatchLineup.club_id, MatchLineup.is_starter.desc(), MatchLineup.jersey_number.asc().nulls_last())
    )
    lineups = (await session.execute(stmt)).scalars().all()
    results: list[MatchLineupResponse] = []
    for lu in lineups:
        results.append(
            MatchLineupResponse(
                id=lu.id,
                match_id=lu.match_id,
                club_id=lu.club_id,
                club_name=lu.club.name if lu.club else None,
                player_id=lu.player_id,
                player_name=lu.player.name if lu.player else None,
                is_starter=lu.is_starter,
                jersey_number=lu.jersey_number,
                position=lu.position,
                formation_position=lu.formation_position,
                formation=lu.formation,
                is_captain=lu.is_captain,
                coach_name=lu.coach_name,
                snapshot_id=lu.snapshot_id,
                created_at=lu.created_at,
            )
        )
    return results


@router.get("/matches/{match_id}/statistics", response_model=list[MatchStatisticsResponse])
async def get_match_statistics(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[MatchStatisticsResponse]:
    m_check = await session.execute(select(Match.id).where(Match.id == match_id))
    if m_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Match not found")

    stmt = (
        select(MatchStatistics)
        .options(selectinload(MatchStatistics.club))
        .where(MatchStatistics.match_id == match_id)
        .order_by(MatchStatistics.club_id)
    )
    stats = (await session.execute(stmt)).scalars().all()
    results: list[MatchStatisticsResponse] = []
    for st in stats:
        results.append(
            MatchStatisticsResponse(
                id=st.id,
                match_id=st.match_id,
                club_id=st.club_id,
                club_name=st.club.name if st.club else None,
                possession_pct=st.possession_pct,
                shots_total=st.shots_total,
                shots_on_target=st.shots_on_target,
                shots_off_target=st.shots_off_target,
                blocked_shots=st.blocked_shots,
                shots_inside_box=st.shots_inside_box,
                shots_outside_box=st.shots_outside_box,
                fouls=st.fouls,
                corners=st.corners,
                offsides=st.offsides,
                yellow_cards=st.yellow_cards,
                red_cards=st.red_cards,
                saves=st.saves,
                passes_total=st.passes_total,
                passes_accurate=st.passes_accurate,
                pass_accuracy_pct=st.pass_accuracy_pct,
                expected_goals=st.expected_goals,
                free_kicks=st.free_kicks,
                snapshot_id=st.snapshot_id,
                created_at=st.created_at,
            )
        )
    return results


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
