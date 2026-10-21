from __future__ import annotations

from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
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
    PlayerRoleProfile,
    PlayerSeasonStats,
    Season,
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
    """Season statistics for one player.

    The metric fields are nullable: a statistic the provider never reported is
    unknown (null), never zero. Clients must treat null as "not measured".
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    club_id: uuid.UUID | None
    competition_season_id: uuid.UUID
    snapshot_id: uuid.UUID | None
    appearances: int | None
    lineups: int | None
    minutes: int | None
    position: str | None
    rating: float | None
    goals: int | None
    assists: int | None
    conceded: int | None


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


class PlayerPageResponse(BaseModel):
    """Paginated player result. `total` is the count of matching records
    before pagination, never the size of the current page."""

    items: list[PlayerResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool


class PlayerFacetsResponse(BaseModel):
    nationalities: list[str]
    positions: list[str]
    total_players: int


class BatchRoleItem(BaseModel):
    """One sampled player's latest persisted role classification."""

    player_id: uuid.UUID
    player_name: str
    primary_position: str | None = None
    role_status: str = "NOT_CLASSIFIED"
    position_group: str | None = None
    primary_archetype: str | None = None
    secondary_archetype: str | None = None
    archetype_confidence: float | None = None
    sample_minutes: int | None = None
    sample_matches: int | None = None
    as_of: datetime | None = None


class RoleCoverageSummary(BaseModel):
    qualified_profiles: int
    insufficient_profiles: int
    total_players: int


class BatchRoleResponse(BaseModel):
    items: list[BatchRoleItem]
    requested: int
    returned: int
    classified: int
    insufficient: int
    not_classified: int
    coverage: RoleCoverageSummary


class PlayerCompetitionCoverage(BaseModel):
    competition: str
    season: str
    players: int


class PlayerCoverageResponse(BaseModel):
    canonical_players: int
    provider_mappings: dict[str, int]
    unique_mapped_players_by_provider: dict[str, int]
    players_with_season_stats: int
    players_with_club_association: int
    players_missing_identity: int
    players_missing_position: int
    duplicate_provider_ids: int
    by_competition_season: list[PlayerCompetitionCoverage]
    latest_player_ingestion: dict[str, Any]
    ingestion_completeness: dict[str, Any]
    generated_at: str


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
    competition_name: str | None = None
    season_name: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    winner_club_id: uuid.UUID | None = None


