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
    PlayerMatchStats,
    PlayerSeasonStats,
)
from app.db.session import get_session
from app.features.registry import list_features
from app.features.schemas import (
    FeatureDefinitionResponse,
    FeatureSnapshotResponse,
    MatchContextFeaturesResponse,
)
from app.features.service import FeatureService
from app.normalization.service import NormalizationService
from app.roles.schemas import (
    PlayerComparisonResponse,
    RoleArchetypeResponse,
    RoleProfileResponse,
    SimilarPlayersResponse,
)
from app.roles.service import RoleService

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


class PlayerMatchStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    club_id: uuid.UUID
    club_name: str | None = None
    player_id: uuid.UUID
    player_name: str | None = None
    is_starter: bool | None = None
    is_substitute: bool | None = None
    is_captain: bool = False
    position: str | None = None
    jersey_number: int | None = None
    formation_position: str | None = None
    minutes: int | None = None
    rating: float | None = None
    goals: int | None = None
    assists: int | None = None
    shots_total: int | None = None
    shots_on_target: int | None = None
    offsides: int | None = None
    passes_total: int | None = None
    passes_key: int | None = None
    pass_accuracy: float | None = None
    tackles_total: int | None = None
    blocks: int | None = None
    interceptions: int | None = None
    duels_total: int | None = None
    duels_won: int | None = None
    dribbles_attempts: int | None = None
    dribbles_success: int | None = None
    dribbles_past: int | None = None
    fouls_drawn: int | None = None
    fouls_committed: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    penalties_won: int | None = None
    penalties_committed: int | None = None
    penalties_scored: int | None = None
    penalties_missed: int | None = None
    penalties_saved: int | None = None
    saves: int | None = None
    goals_conceded: int | None = None
    clean_sheet: bool | None = None
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


