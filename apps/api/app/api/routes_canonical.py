from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ml.valuation_registry import ModelNotServable
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
    Transfer,
)
from app.market.adapters.open_data import load_bronze_open_transfers
from app.market.comparables import ComparableTransferEngine
from app.market.context import build_player_market_context
from app.market.dataset import ValuationDatasetBuilder, ValuationTrainingRow
from app.market.merging import merge_multi_source_transfers
from app.market.readiness import MarketReadinessReport, evaluate_market_readiness
from app.market.schemas import (
    ComparableTransfersResponse,
    MarketBenchmarkResponse,
    MarketContextResponse,
    MarketCoverageResponse,
    TransferResponse,
    ValuationBaselineResponse,
    ValuationMLComparablesResponse,
    ValuationMLExplanationResponse,
    ValuationMLPredictionResponse,
    ValuationModelStatusResponse,
)
from app.market.ml.service import ValuationMLService
from app.market.universe import (
    compute_market_coverage_audit,
    get_temporal_transfers,
    transfer_db_to_normalized,
)
from app.market.valuation import BaselineValuationEngine, MarketBenchmarkEngine
from app.market.opportunities import (
    MarketOpportunitiesEngine,
    MarketOpportunitiesResponse,
)
from app.market.replacements import (
    ReplacementFinderEngine,
    ReplacementFinderRequest,
    ReplacementFinderResponse,
)
from app.market.risk import (
    TransferRiskEngine,
    TransferRiskProfile,
    TransferRiskBatchResponse,
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
from app.tactical.contexts import (
    STANDARD_TACTICAL_CONTEXTS,
    TacticalContext,
    build_custom_context,
    get_standard_context,
)
from app.tactical.schemas import (
    PlayerTacticalFitResponse,
    TacticalContextResponse,
    TacticalFitComparisonRequest,
    TacticalFitComparisonResponse,
    TacticalRequirementSchema,
)
from app.tactical.service import TacticalFitService

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
    mode: str = Query("composite", description="Similarity mode: composite, contribution, role, tactical, replacement"),
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
            mode=mode,
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
    mode: str = Query("composite", description="Similarity mode: composite, contribution, role, tactical, replacement"),
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
            mode=mode,
        )
        await session.commit()
        return result
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tactical/contexts", response_model=list[TacticalContextResponse])
async def list_tactical_contexts() -> list[TacticalContextResponse]:
    """Lists standard pre-configured tactical contexts and formations."""
    responses: list[TacticalContextResponse] = []
    for ctx in STANDARD_TACTICAL_CONTEXTS.values():
        responses.append(
            TacticalContextResponse(
                context_id=ctx.context_id,
                formation=ctx.formation,
                target_position=ctx.target_position,
                position_group=ctx.position_group.value,
                target_role=ctx.target_role,
                requirements=[
                    TacticalRequirementSchema(
                        dimension=r.dimension,
                        required_strength=r.required_strength,
                        importance_weight=r.importance_weight,
                        minimum_threshold=r.minimum_threshold,
                        description=r.description,
                    )
                    for r in ctx.requirements
                ],
                possession_style=ctx.possession_style,
                pressing_style=ctx.pressing_style,
                build_up_style=ctx.build_up_style,
                transition_style=ctx.transition_style,
                version=ctx.version,
                description=ctx.description,
            )
        )
    return responses