class MatchPageResponse(BaseModel):
    """Server-side paginated fixture list with a true matching total."""

    items: list[MatchListResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool


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


_PLAYER_POSITION_ALIASES: dict[str, tuple[str, ...]] = {
    "gk": ("goalkeeper",),
    "goalkeeper": ("goalkeeper",),
    "d": ("defender",),
    "defender": ("defender",),
    "defence": ("defender",),
    "defense": ("defender",),
    "m": ("midfielder",),
    "midfielder": ("midfielder",),
    "f": ("attacker", "forward", "winger", "striker"),
    "attacker": ("attacker", "forward", "winger", "striker"),
    "forward": ("attacker", "forward", "winger", "striker"),
    "striker": ("attacker", "forward", "winger", "striker"),
    "winger": ("attacker", "forward", "winger", "striker"),
}

_PLAYER_SORT_COLUMNS = {
    "name": Player.name,
    "nationality": Player.nationality,
    "date_of_birth": Player.date_of_birth,
    "position": Player.primary_position,
    "created_at": Player.created_at,
}


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so a search for `%` stays a search for `%`."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _player_filters(
    *,
    q: str | None,
    position: str | None,
    nationality: str | None,
    club_id: uuid.UUID | None,
    competition_season_id: uuid.UUID | None,
) -> list[Any]:
    filters: list[Any] = []
    if q and q.strip():
        filters.append(Player.name.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
    if position and position.strip():
        terms = _PLAYER_POSITION_ALIASES.get(
            position.strip().lower(), (position.strip().lower(),)
        )
        filters.append(func.lower(Player.primary_position).in_(terms))
    if nationality and nationality.strip():
        filters.append(func.lower(Player.nationality) == nationality.strip().lower())
    if club_id is not None:
        filters.append(
            Player.id.in_(
                select(PlayerSeasonStats.player_id).where(
                    PlayerSeasonStats.club_id == club_id
                )
            )
        )
    if competition_season_id is not None:
        filters.append(
            Player.id.in_(
                select(PlayerSeasonStats.player_id).where(
                    PlayerSeasonStats.competition_season_id == competition_season_id
                )
            )
        )
    return filters


@router.get("/players/search", response_model=PlayerPageResponse)
async def search_players(
    q: str | None = Query(None, max_length=128),
    position: str | None = Query(None, max_length=64),
    nationality: str | None = Query(None, max_length=64),
    club_id: uuid.UUID | None = Query(None),
    competition_season_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1, le=1000),
    sort_by: Literal[
        "name", "nationality", "date_of_birth", "position", "created_at"
    ] = "name",
    sort_dir: Literal["asc", "desc"] = "asc",
    session: AsyncSession = Depends(get_session),
) -> PlayerPageResponse:
    """Server-side paginated player search.

    Filters are applied before counting and pagination, so `total` is the
    number of matching canonical players — not the size of this page.
    """
    settings = get_settings()
    size = page_size or settings.players_default_page_size
    if size > settings.players_max_page_size:
        raise HTTPException(
            status_code=422,
            detail=f"page_size must be <= {settings.players_max_page_size}",
        )

    filters = _player_filters(
        q=q,
        position=position,
        nationality=nationality,
        club_id=club_id,
        competition_season_id=competition_season_id,
    )

    total = (
        await session.execute(select(func.count(Player.id)).where(*filters))
    ).scalar_one()

    sort_column = _PLAYER_SORT_COLUMNS[sort_by]
    order = sort_column.desc() if sort_dir == "desc" else sort_column.asc()
    stmt = (
        select(Player)
        .options(selectinload(Player.identities), selectinload(Player.season_stats))
        .where(*filters)
        .order_by(order.nulls_last(), Player.id.asc())
        .offset((page - 1) * size)
        .limit(size)
    )
    players = (await session.execute(stmt)).scalars().all()
    total_pages = math.ceil(total / size) if total else 0

    return PlayerPageResponse(
        items=[PlayerResponse.model_validate(p) for p in players],
        total=total,
        page=page,
        page_size=size,
        total_pages=total_pages,
        has_next=page < total_pages,
    )


@router.get("/players/facets", response_model=PlayerFacetsResponse)
async def player_facets(
    session: AsyncSession = Depends(get_session),
) -> PlayerFacetsResponse:
    """Distinct filter values computed from the database, not a page of rows."""
    nationalities = (
        await session.execute(
            select(Player.nationality)
            .where(Player.nationality.is_not(None))
            .distinct()
            .order_by(Player.nationality)
        )
    ).scalars().all()
    positions = (
        await session.execute(
            select(Player.primary_position)
            .where(Player.primary_position.is_not(None))
            .distinct()
            .order_by(Player.primary_position)
        )
    ).scalars().all()
    total = (await session.execute(select(func.count(Player.id)))).scalar_one()
    return PlayerFacetsResponse(
        nationalities=[n for n in nationalities if n],
        positions=[p for p in positions if p],
        total_players=total,
    )