@router.get("/matches/{match_id}/player-stats", response_model=list[PlayerMatchStatsResponse])
@router.get("/matches/{match_id}/players", response_model=list[PlayerMatchStatsResponse])
async def get_match_player_stats(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[PlayerMatchStatsResponse]:
    m_check = await session.execute(select(Match.id).where(Match.id == match_id))
    if m_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Match not found")

    stmt = (
        select(PlayerMatchStats)
        .options(
            selectinload(PlayerMatchStats.club),
            selectinload(PlayerMatchStats.player),
        )
        .where(PlayerMatchStats.match_id == match_id)
        .order_by(
            PlayerMatchStats.club_id,
            PlayerMatchStats.is_starter.desc().nulls_last(),
            PlayerMatchStats.minutes.desc().nulls_last(),
            PlayerMatchStats.jersey_number.asc().nulls_last(),
        )
    )
    p_stats = (await session.execute(stmt)).scalars().all()
    results: list[PlayerMatchStatsResponse] = []
    for ps in p_stats:
        results.append(
            PlayerMatchStatsResponse(
                id=ps.id,
                match_id=ps.match_id,
                club_id=ps.club_id,
                club_name=ps.club.name if ps.club else None,
                player_id=ps.player_id,
                player_name=ps.player.name if ps.player else None,
                is_starter=ps.is_starter,
                is_substitute=ps.is_substitute,
                is_captain=ps.is_captain,
                position=ps.position,
                jersey_number=ps.jersey_number,
                formation_position=ps.formation_position,
                minutes=ps.minutes,
                rating=ps.rating,
                goals=ps.goals,
                assists=ps.assists,
                shots_total=ps.shots_total,
                shots_on_target=ps.shots_on_target,
                offsides=ps.offsides,
                passes_total=ps.passes_total,
                passes_key=ps.passes_key,
                pass_accuracy=ps.pass_accuracy,
                tackles_total=ps.tackles_total,
                blocks=ps.blocks,
                interceptions=ps.interceptions,
                duels_total=ps.duels_total,
                duels_won=ps.duels_won,
                dribbles_attempts=ps.dribbles_attempts,
                dribbles_success=ps.dribbles_success,
                dribbles_past=ps.dribbles_past,
                fouls_drawn=ps.fouls_drawn,
                fouls_committed=ps.fouls_committed,
                yellow_cards=ps.yellow_cards,
                red_cards=ps.red_cards,
                penalties_won=ps.penalties_won,
                penalties_committed=ps.penalties_committed,
                penalties_scored=ps.penalties_scored,
                penalties_missed=ps.penalties_missed,
                penalties_saved=ps.penalties_saved,
                saves=ps.saves,
                goals_conceded=ps.goals_conceded,
                clean_sheet=ps.clean_sheet,
                snapshot_id=ps.snapshot_id,
                created_at=ps.created_at,
            )
        )
    return results


@router.get("/players/{player_id}/matches", response_model=list[PlayerMatchStatsResponse])
async def get_player_match_history(
    player_id: uuid.UUID,
    club_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[PlayerMatchStatsResponse]:
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    stmt = (
        select(PlayerMatchStats)
        .options(
            selectinload(PlayerMatchStats.club),
            selectinload(PlayerMatchStats.player),
        )
        .where(PlayerMatchStats.player_id == player_id)
    )
    if club_id is not None:
        stmt = stmt.where(PlayerMatchStats.club_id == club_id)

    stmt = stmt.order_by(PlayerMatchStats.created_at.desc()).offset(offset).limit(limit)
    records = (await session.execute(stmt)).scalars().all()

    results: list[PlayerMatchStatsResponse] = []
    for ps in records:
        results.append(
            PlayerMatchStatsResponse(
                id=ps.id,
                match_id=ps.match_id,
                club_id=ps.club_id,
                club_name=ps.club.name if ps.club else None,
                player_id=ps.player_id,
                player_name=ps.player.name if ps.player else None,
                is_starter=ps.is_starter,
                is_substitute=ps.is_substitute,
                is_captain=ps.is_captain,
                position=ps.position,
                jersey_number=ps.jersey_number,
                formation_position=ps.formation_position,
                minutes=ps.minutes,
                rating=ps.rating,
                goals=ps.goals,
                assists=ps.assists,
                shots_total=ps.shots_total,
                shots_on_target=ps.shots_on_target,
                offsides=ps.offsides,
                passes_total=ps.passes_total,
                passes_key=ps.passes_key,
                pass_accuracy=ps.pass_accuracy,
                tackles_total=ps.tackles_total,
                blocks=ps.blocks,
                interceptions=ps.interceptions,
                duels_total=ps.duels_total,
                duels_won=ps.duels_won,
                dribbles_attempts=ps.dribbles_attempts,
                dribbles_success=ps.dribbles_success,
                dribbles_past=ps.dribbles_past,
                fouls_drawn=ps.fouls_drawn,
                fouls_committed=ps.fouls_committed,
                yellow_cards=ps.yellow_cards,
                red_cards=ps.red_cards,
                penalties_won=ps.penalties_won,
                penalties_committed=ps.penalties_committed,
                penalties_scored=ps.penalties_scored,
                penalties_missed=ps.penalties_missed,
                penalties_saved=ps.penalties_saved,
                saves=ps.saves,
                goals_conceded=ps.goals_conceded,
                clean_sheet=ps.clean_sheet,
                snapshot_id=ps.snapshot_id,
                created_at=ps.created_at,
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


@router.get("/features/registry", response_model=list[FeatureDefinitionResponse])
async def get_feature_registry(
    feature_set: str | None = Query(None, description="Filter by feature set e.g. player_match_v1"),
    entity_type: str | None = Query(None, description="Filter by entity type: player, team, match"),
) -> list[FeatureDefinitionResponse]:
    """Retrieves all registered feature definitions, calculation semantics, and leakage policies."""
    defs = list_features(feature_set=feature_set, entity_type=entity_type)
    return [FeatureDefinitionResponse.model_validate(d.to_dict()) for d in defs]


@router.get("/players/{player_id}/features", response_model=FeatureSnapshotResponse)
async def get_player_features(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Temporal cutoff (defaults to now or match date)"),
    match_id: uuid.UUID | None = Query(None, description="Optional target match for context"),
    session: AsyncSession = Depends(get_session),
) -> FeatureSnapshotResponse:
    """Computes or retrieves leakage-safe pre-match analytical features for a player."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    cutoff = as_of
    if cutoff is None and match_id is not None:
        m_check = await session.execute(select(Match.date).where(Match.id == match_id))
        cutoff = m_check.scalar_one_or_none()
    if cutoff is None:
        cutoff = datetime.now(timezone.utc)

    feature_service = FeatureService(session)
    try:
        snapshot = await feature_service.compute_player_features(
            player_id=player_id,
            as_of=cutoff,
            match_id=match_id,
            save=True,
        )
        await session.commit()
        return FeatureSnapshotResponse(
            id=snapshot.id,
            entity_type=snapshot.entity_type,
            entity_id=snapshot.entity_id,
            match_id=snapshot.match_id,
            feature_set=snapshot.feature_set,
            calculation_version=snapshot.calculation_version,
            as_of=snapshot.as_of,
            season_id=snapshot.season_id,
            competition_id=snapshot.competition_id,
            features=snapshot.features,
            provenance=snapshot.provenance,
            created_at=snapshot.created_at,
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/matches/{match_id}/features", response_model=MatchContextFeaturesResponse)
async def get_match_features(
    match_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff (defaults to match date)"),
    session: AsyncSession = Depends(get_session),
) -> MatchContextFeaturesResponse:
    """Computes pre-match context, team features, rest days, and opponent strength baselines."""
    m_check = await session.execute(select(Match.id).where(Match.id == match_id))
    if m_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Match not found")

    feature_service = FeatureService(session)
    try:
        result = await feature_service.compute_match_features(
            match_id=match_id,
            as_of=as_of,
            save=True,
        )
        await session.commit()
        return MatchContextFeaturesResponse(
            match_id=result["match_id"],
            as_of=result["as_of"],
            home_club_id=result["home_club_id"],
            away_club_id=result["away_club_id"],
            home_features=result["home_features"],
            away_features=result["away_features"],
            match_context=result["match_context"],
            provenance=result["provenance"],
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/role", response_model=RoleArchetypeResponse)
async def get_player_role_archetype(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for historical evaluation"),
    session: AsyncSession = Depends(get_session),
) -> RoleArchetypeResponse:
    """Returns human-readable role archetype classification derived from leakage-safe features."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    role_service = RoleService(session)
    try:
        archetype_summary = await role_service.get_archetype_summary(player_id, as_of)
        await session.commit()
        return archetype_summary
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/role-profile", response_model=RoleProfileResponse)
async def get_player_role_profile(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for historical evaluation"),
    session: AsyncSession = Depends(get_session),
) -> RoleProfileResponse:
    """Returns the continuous 9-dimension functional role profile and standardized feature vector."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    role_service = RoleService(session)
    try:
        profile = await role_service.get_role_profile(player_id, as_of)
        if not profile:
            profile = await role_service.compute_and_save_role_profile(player_id, as_of)
            await session.commit()
        return RoleProfileResponse(
            id=profile.id,
            player_id=profile.player_id,
            as_of=profile.as_of,
            feature_set_version=profile.feature_set_version,
            role_status=profile.role_status,
            sample_minutes=profile.sample_minutes,
            sample_matches=profile.sample_matches,
            position_group=profile.position_group,
            primary_archetype=profile.primary_archetype,
            secondary_archetype=profile.secondary_archetype,
            archetype_confidence=profile.archetype_confidence,
            profile_scores=profile.profile_scores,
            feature_vector=profile.feature_vector,
            provenance=profile.provenance,
            created_at=profile.created_at,
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/similar", response_model=SimilarPlayersResponse)
async def get_similar_players(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of similar players to return"),
    position_filter: str | None = Query(None, description="Filter by position group (GK, DEF, MID, ATT)"),
    min_minutes: int | None = Query(None, ge=0, description="Minimum sample minutes required"),
    session: AsyncSession = Depends(get_session),
) -> SimilarPlayersResponse:
    """Finds top-N multi-dimensionally similar players with explainable contribution breakdowns."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    role_service = RoleService(session)
    try:
        result = await role_service.find_similar_players(
            player_id=player_id,
            as_of=as_of,
            limit=limit,
            position_filter=position_filter,
            min_minutes=min_minutes,
        )
        await session.commit()
        return result
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/similarity/{other_id}", response_model=PlayerComparisonResponse)
async def compare_player_similarity(
    player_id: uuid.UUID,
    other_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> PlayerComparisonResponse:
    """Detailed head-to-head comparison between two players with explainable dimension deltas."""
    p1_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p1_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    p2_check = await session.execute(select(Player.id).where(Player.id == other_id))
    if p2_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Player {other_id} not found")

    role_service = RoleService(session)
    try:
        result = await role_service.compare_players(
            player_a_id=player_id,
            player_b_id=other_id,
            as_of=as_of,
        )
        await session.commit()
        return result
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