@router.get("/players/{player_id}/tactical-fit", response_model=PlayerTacticalFitResponse)
async def get_player_tactical_fit(
    player_id: uuid.UUID,
    context_id: str | None = Query(None, description="Standard context ID (e.g. 433_dm_deep_distributor)"),
    formation: str = Query("4-3-3", description="Formation (e.g. 4-3-3, 4-2-3-1)"),
    position: str | None = Query(None, description="Target position (e.g. DM, CM, RW, CB)"),
    role: str | None = Query(None, description="Target role archetype (e.g. Deep Distributor)"),
    team_id: uuid.UUID | None = Query(None, description="Optional team context club ID"),
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for historical evaluation"),
    session: AsyncSession = Depends(get_session),
) -> PlayerTacticalFitResponse:
    """Evaluates player tactical compatibility with a specified system, formation, and role."""
    p_check = await session.execute(select(Player).where(Player.id == player_id))
    player = p_check.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Resolve tactical context
    if context_id:
        context = get_standard_context(context_id)
        if not context:
            raise HTTPException(status_code=404, detail=f"Tactical context '{context_id}' not found.")
    else:
        target_pos = position or player.primary_position or "CM"
        target_role = role or "Deep Distributor"
        context = build_custom_context(formation=formation, target_position=target_pos, target_role=target_role)

    service = TacticalFitService(session)
    try:
        fit = await service.calculate_and_save_tactical_fit(
            player_id=player_id,
            context=context,
            as_of=as_of,
            team_id=team_id,
        )
        await session.commit()
        return PlayerTacticalFitResponse(
            id=fit.id,
            player_id=fit.player_id,
            player_name=player.name,
            team_id=fit.team_id,
            season_id=fit.season_id,
            tactical_context_id=fit.tactical_context_id,
            formation=fit.formation,
            target_position=fit.target_position,
            position_group=fit.position_group,
            target_role=fit.target_role,
            fit_score=fit.fit_score,
            position_fit=fit.position_fit,
            role_fit=fit.role_fit,
            dimension_fit=fit.dimension_fit,
            style_fit=fit.style_fit,
            contextual_fit=fit.contextual_fit,
            confidence=fit.confidence,
            fit_status=fit.fit_status,
            dimension_breakdown=fit.dimension_breakdown,
            why_fit=fit.why_fit,
            why_not_fit=fit.why_not_fit,
            calculation_version=fit.calculation_version,
            feature_set_version=fit.feature_set_version,
            as_of=fit.as_of,
            provenance=fit.provenance,
            created_at=fit.created_at,
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/tactical-fit/{context_id}", response_model=PlayerTacticalFitResponse)
async def get_player_tactical_fit_by_context(
    player_id: uuid.UUID,
    context_id: str,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> PlayerTacticalFitResponse:
    """Evaluates player tactical compatibility with a pre-configured tactical context."""
    return await get_player_tactical_fit(
        player_id=player_id,
        context_id=context_id,
        formation="4-3-3",
        position=None,
        role=None,
        team_id=None,
        as_of=as_of,
        session=session,
    )


@router.post("/tactical-fit/compare", response_model=TacticalFitComparisonResponse)
async def compare_players_tactical_fit(
    req: TacticalFitComparisonRequest,
    session: AsyncSession = Depends(get_session),
) -> TacticalFitComparisonResponse:
    """Head-to-head comparison of two players within the same tactical system."""
    p1_check = await session.execute(select(Player).where(Player.id == req.player_a_id))
    p1 = p1_check.scalar_one_or_none()
    if not p1:
        raise HTTPException(status_code=404, detail=f"Player A {req.player_a_id} not found")

    p2_check = await session.execute(select(Player).where(Player.id == req.player_b_id))
    p2 = p2_check.scalar_one_or_none()
    if not p2:
        raise HTTPException(status_code=404, detail=f"Player B {req.player_b_id} not found")

    if req.context_id:
        context = get_standard_context(req.context_id)
        if not context:
            raise HTTPException(status_code=404, detail=f"Tactical context '{req.context_id}' not found.")
    else:
        target_formation = req.formation or "4-3-3"
        target_pos = req.target_position or p1.primary_position or "CM"
        target_role = req.target_role or "Deep Distributor"
        context = build_custom_context(formation=target_formation, target_position=target_pos, target_role=target_role)

    service = TacticalFitService(session)
    try:
        comparison = await service.compare_players(
            player_a_id=req.player_a_id,
            player_b_id=req.player_b_id,
            context=context,
            as_of=req.as_of,
        )
        await session.commit()
        return comparison
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================
# PLAYER CONTRIBUTION & ACTION-VALUE FOUNDATION (PHASE 3.1)
# ============================================================

from app.actions.schemas import CanonicalActionResponse, PlayerActionsResponse  # noqa: E402
from app.contributions.schemas import PlayerContributionResponse  # noqa: E402
from app.contributions.service import ContributionService  # noqa: E402
from app.action_value.base import ActionValueResult  # noqa: E402
from app.action_value.action_impact import ActionImpactModel  # noqa: E402
from app.action_value.spatial_threat import SpatialThreatModel  # noqa: E402
from app.intelligence.schemas import (  # noqa: E402
    PlayerBenchmarksResponse,
    PlayerIntelligenceResponse,
    PlayerTrajectoryResponse,
)
from app.intelligence.service import PlayerIntelligenceService  # noqa: E402


@router.get("/players/{player_id}/contributions", response_model=PlayerContributionResponse)
async def get_player_contributions(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for historical evaluation"),
    session: AsyncSession = Depends(get_session),
) -> PlayerContributionResponse:
    """Returns multi-dimensional, position-aware player contribution profile with explicit confidence gates."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    service = ContributionService(session)
    try:
        profile = await service.get_player_contribution_profile(player_id, as_of)
        await session.commit()
        return profile
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/actions", response_model=PlayerActionsResponse)
async def get_player_actions(
    player_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200, description="Max actions to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_session),
) -> PlayerActionsResponse:
    """Returns paginated canonical actions recorded for a player."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    service = ContributionService(session)
    try:
        total, actions = await service.get_player_actions(player_id, limit=limit, offset=offset)
        await session.commit()
        return PlayerActionsResponse(
            player_id=player_id,
            total_actions=total,
            limit=limit,
            offset=offset,
            actions=[CanonicalActionResponse.model_validate(a) for a in actions],
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/action-values", response_model=ActionValueResult)
async def get_player_action_values(
    player_id: uuid.UUID,
    model: str = Query("impact", description="Model type: 'impact' (baseline) or 'spatial_threat'"),
    session: AsyncSession = Depends(get_session),
) -> ActionValueResult:
    """Evaluates action value for a player. Enforces data sufficiency gate for spatial models."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    service = ContributionService(session)
    try:
        _, actions = await service.get_player_actions(player_id, limit=500, offset=0)
        pms_res = await session.execute(
            select(PlayerMatchStats.minutes).where(PlayerMatchStats.player_id == player_id)
        )
        minutes = sum(m for m in pms_res.scalars().all() if m)

        val_model = SpatialThreatModel() if model == "spatial_threat" else ActionImpactModel()
        result = val_model.evaluate(player_id, actions, minutes)
        await session.commit()
        return result
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/intelligence", response_model=PlayerIntelligenceResponse)
async def get_player_intelligence(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for historical evaluation"),
    session: AsyncSession = Depends(get_session),
) -> PlayerIntelligenceResponse:
    """Retrieves or calculates point-in-time Player Intelligence Profile, Vectors, Benchmarks, and Explanations."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    service = PlayerIntelligenceService(session)
    try:
        intel = await service.get_player_intelligence(player_id=player_id, as_of=as_of)
        await session.commit()
        return intel
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/trajectory", response_model=PlayerTrajectoryResponse)
async def get_player_trajectory(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for historical evaluation"),
    session: AsyncSession = Depends(get_session),
) -> PlayerTrajectoryResponse:
    """Returns chronological match-by-match trajectory and seasonal trend without predictive simulation."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    service = PlayerIntelligenceService(session)
    try:
        traj = await service.get_player_trajectory(player_id=player_id, as_of=as_of)
        await session.commit()
        return traj
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/benchmarks", response_model=PlayerBenchmarksResponse)
async def get_player_benchmarks(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for historical evaluation"),
    session: AsyncSession = Depends(get_session),
) -> PlayerBenchmarksResponse:
    """Returns position-group peer benchmarks, z-scores, and percentiles."""
    p_check = await session.execute(select(Player.id).where(Player.id == player_id))
    if p_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Player not found")

    service = PlayerIntelligenceService(session)
    try:
        bm = await service.get_player_benchmarks(player_id=player_id, as_of=as_of)
        await session.commit()
        return bm
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ============================================================
# TRANSFER MARKET INTELLIGENCE & VALUATION (PHASE 4.1)
# ============================================================

@router.get("/players/{player_id}/transfers", response_model=list[TransferResponse])
async def get_player_transfers(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> list[TransferResponse]:
    """Returns canonical transfer history for a player with full fee semantics and quality states."""
    p_check = await session.execute(select(Player).where(Player.id == player_id))
    player = p_check.scalar_one_or_none()
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    transfers = await get_temporal_transfers(session, as_of=as_of, player_id=player_id)
    return [
        TransferResponse(
            id=t.id,
            player_id=t.player_id,
            player_name=player.name,
            from_club_id=t.from_club_id,
            from_club_name=t.from_club.name if t.from_club else None,
            to_club_id=t.to_club_id,
            to_club_name=t.to_club.name if t.to_club else None,
            transfer_date=t.transfer_date,
            season_id=t.season_id,
            competition_context=t.competition_context,
            transfer_type=t.transfer_type,
            fee_value=t.fee_value,
            fee_currency=t.fee_currency,
            fee_status=t.fee_status,
            fee_eur_normalized=t.fee_eur_normalized,
            is_loan=t.is_loan,
            is_permanent=t.is_permanent,
            option_type=t.option_type,
            source_provider=t.source_provider,
            source_record_id=t.source_record_id,
            data_quality_status=t.data_quality_status,
            quality_reasons=t.quality_reasons or [],
            created_at=t.created_at,
        )
        for t in transfers
    ]


@router.get("/players/{player_id}/market-context", response_model=MarketContextResponse)
async def get_player_market_context_endpoint(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> MarketContextResponse:
    """Returns leakage-safe market context representation for a player as of a target timestamp."""
    context = await build_player_market_context(session, player_id, as_of=as_of)
    if not context:
        raise HTTPException(status_code=404, detail="Player or market context not found")
    return context


@router.get("/players/{player_id}/transfer-comparables", response_model=ComparableTransfersResponse)
async def get_player_transfer_comparables(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    top_k: int = Query(5, ge=1, le=20),
    include_free: bool = Query(False, description="Include free transfers in candidate pool"),
    session: AsyncSession = Depends(get_session),
) -> ComparableTransfersResponse:
    """Returns deterministic comparable historical transactions with similarity scores and breakdown."""
    engine = ComparableTransferEngine()
    try:
        return await engine.find_comparables(
            session, player_id, as_of=as_of, top_k=top_k, include_free=include_free
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/players/{player_id}/valuation-baseline", response_model=ValuationBaselineResponse)
async def get_player_valuation_baseline(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> ValuationBaselineResponse:
    """Returns deterministic comparable-median baseline valuation, uncertainty range, and sufficiency status."""
    engine = BaselineValuationEngine()
    try:
        return await engine.compute_valuation_baseline(session, player_id, as_of=as_of)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/market/transfers", response_model=list[TransferResponse])
async def list_market_transfers(
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    position_group: str | None = Query(None, description="Filter by position group (GK, DEF, MID, ATT)"),
    fee_status: str | None = Query(None, description="Filter by fee status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[TransferResponse]:
    """Search and filter verified historical transfers across the market universe."""
    fee_statuses = [fee_status] if fee_status else None
    transfers = await get_temporal_transfers(
        session,
        as_of=as_of,
        position_group=position_group,
        fee_statuses=fee_statuses,
        limit=limit,
        offset=offset,
    )
    return [
        TransferResponse(
            id=t.id,
            player_id=t.player_id,
            player_name=t.player.name if t.player else None,
            from_club_id=t.from_club_id,
            from_club_name=t.from_club.name if t.from_club else None,
            to_club_id=t.to_club_id,
            to_club_name=t.to_club.name if t.to_club else None,
            transfer_date=t.transfer_date,
            season_id=t.season_id,
            competition_context=t.competition_context,
            transfer_type=t.transfer_type,
            fee_value=t.fee_value,
            fee_currency=t.fee_currency,
            fee_status=t.fee_status,
            fee_eur_normalized=t.fee_eur_normalized,
            is_loan=t.is_loan,
            is_permanent=t.is_permanent,
            option_type=t.option_type,
            source_provider=t.source_provider,
            source_record_id=t.source_record_id,
            data_quality_status=t.data_quality_status,
            quality_reasons=t.quality_reasons or [],
            created_at=t.created_at,
        )
        for t in transfers
    ]


@router.get("/market/benchmarks", response_model=MarketBenchmarkResponse)
async def get_market_benchmarks(
    position_group: str = Query("ALL", description="Position group cohort (ALL, GK, DEF, MID, ATT)"),
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> MarketBenchmarkResponse:
    """Returns sample-gated market fee percentiles and IQR dispersion for a position cohort."""
    pos = None if position_group.upper() == "ALL" else position_group
    transfers = await get_temporal_transfers(session, as_of=as_of, position_group=pos, limit=10000)
    clean_fees = [
        t.fee_eur_normalized
        for t in transfers
        if t.fee_eur_normalized is not None and t.fee_eur_normalized > 0 and t.is_permanent
    ]
    return MarketBenchmarkEngine.calculate_benchmarks(
        clean_fees, position_group=position_group, min_sample=3
    )


@router.get("/market/coverage", response_model=MarketCoverageResponse)
async def get_market_coverage(
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> MarketCoverageResponse:
    """Returns transparent audit of the historical transfer universe and readiness status for ML."""
    return await compute_market_coverage_audit(session, as_of=as_of)


@router.get("/market/readiness", response_model=MarketReadinessReport)
async def get_market_readiness(
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> MarketReadinessReport:
    """Returns deterministic Phase 4.1B model readiness report answering all 15 audit questions."""
    db_transfers = await get_temporal_transfers(session, as_of=as_of, limit=10000)
    open_transfers = load_bronze_open_transfers()
    all_normalized = [transfer_db_to_normalized(t) for t in db_transfers] + open_transfers
    merged = merge_multi_source_transfers(all_normalized)

    # Resolve player IDs present in database
    stmt = select(Player.id)
    res = await session.execute(stmt)
    intel_player_ids = {str(pid) for pid in res.scalars().all()}

    return evaluate_market_readiness(merged, player_intel_player_ids=intel_player_ids)


@router.get("/market/dataset-preview", response_model=list[ValuationTrainingRow])
async def get_market_dataset_preview(
    limit: int = Query(50, ge=1, le=500, description="Max preview rows"),
    as_of: datetime | None = Query(None, description="Optional temporal cutoff"),
    session: AsyncSession = Depends(get_session),
) -> list[ValuationTrainingRow]:
    """Returns preview of supervised learning training rows constructed by ValuationDatasetBuilder."""
    db_transfers = await get_temporal_transfers(session, as_of=as_of, limit=10000)
    open_transfers = load_bronze_open_transfers()
    all_normalized = [transfer_db_to_normalized(t) for t in db_transfers] + open_transfers
    merged = merge_multi_source_transfers(all_normalized)

    cutoff = as_of.date() if as_of else None
    builder = ValuationDatasetBuilder(as_of_date=cutoff)
    dataset = builder.build_dataset(merged)
    return dataset[:limit]


# -------------------------------------------------------------------------
# Phase 4.2: Machine Learning Transfer Valuation & Uncertainty Engine
# -------------------------------------------------------------------------

@router.get("/players/{player_id}/valuation", response_model=ValuationMLPredictionResponse)
async def get_player_ml_valuation(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional valuation as-of timestamp"),
    session: AsyncSession = Depends(get_session),
) -> ValuationMLPredictionResponse:
    """Estimates fair transfer value using the active Phase 4.2 ML valuation engine."""
    try:
        return await ValuationMLService.get_player_valuation(session, player_id, as_of=as_of)
    except ModelNotServable as e:  # Phase 18: refused by the authoritative registry
        return JSONResponse(e.body(player_id=str(player_id)))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/players/{player_id}/valuation/explanation", response_model=ValuationMLExplanationResponse)
async def get_player_valuation_explanation(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional valuation as-of timestamp"),
    session: AsyncSession = Depends(get_session),
) -> ValuationMLExplanationResponse:
    """Returns deterministic SHAP and non-causal feature attributions for valuation prediction."""
    try:
        return await ValuationMLService.get_player_valuation_explanation(session, player_id, as_of=as_of)
    except ModelNotServable as e:  # Phase 18: refused by the authoritative registry
        return JSONResponse(e.body(player_id=str(player_id)))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/players/{player_id}/valuation/comparables", response_model=ValuationMLComparablesResponse)
async def get_player_valuation_comparables(
    player_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional valuation as-of timestamp"),
    top_k: int = Query(5, ge=1, le=20, description="Max comparable transfers to return"),
    session: AsyncSession = Depends(get_session),
) -> ValuationMLComparablesResponse:
    """Returns model prediction alongside historical comparable transfers evidence."""
    try:
        return await ValuationMLService.get_player_valuation_comparables(
            session, player_id, as_of=as_of, top_k=top_k
        )
    except ModelNotServable as e:  # Phase 18: refused by the authoritative registry
        return JSONResponse(e.body(player_id=str(player_id)))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/market/model-status")
async def get_market_model_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Valuation model state from the authoritative registry (ops_model_registry)."""
    from app.ml.valuation_registry import VALUATION_DOMAIN
    from app.observability.system_health import check_model_health

    status = await check_model_health(session)
    status["models"] = [m for m in status["models"] if m["domain"] == VALUATION_DOMAIN]
    return status


# ============================================================
# MARKET OPPORTUNITIES (Phase 5B.1)
# ============================================================

@router.get("/market/opportunities", response_model=MarketOpportunitiesResponse)
async def get_market_opportunities(
    session: AsyncSession = Depends(get_session),
    position_group: str | None = Query(None, description="Filter by position group: GK, DEF, MID, ATT, ALL"),
    min_gap_pct: float | None = Query(None, description="Minimum absolute value gap percentage (e.g. 0.15 for 15%)"),
    opportunity_class: str | None = Query(None, description="Filter by class: UNDERVALUED, FAIRLY_VALUED, PREMIUM"),
    limit: int = Query(25, ge=1, le=100),
) -> MarketOpportunitiesResponse:
    """Identifies players with significant value gaps between estimated value and comparable market median."""
    engine = MarketOpportunitiesEngine()
    return await engine.scan_opportunities(
        session,
        position_group=position_group,
        min_gap_pct=min_gap_pct,
        opportunity_class=opportunity_class,
        limit=limit,
    )


# ============================================================
# REPLACEMENT FINDER (Phase 5B.2)
# ============================================================

@router.post("/market/replacements", response_model=ReplacementFinderResponse)
async def find_replacements(
    request: ReplacementFinderRequest,
    session: AsyncSession = Depends(get_session),
) -> ReplacementFinderResponse:
    """Ranks candidate replacements for a departing player or role gap."""
    engine = ReplacementFinderEngine()
    return await engine.find_replacements(session, request)


@router.get("/market/replacements/{player_id}", response_model=ReplacementFinderResponse)
async def find_player_replacements(
    player_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    max_age: float | None = Query(None),
    max_value_eur: float | None = Query(None),
    limit: int = Query(15, ge=1, le=50),
) -> ReplacementFinderResponse:
    """Finds replacement candidates for a specific player based on their role and profile."""
    request = ReplacementFinderRequest(
        target_player_id=player_id,
        max_age=max_age,
        max_value_eur=max_value_eur,
        limit=limit,
    )
    engine = ReplacementFinderEngine()
    return await engine.find_replacements(session, request)


# ============================================================
# TRANSFER RISK ASSESSMENT (Phase 5B.3)
# ============================================================

@router.get("/players/{player_id}/transfer-risk", response_model=TransferRiskProfile)
async def get_player_transfer_risk(
    player_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TransferRiskProfile:
    """Returns multi-dimensional transfer risk assessment for a specific player."""
    engine = TransferRiskEngine()
    return await engine.assess_player_risk(session, player_id)


@router.get("/market/risk", response_model=TransferRiskBatchResponse)
async def get_market_risk_batch(
    session: AsyncSession = Depends(get_session),
    position_group: str | None = Query(None, description="Filter by position group"),
    limit: int = Query(25, ge=1, le=100),
) -> TransferRiskBatchResponse:
    """Batch risk assessment across the player universe, sorted by highest risk first."""
    engine = TransferRiskEngine()
    return await engine.assess_batch(
        session,
        position_group=position_group,
        limit=limit,
    )


# ============================================================
# SQUAD INTELLIGENCE & TRANSFER SIMULATION (Phase 5A)
# ============================================================
from app.squad.schemas import (  # noqa: E402
    SquadAnalysisResponse,
    SquadBuildRequest,
    TransferSimulationRequest,
    TransferSimulationResponse,
)
from app.squad.service import SquadService  # noqa: E402
from app.squad.simulator import TransferSimulator  # noqa: E402


@router.get("/squads/build", response_model=SquadAnalysisResponse)
async def build_squad_get(
    club_id: uuid.UUID | None = Query(None, description="Optional club ID to filter squad"),
    formation: str = Query("4-3-3", description="Formation: 4-3-3, 4-2-3-1, 3-5-2"),
    session: AsyncSession = Depends(get_session),
) -> SquadAnalysisResponse:
    """Builds and analyzes squad formation structure, role coverage, and depth risk."""
    service = SquadService(session)
    req = SquadBuildRequest(club_id=club_id, formation=formation)
    return await service.analyze_squad(req)


@router.post("/squads/analyze", response_model=SquadAnalysisResponse)
async def analyze_squad_post(
    request: SquadBuildRequest,
    session: AsyncSession = Depends(get_session),
) -> SquadAnalysisResponse:
    """Analyzes a custom or club squad roster against formation requirements."""
    service = SquadService(session)
    return await service.analyze_squad(request)


@router.post("/squads/simulate-transfer", response_model=TransferSimulationResponse)
async def simulate_transfer(
    request: TransferSimulationRequest,
    session: AsyncSession = Depends(get_session),
) -> TransferSimulationResponse:
    """Models prospective incoming and outgoing transfers on squad health, quality, and depth."""
    simulator = TransferSimulator(session)
    return await simulator.simulate_transfer(request)


@router.post("/scenarios/transfer", response_model=TransferSimulationResponse)
async def simulate_scenario_transfer(
    request: TransferSimulationRequest,
    session: AsyncSession = Depends(get_session),
) -> TransferSimulationResponse:
    """Scenario Lab: models roster change hypotheses with before/after impact attribution."""
    simulator = TransferSimulator(session)
    return await simulator.simulate_transfer(request)


# ============================================================
# MATCH PREDICTION & CALIBRATION ENGINE (Phase 6)
# ============================================================


# Phase 18 (R8): match predictions come only from the authoritative registry
# and a verified artifact (app.phase17.model_ops.infer_match). The previous
# service answered from five hand-typed weights; it is no longer reachable.

@router.get("/matches/{match_id}/prediction")
async def get_match_prediction(
    match_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Past cutoff for a labelled historical replay; omit for a live pre-match request"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Served only through registry gates; refusals carry their status and reasons."""
    from app.api.routes_phase17 import inference_dict
    from app.phase17.model_ops import MODE_LIVE, MODE_REPLAY, infer_match

    row = await infer_match(session, match_id, as_of=as_of, mode=MODE_REPLAY if as_of else MODE_LIVE)
    await session.commit()
    return inference_dict(row)


@router.get("/matches/{match_id}/prediction/explanation")
async def get_match_prediction_explanation(
    match_id: uuid.UUID,
    as_of: datetime | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Coefficient x standardised-feature contributions of the served model
    (non-causal). No explanation exists for a refused request."""
    from app.phase17.model_ops import MODE_LIVE, MODE_REPLAY, infer_match

    row = await infer_match(session, match_id, as_of=as_of, mode=MODE_REPLAY if as_of else MODE_LIVE)
    await session.commit()
    return {"status": row.status, "reasons": row.reasons,
            "explanation": (row.output or {}).get("explanation") if row.status == "SERVED" else None}


@router.get("/matches/{match_id}/prediction/history")
async def get_match_prediction_history(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Every inference ever logged for this fixture (immutable log), served or refused."""
    from app.api.routes_phase17 import inference_dict
    from app.db.models.operations import InferenceLog

    rows = (await session.execute(select(InferenceLog).where(InferenceLog.subject_id == str(match_id))
                                  .order_by(InferenceLog.created_at.asc()))).scalars().all()
    return {"match_id": str(match_id), "inferences": [inference_dict(r) for r in rows]}


@router.get("/prediction/model-status")
async def get_prediction_model_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Match-model state from the authoritative registry (ops_model_registry)."""
    from app.observability.system_health import check_model_health

    status = await check_model_health(session)
    status["models"] = [m for m in status["models"] if m["domain"] == "match_outcome"]
    return status


# ============================================================
# UNIFIED DECISION INTELLIGENCE & RECRUITMENT ENGINE (Phase 7)
# ============================================================
from app.decisions.schemas import (  # noqa: E402
    CandidateComparisonRequest,
    CandidateComparisonResponse,
    DecisionAssessment,
    EvidenceGraphResponse,
    RecruitmentTargetRequest,
    RecruitmentTargetResponse,
    ReplacementDecisionRequest,
    ReplacementDecisionResponse,
    TransferScenarioDecisionRequest,
    TransferScenarioDecisionResponse,
)
from app.decisions.service import UnifiedDecisionService  # noqa: E402


@router.get("/decisions/recruitment", response_model=RecruitmentTargetResponse)
async def get_recruitment_targets(
    target_position: str = Query("MF", description="Target position (GK, DEF, MID, ATT, etc.)"),
    formation: str = Query("4-3-3", description="Formation: 4-3-3, 4-2-3-1, 3-5-2"),
    target_role: str | None = Query(None, description="Optional target role"),
    budget_eur: float | None = Query(None, description="Optional budget ceiling in EUR"),
    risk_tolerance: str = Query("MEDIUM", description="Risk tolerance: LOW, MEDIUM, HIGH, ALL"),
    limit: int = Query(15, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> RecruitmentTargetResponse:
    """Deterministic recruitment target evaluation across multi-dimensional evidence."""
    service = UnifiedDecisionService(session)
    req = RecruitmentTargetRequest(
        target_position=target_position,
        formation=formation,
        target_role=target_role,
        budget_eur=budget_eur,
        risk_tolerance=risk_tolerance,
        limit=limit,
    )
    return await service.analyze_recruitment_targets(req)


@router.post("/decisions/recruitment/analyze", response_model=RecruitmentTargetResponse)
async def analyze_recruitment_targets_post(
    request: RecruitmentTargetRequest,
    session: AsyncSession = Depends(get_session),
) -> RecruitmentTargetResponse:
    """Advanced recruitment target evaluation with structured multi-constraint body."""
    service = UnifiedDecisionService(session)
    return await service.analyze_recruitment_targets(request)


@router.post("/decisions/replacement", response_model=ReplacementDecisionResponse)
async def analyze_player_replacement(
    request: ReplacementDecisionRequest,
    session: AsyncSession = Depends(get_session),
) -> ReplacementDecisionResponse:
    """Dedicated replacement intelligence connecting player intelligence, similarity, tactical fit, market, and risk."""
    service = UnifiedDecisionService(session)
    try:
        return await service.analyze_replacement(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Replacement error: {str(exc)}") from exc


@router.post("/decisions/transfer-scenario", response_model=TransferScenarioDecisionResponse)
async def analyze_transfer_scenario(
    request: TransferScenarioDecisionRequest,
    session: AsyncSession = Depends(get_session),
) -> TransferScenarioDecisionResponse:
    """Evaluates multi-player roster changes against squad depth, finances, risk, and match forecast."""
    service = UnifiedDecisionService(session)
    try:
        return await service.simulate_transfer_scenario(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scenario error: {str(exc)}") from exc


@router.post("/decisions/compare", response_model=CandidateComparisonResponse)
async def compare_candidates(
    request: CandidateComparisonRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateComparisonResponse:
    """Side-by-side comparison of candidate targets across all 6 analytical dimensions."""
    service = UnifiedDecisionService(session)
    return await service.compare_candidates(request)


@router.get("/decisions/{decision_id}", response_model=DecisionAssessment)
async def get_decision_by_id(
    decision_id: uuid.UUID,
) -> DecisionAssessment:
    """Retrieves an evaluated decision assessment snapshot and provenance."""
    service = UnifiedDecisionService()
    try:
        return service.get_decision(decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/decisions/{decision_id}/evidence", response_model=EvidenceGraphResponse)
async def get_decision_evidence_graph(
    decision_id: uuid.UUID,
) -> EvidenceGraphResponse:
    """Retrieves the traceable evidence DAG for a previously evaluated decision assessment."""
    service = UnifiedDecisionService()
    try:
        return service.get_decision_evidence(decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