@router.get("/players/roles", response_model=BatchRoleResponse)
async def batch_player_roles(
    ids: str | None = Query(
        None, description="comma-separated player UUIDs (max 100); omit to page the canonical index"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> BatchRoleResponse:
    """Batch role classifications, replacing one HTTP request per player.

    Reads the latest persisted `player_role_profiles` row per player. A player
    without a profile is reported as `NOT_CLASSIFIED`; nothing is computed or
    invented here. Coverage is stated over the whole canonical index so the
    page can distinguish "sampled" from "classified".
    """
    requested_ids: list[uuid.UUID] = []
    if ids:
        for raw in ids.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                requested_ids.append(uuid.UUID(raw))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"invalid player id: {raw}") from exc
        if len(requested_ids) > 100:
            raise HTTPException(status_code=422, detail="at most 100 ids per request")
        requested_ids = list(dict.fromkeys(requested_ids))

    if requested_ids:
        players = (
            await session.execute(
                select(Player).where(Player.id.in_(requested_ids)).order_by(Player.name, Player.id)
            )
        ).scalars().all()
    else:
        players = (
            await session.execute(
                select(Player)
                .order_by(Player.name, Player.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()

    player_ids = [p.id for p in players]
    profile_rows = []
    if player_ids:
        profile_rows = list(
            (
                await session.execute(
                    select(PlayerRoleProfile)
                    .where(PlayerRoleProfile.player_id.in_(player_ids))
                    .order_by(PlayerRoleProfile.player_id, PlayerRoleProfile.as_of.desc())
                )
            ).scalars().all()
        )
    latest: dict[uuid.UUID, PlayerRoleProfile] = {}
    for profile in profile_rows:
        current = latest.get(profile.player_id)
        if current is None:
            latest[profile.player_id] = profile
            continue
        # Prefer a qualified classification over a newer insufficient row;
        # otherwise the page reports 0 classified while qualified profiles exist.
        profile_qualified = profile.role_status == "QUALIFIED"
        current_qualified = current.role_status == "QUALIFIED"
        if profile_qualified and not current_qualified:
            latest[profile.player_id] = profile
        elif profile_qualified == current_qualified and profile.as_of > current.as_of:
            latest[profile.player_id] = profile

    items: list[BatchRoleItem] = []
    classified = insufficient = not_classified = 0
    for player in players:
        profile = latest.get(player.id)
        if profile is None:
            not_classified += 1
            items.append(
                BatchRoleItem(player_id=player.id, player_name=player.name, primary_position=player.primary_position)
            )
            continue
        if profile.role_status == "QUALIFIED" and profile.primary_archetype:
            classified += 1
        else:
            insufficient += 1
        items.append(
            BatchRoleItem(
                player_id=player.id,
                player_name=player.name,
                primary_position=player.primary_position,
                role_status=profile.role_status,
                position_group=profile.position_group,
                primary_archetype=profile.primary_archetype,
                secondary_archetype=profile.secondary_archetype,
                archetype_confidence=profile.archetype_confidence,
                sample_minutes=profile.sample_minutes,
                sample_matches=profile.sample_matches,
                as_of=profile.as_of,
            )
        )

    qualified_profiles = (
        await session.execute(
            select(func.count(func.distinct(PlayerRoleProfile.player_id))).where(
                PlayerRoleProfile.role_status == "QUALIFIED",
                PlayerRoleProfile.primary_archetype.is_not(None),
            )
        )
    ).scalar_one()
    # Count players that have any profile but no qualified one; counting
    # non-qualified rows would also count players who now have a qualified
    # season profile alongside an older insufficient row.
    profiled_players = (
        await session.execute(
            select(func.count(func.distinct(PlayerRoleProfile.player_id)))
        )
    ).scalar_one()
    insufficient_profiles = max(0, profiled_players - qualified_profiles)
    total_players = (await session.execute(select(func.count(Player.id)))).scalar_one()

    return BatchRoleResponse(
        items=items,
        requested=len(requested_ids) if requested_ids else len(players),
        returned=len(items),
        classified=classified,
        insufficient=insufficient,
        not_classified=not_classified,
        coverage=RoleCoverageSummary(
            qualified_profiles=qualified_profiles,
            insufficient_profiles=insufficient_profiles,
            total_players=total_players,
        ),
    )


@router.get("/players/coverage", response_model=PlayerCoverageResponse)
async def player_coverage(
    session: AsyncSession = Depends(get_session),
) -> PlayerCoverageResponse:
    """Measured canonical player coverage and the latest ingestion state.

    Nothing here is inferred from a single successful request: page counts,
    the declared provider total and the completed pages are reported
    separately, and completeness is only COMPLETE when they agree.
    """
    from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun

    canonical_players = (
        await session.execute(select(func.count(Player.id)))
    ).scalar_one()

    provider_rows = (
        await session.execute(
            select(
                PlayerIdentity.provider,
                func.count(PlayerIdentity.id),
                func.count(func.distinct(PlayerIdentity.player_id)),
            ).group_by(PlayerIdentity.provider)
        )
    ).all()
    provider_mappings = {row[0]: row[1] for row in provider_rows}
    unique_mapped = {row[0]: row[2] for row in provider_rows}

    players_with_stats = (
        await session.execute(
            select(func.count(func.distinct(PlayerSeasonStats.player_id)))
        )
    ).scalar_one()
    players_with_club = (
        await session.execute(
            select(func.count(Player.id)).where(Player.club_id.is_not(None))
        )
    ).scalar_one()
    players_missing_identity = (
        await session.execute(
            select(func.count(Player.id)).where(
                ~select(PlayerIdentity.id)
                .where(PlayerIdentity.player_id == Player.id)
                .exists()
            )
        )
    ).scalar_one()
    players_missing_position = (
        await session.execute(
            select(func.count(Player.id)).where(Player.primary_position.is_(None))
        )
    ).scalar_one()
    duplicate_provider_ids = (
        await session.execute(
            select(func.count()).select_from(
                select(PlayerIdentity.provider, PlayerIdentity.provider_player_id)
                .group_by(PlayerIdentity.provider, PlayerIdentity.provider_player_id)
                .having(func.count(PlayerIdentity.id) > 1)
                .subquery()
            )
        )
    ).scalar_one()

    competition_rows = (
        await session.execute(
            select(
                Competition.name,
                Season.name,
                func.count(func.distinct(PlayerSeasonStats.player_id)),
            )
            .join(
                CompetitionSeason,
                CompetitionSeason.id == PlayerSeasonStats.competition_season_id,
            )
            .join(Competition, Competition.id == CompetitionSeason.competition_id)
            .join(Season, Season.id == CompetitionSeason.season_id)
            .group_by(Competition.name, Season.name)
            .order_by(Competition.name, Season.name)
        )
    ).all()

    runs = (
        await session.execute(
            select(IngestionRun, DataSource.name)
            .join(DataSource, DataSource.id == IngestionRun.data_source_id)
            .where(IngestionRun.endpoint == "players")
            .order_by(
                func.coalesce(IngestionRun.finished_at, IngestionRun.started_at).desc()
            )
            .limit(500)
        )
    ).all()

    latest: dict[str, Any] = {
        "provider": None,
        "status": "NEVER_RUN",
        "finished_at": None,
        "parameters": {},
        "record_count": None,
        "error": None,
    }
    pages_by_scope: dict[str, set[int]] = {}
    failures = 0
    plan_page_max: int | None = None
    plan_limit_message: str | None = None
    for run, provider in runs:
        params = dict(run.parameters or {})
        page = params.get("page")
        scope_params = {k: v for k, v in params.items() if k != "page"}
        scope_key = f"{provider}:{sorted(scope_params.items())}"
        status_value = getattr(run.status, "value", run.status)
        if page is not None and status_value in ("SUCCESS", "PARTIAL"):
            pages_by_scope.setdefault(scope_key, set()).add(int(page))
        if status_value == "FAILED":
            failures += 1
            if plan_page_max is None and run.error:
                plan_match = re.search(
                    r"maximum value of (\d+) for the Page parameter",
                    run.error,
                    flags=re.IGNORECASE,
                )
                if plan_match:
                    plan_page_max = int(plan_match.group(1))
                    plan_limit_message = run.error
        if latest["provider"] is None:
            latest = {
                "provider": provider,
                "status": status_value,
                "finished_at": (
                    run.finished_at.isoformat() if run.finished_at else None
                ),
                "parameters": params,
                "record_count": run.record_count,
                "error": run.error,
            }

    latest_scope_key = None
    latest_scope_params: dict[str, Any] = {}
    if latest["provider"] is not None:
        latest_params = latest["parameters"] or {}
        latest_scope_params = {
            k: v for k, v in latest_params.items() if k != "page"
        }
        latest_scope_key = f"{latest['provider']}:{sorted(latest_scope_params.items())}"

    # Completeness must be measured against the same provider/scope as the
    # latest run, not whichever snapshot happens to be newest globally.
    latest_success: IngestionRun | None = None
    if latest["provider"] is not None:
        for run, provider in runs:
            params = dict(run.parameters or {})
            scope_params = {k: v for k, v in params.items() if k != "page"}
            status_value = getattr(run.status, "value", run.status)
            if (
                provider == latest["provider"]
                and scope_params == latest_scope_params
                and status_value == "SUCCESS"
            ):
                latest_success = run
                break

    declared_total_pages: int | None = None
    declared_current_page: int | None = None
    if latest_success is not None:
        snapshot = (
            await session.execute(
                select(DataSnapshot)
                .where(DataSnapshot.ingestion_run_id == latest_success.id)
                .order_by(DataSnapshot.retrieved_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is not None:
            try:
                payload = json.loads(Path(snapshot.storage_location).read_bytes())
                paging = payload.get("paging") or {}
                if isinstance(paging, dict):
                    if isinstance(paging.get("total"), int):
                        declared_total_pages = paging["total"]
                    if isinstance(paging.get("current"), int):
                        declared_current_page = paging["current"]
            except (OSError, ValueError):
                declared_total_pages = None

    completed_pages = (
        len(pages_by_scope.get(latest_scope_key, set())) if latest_scope_key else 0
    )

    if (
        plan_page_max is not None
        and (declared_total_pages is None or completed_pages < declared_total_pages)
    ):
        completeness_status = "BLOCKED_BY_PLAN"
    elif declared_total_pages is None:
        completeness_status = "UNKNOWN" if completed_pages == 0 else "PARTIAL"
    elif completed_pages >= declared_total_pages:
        completeness_status = "COMPLETE"
    elif completed_pages == 0:
        completeness_status = "INCOMPLETE"
    else:
        completeness_status = "PARTIAL"

    return PlayerCoverageResponse(
        canonical_players=canonical_players,
        provider_mappings=provider_mappings,
        unique_mapped_players_by_provider=unique_mapped,
        players_with_season_stats=players_with_stats,
        players_with_club_association=players_with_club,
        players_missing_identity=players_missing_identity,
        players_missing_position=players_missing_position,
        duplicate_provider_ids=duplicate_provider_ids,
        by_competition_season=[
            PlayerCompetitionCoverage(
                competition=row[0], season=row[1], players=row[2]
            )
            for row in competition_rows
        ],
        latest_player_ingestion=latest,
        ingestion_completeness={
            "scope": latest_scope_params,
            "declared_total_pages": declared_total_pages,
            "latest_page": declared_current_page,
            "completed_pages": completed_pages,
            "failed_runs": failures,
            "status": completeness_status,
            "provider_plan_limit": (
                {
                    "page_max": plan_page_max,
                    "message": plan_limit_message,
                }
                if plan_page_max is not None
                else None
            ),
            "accessible_pages": (
                min(plan_page_max, declared_total_pages)
                if plan_page_max is not None and declared_total_pages is not None
                else plan_page_max
            ),
            "provider_quota_note": (
                "Provider rate limits and quotas are not inferred from a "
                "successful request; FAILED runs carry the provider error."
            ),
        },
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/players", response_model=list[PlayerResponse])
async def list_players(
    position: str | None = Query(None),
    nationality: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[PlayerResponse]:
    """Legacy bounded list (no total metadata). Prefer `/players/search`."""
    stmt = (
        select(Player)
        .options(selectinload(Player.identities), selectinload(Player.season_stats))
        .order_by(Player.name, Player.id.asc())
        .offset(offset)
        .limit(limit)
    )
    filters = _player_filters(
        q=None,
        position=position,
        nationality=nationality,
        club_id=None,
        competition_season_id=None,
    )
    if filters:
        stmt = stmt.where(*filters)
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


def _match_filters(
    *,
    competition_id: uuid.UUID | None,
    season_id: uuid.UUID | None,
    competition_season_id: uuid.UUID | None,
    club_id: uuid.UUID | None,
    status: str | None,
    date_from: date | None,
    date_to: date | None,
) -> list:
    filters: list = []
    if competition_season_id:
        filters.append(Match.competition_season_id == competition_season_id)
    if competition_id:
        filters.append(CompetitionSeason.competition_id == competition_id)
    if season_id:
        filters.append(CompetitionSeason.season_id == season_id)
    if club_id:
        filters.append((Match.home_club_id == club_id) | (Match.away_club_id == club_id))
    if status:
        filters.append(Match.status == status.upper())
    if date_from:
        filters.append(
            Match.date >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if date_to:
        filters.append(
            Match.date <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc)
        )
    return filters


def _match_list_item(m: Match) -> MatchListResponse:
    competition_season = m.competition_season
    return MatchListResponse(
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
        competition_name=(
            competition_season.competition.name
            if competition_season and competition_season.competition
            else None
        ),
        season_name=(
            competition_season.season.name
            if competition_season and competition_season.season
            else None
        ),
        home_score=m.home_score,
        away_score=m.away_score,
        winner_club_id=m.winner_club_id,
    )


@router.get("/matches/search", response_model=MatchPageResponse)
async def search_matches(
    competition_id: uuid.UUID | None = Query(None),
    season_id: uuid.UUID | None = Query(None),
    competition_season_id: uuid.UUID | None = Query(None),
    club_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> MatchPageResponse:
    """Paginated fixtures with a total measured on the same filters.

    `/matches` remains as a bounded legacy list (no total metadata); the UI
    and any completeness claim use this endpoint.
    """
    needs_join = bool(competition_id or season_id)
    filters = _match_filters(
        competition_id=competition_id,
        season_id=season_id,
        competition_season_id=competition_season_id,
        club_id=club_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )

    count_stmt = select(func.count(Match.id))
    if needs_join:
        count_stmt = count_stmt.join(
            CompetitionSeason, Match.competition_season_id == CompetitionSeason.id
        )
    total = (await session.execute(count_stmt.where(*filters))).scalar_one()

    stmt = (
        select(Match)
        .options(
            selectinload(Match.home_club),
            selectinload(Match.away_club),
            selectinload(Match.competition_season).selectinload(CompetitionSeason.competition),
            selectinload(Match.competition_season).selectinload(CompetitionSeason.season),
        )
        .order_by(Match.date.desc(), Match.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if needs_join:
        stmt = stmt.join(
            CompetitionSeason, Match.competition_season_id == CompetitionSeason.id
        )
    matches = (await session.execute(stmt.where(*filters))).scalars().all()
    total_pages = math.ceil(total / page_size) if total else 0

    return MatchPageResponse(
        items=[_match_list_item(m) for m in matches],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
    )


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
    """Legacy bounded list (no total metadata). Prefer `/matches/search`."""
    needs_join = bool(competition_id or season_id)
    filters = _match_filters(
        competition_id=competition_id,
        season_id=season_id,
        competition_season_id=competition_season_id,
        club_id=club_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    stmt = (
        select(Match)
        .options(
            selectinload(Match.home_club),
            selectinload(Match.away_club),
            selectinload(Match.competition_season).selectinload(CompetitionSeason.competition),
            selectinload(Match.competition_season).selectinload(CompetitionSeason.season),
        )
        .order_by(Match.date.desc(), Match.id.asc())
        .offset(offset)
        .limit(limit)
    )
    if needs_join:
        stmt = stmt.join(
            CompetitionSeason, Match.competition_season_id == CompetitionSeason.id
        )
    matches = (await session.execute(stmt.where(*filters))).scalars().all()
    return [_match_list_item(m) for m in matches]


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
            # Rows written before the sample gate blanked placeholder scores can
            # still exist. Never serve neutral 0.5 dimensions as a percentile
            # shape for a player without a qualified sample.
            profile_scores=(
                profile.profile_scores if profile.role_status == "QUALIFIED" else {}
            ),
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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/market/model-status", response_model=ValuationModelStatusResponse)
async def get_market_model_status() -> ValuationModelStatusResponse:
    """Returns operational status, versioning, and test evaluation metrics of active valuation model."""
    return ValuationMLService.get_model_status()


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
from app.prediction.schemas import (  # noqa: E402
    MatchPredictionHistoryResponse,
    MatchPredictionResponse,
    ModelStatusResponse,
    PredictionExplanation,
)
from app.prediction.service import MatchPredictionService  # noqa: E402


@router.get("/matches/{match_id}/prediction", response_model=MatchPredictionResponse)
async def get_match_prediction(
    match_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for leakage-safe evaluation (defaults to match date)"),
    session: AsyncSession = Depends(get_session),
) -> MatchPredictionResponse:
    """Computes a temporally valid, leakage-safe, calibrated match prediction (1X2 probabilities and expected goals)."""
    service = MatchPredictionService(session)
    try:
        return await service.predict_match(match_id=match_id, as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(exc)}") from exc


@router.get("/matches/{match_id}/prediction/explanation", response_model=PredictionExplanation)
async def get_match_prediction_explanation(
    match_id: uuid.UUID,
    as_of: datetime | None = Query(None, description="Optional temporal cutoff for leakage-safe evaluation (defaults to match date)"),
    session: AsyncSession = Depends(get_session),
) -> PredictionExplanation:
    """Provides non-causal evidence factor breakdown and feature attribution for match prediction."""
    service = MatchPredictionService(session)
    try:
        return await service.get_prediction_explanation(match_id=match_id, as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Explanation error: {str(exc)}") from exc


@router.get("/matches/{match_id}/prediction/history", response_model=MatchPredictionHistoryResponse)
async def get_match_prediction_history(
    match_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MatchPredictionHistoryResponse:
    """Retrieves point-in-time prediction evolution history and snapshot audit trail for a fixture."""
    service = MatchPredictionService(session)
    return await service.get_prediction_history(match_id=match_id)


@router.get("/prediction/model-status", response_model=ModelStatusResponse)
async def get_prediction_model_status() -> ModelStatusResponse:
    """Returns verified operational status, Log Loss, Brier score, and calibration diagnostics for active model."""
    service = MatchPredictionService()
    return service.get_model_status()


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



