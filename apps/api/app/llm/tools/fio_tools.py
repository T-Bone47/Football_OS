"""The FIO tool registry: typed tools wired to the real FIO services.

Every tool here calls an existing FIO service or route handler. Nothing is
re-implemented: a tool answer and the corresponding page/API answer come from the
same code, so they cannot drift apart.

Where a capability does not exist in the platform, the tool says so explicitly
(``UNSUPPORTED``) instead of returning an empty or invented result.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import date as date_type
from typing import Any, Literal

from fastapi import HTTPException
from fastapi.params import Param
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.tools.base import (
    EpistemicStatus,
    Evidence,
    ToolError,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

# --------------------------------------------------------------------------- helpers


def _route_kwargs(handler, provided: dict[str, Any]) -> dict[str, Any]:
    """Fill the parameters a route handler declares but the caller did not supply.

    FastAPI's ``Query(...)`` defaults are sentinel objects, not values: calling a
    route handler directly without every argument would hand a ``Query`` object to the
    handler. This resolves the declared defaults instead.
    """
    kwargs = dict(provided)
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return kwargs
    for name, parameter in signature.parameters.items():
        if name in kwargs or name in ("session", "principal", "call_id"):
            continue
        default = parameter.default
        if isinstance(default, Param):
            default = default.default
        kwargs[name] = default
    return kwargs


async def _call_route(handler, **provided):
    """Call a route handler, mapping FastAPI's HTTP errors onto tool statuses."""
    try:
        return await handler(**_route_kwargs(handler, provided))
    except HTTPException as exc:
        if exc.status_code == 404:
            raise _not_found(str(exc.detail)) from exc
        if exc.status_code in (400, 422):
            raise ToolError(str(exc.detail), ToolStatus.ERROR) from exc
        raise ToolError(f"upstream error {exc.status_code}", ToolStatus.ERROR) from exc


def _parse_date(value: Any) -> date_type | None:
    if value in (None, ""):
        return None
    if isinstance(value, date_type):
        return value
    try:
        return date_type.fromisoformat(str(value))
    except ValueError:
        return None


def _dump(model: Any) -> Any:
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if isinstance(model, list):
        return [_dump(item) for item in model]
    if isinstance(model, dict):
        return {key: _dump(value) for key, value in model.items()}
    return model


def _not_found(message: str) -> ToolError:
    return ToolError(message, ToolStatus.NOT_FOUND)


def _insufficient(message: str) -> ToolError:
    return ToolError(message, ToolStatus.INSUFFICIENT_DATA)


def _unsupported(message: str) -> ToolError:
    return ToolError(message, ToolStatus.UNSUPPORTED)


async def _competition_season_names(
    session: AsyncSession, competition_season_ids: set[str]
) -> dict[str, dict[str, str]]:
    """Resolve competition-season ids to their competition and season names.

    The canonical season-statistic row stores a competition-season id; the answer must
    be able to say *which* competition and season the number belongs to, so the names
    are resolved from the canonical tables instead of being guessed.
    """
    from sqlalchemy import select

    from app.db.models.canonical import Competition, CompetitionSeason, Season

    if not competition_season_ids:
        return {}
    rows = (
        await session.execute(
            select(CompetitionSeason.id, Competition.name, Season.name)
            .join(Competition, Competition.id == CompetitionSeason.competition_id)
            .join(Season, Season.id == CompetitionSeason.season_id)
            .where(CompetitionSeason.id.in_([uuid.UUID(str(item)) for item in competition_season_ids]))
        )
    ).all()
    return {
        str(identifier): {"competition": competition, "season": season}
        for identifier, competition, season in rows
    }


def _player_evidence(
    player: dict[str, Any],
    *,
    source: str = "fio-canonical",
    season_names: dict[str, dict[str, str]] | None = None,
) -> list[Evidence]:
    """Evidence for one canonical player: identity plus every season statistic."""
    evidence: list[Evidence] = []
    entity_id = str(player.get("id") or "")
    season_names = season_names or {}
    for stat in player.get("season_stats") or []:
        competition_season = stat.get("competition_season_id")
        names = season_names.get(str(competition_season), {})
        for metric, unit in (
            ("appearances", "appearances"),
            ("lineups", "lineups"),
            ("minutes", "minutes"),
            ("goals", "goals"),
            ("assists", "assists"),
            ("conceded", "goals_conceded"),
            ("rating", "rating"),
        ):
            if metric not in stat:
                continue
            value = stat.get(metric)
            if value is None:
                continue
            evidence.append(
                Evidence(
                    entity_type="player_season_stat",
                    entity_id=entity_id,
                    entity_name=player.get("name"),
                    metric=metric,
                    value=value,
                    unit=unit,
                    competition=names.get("competition") or competition_season,
                    season=names.get("season"),
                    sample_size=stat.get("minutes"),
                    source=source,
                    method="canonical player_season_stats row",
                    provenance_ref=str(stat.get("id") or ""),
                )
            )
    evidence.append(
        Evidence(
            entity_type="player",
            entity_id=entity_id,
            entity_name=player.get("name"),
            metric="identity",
            value={
                "nationality": player.get("nationality"),
                "primary_position": player.get("primary_position"),
                "date_of_birth": player.get("date_of_birth"),
                "height_cm": player.get("height_cm"),
                "weight_kg": player.get("weight_kg"),
            },
            source=source,
            method="canonical players row",
            provenance_ref=entity_id,
        )
    )
    return evidence


def _match_evidence(match: dict[str, Any]) -> list[Evidence]:
    evidence = [
        Evidence(
            entity_type="match",
            entity_id=str(match.get("id") or ""),
            entity_name=f"{match.get('home_club_name')} vs {match.get('away_club_name')}",
            metric="score",
            value={
                "home": match.get("home_score"),
                "away": match.get("away_score"),
            },
            competition=match.get("competition_name"),
            season=match.get("season_name"),
            source="fio-canonical",
            method="canonical matches row",
            provenance_ref=str(match.get("provider_fixture_id") or match.get("id") or ""),
        )
    ]
    return evidence


# ------------------------------------------------------------------------ input models


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchPlayersInput(_Input):
    q: str | None = Field(default=None, max_length=128, description="Name or partial name.")
    position: str | None = Field(default=None, max_length=64, description="Position or position group.")
    nationality: str | None = Field(default=None, max_length=64, description="Nationality, case-insensitive.")
    club_id: uuid.UUID | None = None
    competition_season_id: uuid.UUID | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50, description="Page size (max 50 per call).")


class PlayerRefInput(_Input):
    player_id: uuid.UUID | None = Field(default=None, description="Canonical player id.")
    name: str | None = Field(default=None, max_length=128, description="Player name, used when the id is unknown.")


class PlayerStatsInput(_Input):
    player_id: uuid.UUID
    competition_season_id: uuid.UUID | None = None


class ComparePlayersInput(_Input):
    player_ids: list[uuid.UUID] = Field(min_length=2, max_length=5)
    competition_season_id: uuid.UUID | None = None


class SimilarPlayersInput(_Input):
    player_id: uuid.UUID
    limit: int = Field(default=10, ge=1, le=25)
    mode: Literal["composite", "contribution", "role", "tactical", "replacement"] = "composite"


class PlayerIdInput(_Input):
    player_id: uuid.UUID


class SearchTeamsInput(_Input):
    query: str | None = Field(default=None, max_length=128, description="Club name fragment.")
    country: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=20, ge=1, le=50)


class ClubIdInput(_Input):
    club_id: uuid.UUID


class SquadInput(_Input):
    club_id: uuid.UUID | None = None
    formation: Literal["4-3-3", "4-2-3-1", "3-5-2"] = "4-3-3"


class CompetitionInput(_Input):
    competition_id: uuid.UUID | None = None
    season: str | None = Field(default=None, max_length=16)


class SearchMatchesInput(_Input):
    competition_id: uuid.UUID | None = None
    season_id: uuid.UUID | None = None
    competition_season_id: uuid.UUID | None = None
    club_id: uuid.UUID | None = None
    status: str | None = Field(default=None, max_length=32)
    date_from: str | None = Field(default=None, max_length=32, description="ISO date, e.g. 2024-01-01.")
    date_to: str | None = Field(default=None, max_length=32, description="ISO date, e.g. 2024-12-31.")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)


class MatchIdInput(_Input):
    match_id: uuid.UUID


class EventSummaryInput(_Input):
    match_id: uuid.UUID
    limit: int = Field(default=30, ge=1, le=100)


class RecruitmentInput(_Input):
    target_position: str = Field(default="MF", max_length=8)
    target_role: str | None = Field(default=None, max_length=64)
    formation: str = Field(default="4-3-3", max_length=16)
    budget_eur: float | None = Field(default=None, ge=0)
    min_minutes: int = Field(default=450, ge=0)
    limit: int = Field(default=5, ge=1, le=25)


class ReplacementsInput(_Input):
    player_id: uuid.UUID
    limit: int = Field(default=5, ge=1, le=25)
    max_value_eur: float | None = Field(default=None, ge=0)


class TacticalFitInput(_Input):
    player_id: uuid.UUID
    context_id: str | None = Field(default=None, max_length=64)


class CandidateIdsInput(_Input):
    candidate_ids: list[uuid.UUID] = Field(min_length=2, max_length=10)


class DocsQueryInput(_Input):
    query: str = Field(min_length=2, max_length=200, description="What to look for in the documentation.")


class FieldProvenanceInput(_Input):
    entity_type: str = Field(default="player", max_length=32, description="Canonical entity type.")
    entity_id: str = Field(min_length=1, max_length=64, description="Canonical entity id.")


# --------------------------------------------------------------------------- handlers


async def _resolve_player(session: AsyncSession, player_id: uuid.UUID | None, name: str | None):
    """Resolve a player by canonical id, or by name with an explicit ambiguity check."""
    from app.api import routes_canonical as rc
    from app.db.models.canonical import Player
    from app.identity.names import name_key
    from sqlalchemy import select

    if player_id is not None:
        payload = _dump(await _call_route(rc.get_player, player_id=player_id, session=session))
        return payload
    if not name:
        raise _not_found("a player id or a name is required")

    page = _dump(
        await _call_route(rc.search_players, q=name, page=1, page_size=10, session=session)
    )
    items = page.get("items") or []
    if not items:
        raise _not_found(f"no canonical player matches '{name}'")
    wanted = name_key(name)
    exact = [item for item in items if name_key(item.get("name")) == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ToolError(
            "several canonical players share that name: "
            + ", ".join(f"{item.get('name')} ({item.get('id')})" for item in exact[:5]),
            ToolStatus.AMBIGUOUS,
        )
    if len(items) > 1:
        raise ToolError(
            f"'{name}' is ambiguous: "
            + ", ".join(f"{item.get('name')} ({item.get('id')})" for item in items[:5]),
            ToolStatus.AMBIGUOUS,
        )
    return items[0]


def _register(registry: ToolRegistry) -> None:
    # ------------------------------------------------------------- player tools
    async def search_players(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        page = _dump(await _call_route(rc.search_players, session=session, **kwargs))
        evidence: list[Evidence] = []
        for item in page.get("items") or []:
            evidence.extend(_player_evidence(item))
        return ToolResult(
            tool="search_players",
            data=page,
            evidence=evidence,
            message=(
                f"{page.get('total')} canonical players match; showing page "
                f"{page.get('page')} of {page.get('total_pages')}."
            ),
            service="routes_canonical.search_players",
        )

    registry.register(
        ToolSpec(
            name="search_players",
            family="player",
            summary="Search the canonical player index with filters and server-side pagination.",
            description=(
                "Search the canonical player universe. Returns canonical ids, identity, and the "
                "season statistics that are actually stored. Use it before any player-scoped tool."
            ),
            input_model=SearchPlayersInput,
            handler=search_players,
            service="routes_canonical.search_players",
            data_source="canonical players / player_season_stats",
        )
    )

    async def get_player_profile(session, principal, call_id, **kwargs):
        player = await _resolve_player(session, kwargs.get("player_id"), kwargs.get("name"))
        names = await _competition_season_names(
            session,
            {
                str(stat.get("competition_season_id"))
                for stat in player.get("season_stats") or []
                if stat.get("competition_season_id")
            },
        )
        return ToolResult(
            tool="get_player_profile",
            data=player,
            evidence=_player_evidence(player, season_names=names),
            message="Canonical player profile and stored season statistics.",
            service="routes_canonical.get_player",
        )

    registry.register(
        ToolSpec(
            name="get_player_profile",
            family="player",
            summary="Fetch one canonical player profile (identity + stored season statistics).",
            description=(
                "Fetch the canonical profile of one player by id or by name. If the name is "
                "ambiguous the tool reports the candidates instead of guessing."
            ),
            input_model=PlayerRefInput,
            handler=get_player_profile,
            service="routes_canonical.get_player",
            data_source="canonical players / player_season_stats",
        )
    )

    async def get_player_season_statistics(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        player = _dump(await _call_route(rc.get_player, player_id=kwargs["player_id"], session=session))
        stats = player.get("season_stats") or []
        if kwargs.get("competition_season_id"):
            stats = [
                item
                for item in stats
                if item.get("competition_season_id") == str(kwargs["competition_season_id"])
            ]
        if not stats:
            raise _insufficient(
                "no stored season statistics for this player in the requested scope"
            )
        names = await _competition_season_names(
            session,
            {str(item.get("competition_season_id")) for item in stats if item.get("competition_season_id")},
        )
        return ToolResult(
            tool="get_player_season_statistics",
            data={"player_id": player.get("id"), "player_name": player.get("name"), "season_stats": stats},
            evidence=_player_evidence({**player, "season_stats": stats}, season_names=names),
            message=f"{len(stats)} stored season-statistic row(s).",
            service="routes_canonical.get_player",
        )

    registry.register(
        ToolSpec(
            name="get_player_season_statistics",
            family="player",
            summary="Stored season statistics for one player, with competition and sample size.",
            description=(
                "Return the stored season statistics of one player. Missing statistics are null "
                "(unknown), never zero."
            ),
            input_model=PlayerStatsInput,
            handler=get_player_season_statistics,
            service="routes_canonical.get_player",
            data_source="canonical player_season_stats",
        )
    )

    async def compare_players(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        players = []
        for player_id in kwargs["player_ids"]:
            players.append(_dump(await _call_route(rc.get_player, player_id=player_id, session=session)))
        names = await _competition_season_names(
            session,
            {
                str(stat.get("competition_season_id"))
                for player in players
                for stat in player.get("season_stats") or []
                if stat.get("competition_season_id")
            },
        )
        evidence: list[Evidence] = []
        for player in players:
            evidence.extend(_player_evidence(player, season_names=names))
        return ToolResult(
            tool="compare_players",
            data={"players": players},
            evidence=evidence,
            message=f"{len(players)} canonical players with their stored statistics.",
            service="routes_canonical.get_player",
        )

    registry.register(
        ToolSpec(
            name="compare_players",
            family="player",
            summary="Fetch several canonical players side by side for a like-for-like comparison.",
            description=(
                "Fetch 2-5 canonical players with their stored statistics so they can be "
                "compared on the same season and competition."
            ),
            input_model=ComparePlayersInput,
            handler=compare_players,
            service="routes_canonical.get_player",
            data_source="canonical players / player_season_stats",
        )
    )

    async def find_similar_players(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(
            await _call_route(rc.get_similar_players, 
                player_id=kwargs["player_id"],
                limit=kwargs["limit"],
                mode=kwargs["mode"],
                session=session,
            )
        )
        evidence = [
            Evidence(
                entity_type="player",
                entity_id=str(item.get("player_id") or ""),
                entity_name=item.get("player_name"),
                metric="similarity",
                value=item.get("overall_similarity"),
                unit="score",
                source="fio-roles-similarity",
                method=f"role similarity ({kwargs['mode']})",
                model_version="role_feature_set_v1",
                epistemic_status=EpistemicStatus.MODELLED,
            )
            for item in payload.get("results") or []
        ]
        return ToolResult(
            tool="find_similar_players",
            data=payload,
            evidence=evidence,
            message=payload.get("message") or "Similarity is a model estimate, not an observed fact.",
            service="routes_canonical.get_similar_players",
        )

    registry.register(
        ToolSpec(
            name="find_similar_players",
            family="player",
            summary="Model-based comparable players for a reference player.",
            description=(
                "Return players the role engine considers comparable. The score is a model "
                "estimate and may be empty when the reference player has no qualified profile."
            ),
            input_model=SimilarPlayersInput,
            handler=find_similar_players,
            service="routes_canonical.get_similar_players",
            data_source="canonical player_role_profiles",
        )
    )

    async def analyze_player_role(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(
            await _call_route(rc.get_player_role_profile, player_id=kwargs["player_id"], session=session)
        )
        evidence = [
            Evidence(
                entity_type="player_role_profile",
                entity_id=str(kwargs["player_id"]),
                metric="primary_archetype",
                value=payload.get("primary_archetype"),
                unit="archetype",
                sample_size=payload.get("sample_minutes"),
                source="fio-role-engine",
                method="role feature set v1",
                model_version="role_feature_set_v1",
                confidence=payload.get("archetype_confidence"),
                epistemic_status=EpistemicStatus.MODELLED,
            )
        ]
        return ToolResult(
            tool="analyze_player_role",
            data=payload,
            evidence=evidence,
            message=payload.get("role_status") or "Role classification status.",
            service="routes_canonical.get_player_role_profile",
        )

    registry.register(
        ToolSpec(
            name="analyze_player_role",
            family="player",
            summary="Role archetype classification and its sample depth.",
            description=(
                "Return the stored role archetype for a player, including the sample minutes "
                "behind it and the archetype confidence."
            ),
            input_model=PlayerIdInput,
            handler=analyze_player_role,
            service="routes_canonical.get_player_role_profile",
            data_source="canonical player_role_profiles",
        )
    )

    async def get_player_career_history(session, principal, call_id, **kwargs):
        from sqlalchemy import select

        from app.db.models.canonical import Transfer
        from app.db.models.expansion import PlayerClubMembership

        memberships = (
            await session.execute(
                select(PlayerClubMembership)
                .where(PlayerClubMembership.player_id == kwargs["player_id"])
                .order_by(PlayerClubMembership.is_current.desc())
            )
        ).scalars().all()
        transfers = (
            await session.execute(
                select(Transfer)
                .where(Transfer.player_id == kwargs["player_id"])
                .order_by(Transfer.transfer_date.desc())
            )
        ).scalars().all()
        if not memberships and not transfers:
            raise _insufficient("no stored club memberships or transfers for this player")
        evidence = [
            Evidence(
                entity_type="player_club_membership",
                entity_id=str(kwargs["player_id"]),
                metric="club_registration",
                value=(
                    (item.provenance or {}).get("season_year")
                    if item.provenance
                    else None
                ),
                unit="season",
                source="fio-canonical",
                method="time-bounded membership record",
                provenance_ref=str(item.id),
            )
            for item in memberships
        ]
        return ToolResult(
            tool="get_player_career_history",
            data={
                "memberships": [
                    {
                        "club_id": str(item.club_id) if item.club_id else None,
                        "competition_season_id": str(item.competition_season_id)
                        if item.competition_season_id
                        else None,
                        "is_current": item.is_current,
                        "season": (item.provenance or {}).get("season_year"),
                        "membership_type": item.membership_type,
                        "source_provider": item.source_provider,
                    }
                    for item in memberships
                ],
                "transfers": [_dump(item) for item in transfers],
            },
            evidence=evidence,
            message=f"{len(memberships)} membership row(s), {len(transfers)} transfer row(s).",
            service="player_club_memberships / transfers",
        )

    registry.register(
        ToolSpec(
            name="get_player_career_history",
            family="player",
            summary="Club registrations and transfers for a player (time-aware).",
            description=(
                "Return the time-bounded club memberships and the stored transfer records for "
                "a player. Season coverage is whatever the database actually holds."
            ),
            input_model=PlayerIdInput,
            handler=get_player_career_history,
            service="player_club_memberships / transfers",
            data_source="canonical memberships and transfers",
        )
    )

    # --------------------------------------------------------------- team tools
    async def search_teams(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        clubs = _dump(await _call_route(rc.list_clubs, country=kwargs.get("country"), session=session))
        query = (kwargs.get("query") or "").strip().lower()
        if query:
            clubs = [club for club in clubs if query in (club.get("name") or "").lower()]
        clubs = clubs[: kwargs["limit"]]
        evidence = [
            Evidence(
                entity_type="club",
                entity_id=str(club.get("id")),
                entity_name=club.get("name"),
                metric="identity",
                value={"country": club.get("country")},
                source="fio-canonical",
                method="canonical clubs row",
            )
            for club in clubs
        ]
        return ToolResult(
            tool="search_teams",
            data={"items": clubs, "returned": len(clubs)},
            evidence=evidence,
            message=f"{len(clubs)} club(s) returned.",
            service="routes_canonical.list_clubs",
        )

    registry.register(
        ToolSpec(
            name="search_teams",
            family="team",
            summary="Find clubs by name fragment and country.",
            description="Search the canonical club directory. Returns canonical club ids.",
            input_model=SearchTeamsInput,
            handler=search_teams,
            service="routes_canonical.list_clubs",
            data_source="canonical clubs",
        )
    )

    async def get_team_profile(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        club = _dump(await _call_route(rc.get_club, club_id=kwargs["club_id"], session=session))
        return ToolResult(
            tool="get_team_profile",
            data=club,
            evidence=[
                Evidence(
                    entity_type="club",
                    entity_id=str(club.get("id")),
                    entity_name=club.get("name"),
                    metric="identity",
                    value={"country": club.get("country"), "founded": club.get("founded")},
                    source="fio-canonical",
                    method="canonical clubs row",
                )
            ],
            message="Canonical club profile.",
            service="routes_canonical.get_club",
        )

    registry.register(
        ToolSpec(
            name="get_team_profile",
            family="team",
            summary="Canonical profile of one club.",
            description="Fetch the canonical club record (name, country, venue, provider identities).",
            input_model=ClubIdInput,
            handler=get_team_profile,
            service="routes_canonical.get_club",
            data_source="canonical clubs",
        )
    )

    async def get_team_squad(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(
            await _call_route(rc.build_squad_get, 
                club_id=kwargs.get("club_id"),
                formation=kwargs.get("formation", "4-3-3"),
                session=session,
            )
        )
        evidence = [
            Evidence(
                entity_type="player",
                entity_id=str(entry.get("player_id") or ""),
                entity_name=entry.get("player_name"),
                metric="squad_selection",
                value=entry.get("role") or entry.get("position"),
                source="fio-squad-engine",
                method="squad build (greedy role allocation)",
                model_version="squad_build",
                epistemic_status=EpistemicStatus.MODELLED,
            )
            for entry in payload.get("players") or []
        ]
        return ToolResult(
            tool="get_team_squad",
            data=payload,
            evidence=evidence,
            message=(
                f"Squad built for formation {payload.get('formation')} "
                f"({payload.get('starters_count')} starters)."
            ),
            service="routes_canonical.build_squad_get",
            data_source="canonical players / squad engine",
        )

    registry.register(
        ToolSpec(
            name="get_team_squad",
            family="team",
            summary="Squad selection for a formation (optionally scoped to one club).",
            description=(
                "Run the squad builder for a formation. The selection is a model allocation, "
                "not an observed lineup."
            ),
            input_model=SquadInput,
            handler=get_team_squad,
            service="routes_canonical.build_squad_get",
            data_source="canonical players / squad engine",
        )
    )

    async def get_competition_overview(session, principal, call_id, **kwargs):
        from app.coverage.service import competition_coverage

        rows = await competition_coverage(session)
        if kwargs.get("competition_id"):
            wanted = str(kwargs["competition_id"])
            rows = [row for row in rows if row["competition_id"] == wanted] if "competition_id" in rows[0] else rows
        evidence = [
            Evidence(
                entity_type="competition_season",
                entity_id=None,
                entity_name=row["competition"],
                metric="players_covered",
                value=row["players"],
                unit="players",
                competition=row["competition"],
                season=row["season"],
                source="fio-coverage-service",
                method="canonical counts",
                epistemic_status=EpistemicStatus.OBSERVED,
            )
            for row in rows
        ]
        return ToolResult(
            tool="get_competition_overview",
            data={"competitions": rows},
            evidence=evidence,
            message=f"{len(rows)} competition-season(s) with stored player coverage.",
            service="coverage.service.competition_coverage",
        )

    registry.register(
        ToolSpec(
            name="get_competition_overview",
            family="team",
            summary="What the database actually holds per competition and season.",
            description=(
                "Return the measured player coverage per competition-season. Use this before "
                "claiming that a search covered a whole league."
            ),
            input_model=CompetitionInput,
            handler=get_competition_overview,
            service="coverage.service.competition_coverage",
            data_source="canonical coverage service",
        )
    )

    async def get_league_standings(session, principal, call_id, **kwargs):
        raise _unsupported(
            "FIO has no persisted league table: the provider standings endpoint is not "
            "normalised into the canonical model. Use get_competition_overview for coverage "
            "and search_matches for fixtures."
        )

    registry.register(
        ToolSpec(
            name="get_league_standings",
            family="team",
            summary="League table (not available in the canonical model).",
            description=(
                "Return the league standings. FIO does not persist a normalised league table, "
                "so this tool reports the capability as unavailable instead of inventing one."
            ),
            input_model=CompetitionInput,
            handler=get_league_standings,
            service="(not implemented)",
            data_source="(none)",
        )
    )

    # -------------------------------------------------------------- match tools
    async def search_matches(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        scope = dict(kwargs)
        scope["date_from"] = _parse_date(scope.get("date_from"))
        scope["date_to"] = _parse_date(scope.get("date_to"))
        payload = _dump(await _call_route(rc.search_matches, session=session, **scope))
        evidence: list[Evidence] = []
        for item in payload.get("items") or []:
            evidence.extend(_match_evidence(item))
        return ToolResult(
            tool="search_matches",
            data=payload,
            evidence=evidence,
            message=f"{payload.get('total')} fixtures match; page {payload.get('page')}.",
            service="routes_canonical.search_matches",
        )

    registry.register(
        ToolSpec(
            name="search_matches",
            family="match",
            summary="Search fixtures with filters and server-side pagination.",
            description="Search the canonical fixture list by competition, season, club, status and date.",
            input_model=SearchMatchesInput,
            handler=search_matches,
            service="routes_canonical.search_matches",
            data_source="canonical matches",
        )
    )

    async def get_match_details(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(await _call_route(rc.get_match, match_id=kwargs["match_id"], session=session))
        return ToolResult(
            tool="get_match_details",
            data=payload,
            evidence=_match_evidence(payload),
            message="Canonical fixture record.",
            service="routes_canonical.get_match",
        )

    registry.register(
        ToolSpec(
            name="get_match_details",
            family="match",
            summary="Canonical fixture record (teams, score, kick-off, competition, season).",
            description="Fetch one fixture with the data the database actually stores about it.",
            input_model=MatchIdInput,
            handler=get_match_details,
            service="routes_canonical.get_match",
            data_source="canonical matches",
        )
    )

    async def get_match_statistics(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        rows = _dump(await _call_route(rc.get_match_statistics, match_id=kwargs["match_id"], session=session))
        if not rows:
            raise _insufficient("no team statistics are stored for this fixture")
        evidence = [
            Evidence(
                entity_type="match_team_statistics",
                entity_id=str(row.get("id")),
                metric=metric,
                value=row.get(metric),
                unit=unit,
                source="fio-canonical",
                method="provider match statistics block",
            )
            for row in rows
            for metric, unit in (
                ("possession_pct", "percent"),
                ("shots_total", "shots"),
                ("shots_on_target", "shots"),
                ("passes_total", "passes"),
                ("pass_accuracy_pct", "percent"),
                ("expected_goals", "expected_goals"),
                ("corners", "corners"),
                ("fouls", "fouls"),
            )
            if row.get(metric) is not None
        ]
        return ToolResult(
            tool="get_match_statistics",
            data=rows,
            evidence=evidence,
            message=f"{len(rows)} team-statistics row(s) stored.",
            service="routes_canonical.get_match_statistics",
        )

    registry.register(
        ToolSpec(
            name="get_match_statistics",
            family="match",
            summary="Stored team statistics for a fixture.",
            description=(
                "Return the stored team statistics (possession, shots, passes, xG) for a fixture. "
                "Many fixtures have no statistics; the tool says so rather than returning zeros."
            ),
            input_model=MatchIdInput,
            handler=get_match_statistics,
            service="routes_canonical.get_match_statistics",
            data_source="canonical match_statistics",
        )
    )

    async def get_match_prediction(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(await _call_route(rc.get_match_prediction, match_id=kwargs["match_id"], session=session))
        data_status = payload.get("data_status")
        status = EpistemicStatus.MODELLED
        if data_status == "INSUFFICIENT_DATA":
            status = EpistemicStatus.INSUFFICIENT_DATA
        elif data_status == "OUT_OF_DISTRIBUTION":
            status = EpistemicStatus.OUT_OF_DISTRIBUTION
        evidence = [
            Evidence(
                entity_type="match_prediction",
                entity_id=str(payload.get("match_id") or kwargs["match_id"]),
                metric="outcome_probabilities",
                value=payload.get("probabilities"),
                unit="probability",
                competition=payload.get("competition_name"),
                season=payload.get("season_name"),
                source="fio-match-model",
                method="temporally valid pre-match feature snapshot",
                model_version=payload.get("model_version"),
                epistemic_status=status,
            )
        ]
        return ToolResult(
            tool="get_match_prediction",
            data=payload,
            evidence=evidence,
            message=f"Prediction data_status: {data_status or 'UNKNOWN'}.",
            service="routes_canonical.get_match_prediction",
        )

    registry.register(
        ToolSpec(
            name="get_match_prediction",
            family="match",
            summary="Match prediction with its own data-status and model version.",
            description=(
                "Return the stored pre-match prediction for a fixture, including the model's "
                "data_status (INSUFFICIENT_DATA, OUT_OF_DISTRIBUTION, ...) and version."
            ),
            input_model=MatchIdInput,
            handler=get_match_prediction,
            service="routes_canonical.get_match_prediction",
            data_source="canonical prediction service",
        )
    )

    async def analyze_matchup(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        match = _dump(await _call_route(rc.get_match, match_id=kwargs["match_id"], session=session))
        payload: dict[str, Any] = {"match": match}
        notes: list[str] = []
        try:
            payload["statistics"] = _dump(
                await _call_route(rc.get_match_statistics, match_id=kwargs["match_id"], session=session)
            )
        except Exception:  # noqa: BLE001 - statistics are optional
            notes.append("no team statistics stored for this fixture")
        try:
            payload["prediction"] = _dump(
                await _call_route(rc.get_match_prediction, match_id=kwargs["match_id"], session=session)
            )
        except Exception:  # noqa: BLE001 - prediction is optional
            notes.append("no prediction available for this fixture")
        evidence = _match_evidence(match)
        for row in payload.get("statistics") or []:
            for metric, unit in (("possession_pct", "percent"), ("shots_total", "shots"), ("expected_goals", "expected_goals")):
                if row.get(metric) is not None:
                    evidence.append(
                        Evidence(
                            entity_type="match_team_statistics",
                            entity_id=str(row.get("id")),
                            metric=metric,
                            value=row.get(metric),
                            unit=unit,
                            competition=match.get("competition_name"),
                            season=match.get("season_name"),
                            source="fio-canonical",
                            method="provider match statistics block",
                        )
                    )
        if payload.get("prediction"):
            evidence.append(
                Evidence(
                    entity_type="match_prediction",
                    entity_id=str(kwargs["match_id"]),
                    metric="outcome_probabilities",
                    value=payload["prediction"].get("probabilities"),
                    unit="probability",
                    competition=match.get("competition_name"),
                    season=match.get("season_name"),
                    source="fio-match-model",
                    method="temporally valid pre-match feature snapshot",
                    model_version=payload["prediction"].get("model_version"),
                    epistemic_status=EpistemicStatus.MODELLED,
                )
            )
        return ToolResult(
            tool="analyze_matchup",
            data=payload,
            evidence=evidence,
            message="; ".join(notes) if notes else "Fixture, statistics and prediction retrieved.",
            service="routes_canonical.get_match / statistics / prediction",
        )

    registry.register(
        ToolSpec(
            name="analyze_matchup",
            family="match",
            summary="Fixture + stored statistics + stored prediction in one call.",
            description=(
                "Combine the canonical fixture, its stored team statistics and its stored "
                "prediction. Observed statistics and model output are labelled separately."
            ),
            input_model=MatchIdInput,
            handler=analyze_matchup,
            service="routes_canonical.get_match",
            data_source="canonical matches / match_statistics / prediction",
        )
    )

    async def get_match_event_summary(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        rows = _dump(await _call_route(rc.get_match_events, match_id=kwargs["match_id"], session=session))
        rows = rows[: kwargs["limit"]]
        if not rows:
            raise _insufficient("no match events are stored for this fixture")
        evidence = [
            Evidence(
                entity_type="match_event",
                entity_id=str(row.get("id")),
                metric=row.get("event_type"),
                value={
                    "minute": row.get("minute"),
                    "detail": row.get("event_detail"),
                    "player_id": str(row.get("player_id")) if row.get("player_id") else None,
                },
                unit="event",
                source="fio-canonical",
                method="provider match event block",
            )
            for row in rows
        ]
        return ToolResult(
            tool="get_match_event_summary",
            data=rows,
            evidence=evidence,
            message=f"{len(rows)} stored event(s).",
            service="routes_canonical.get_match_events",
        )

    registry.register(
        ToolSpec(
            name="get_match_event_summary",
            family="match",
            summary="Stored match events (goals, cards, substitutions) for a fixture.",
            description="Return the stored event stream for a fixture. No events are invented.",
            input_model=EventSummaryInput,
            handler=get_match_event_summary,
            service="routes_canonical.get_match_events",
            data_source="canonical match_events",
        )
    )

    # -------------------------------------------------------- recruitment tools
    async def find_recruitment_candidates(session, principal, call_id, **kwargs):
        from app.decisions.recruitment import RecruitmentTargetEngine
        from app.decisions.schemas import RecruitmentTargetRequest

        engine = RecruitmentTargetEngine(session=session)
        request = RecruitmentTargetRequest(
            target_position=kwargs["target_position"],
            target_role=kwargs.get("target_role"),
            formation=kwargs.get("formation", "4-3-3"),
            budget_eur=kwargs.get("budget_eur"),
            min_minutes=kwargs.get("min_minutes", 450),
            limit=kwargs.get("limit", 5),
        )
        result = await engine.evaluate_recruitment(request)
        evidence = [
            Evidence(
                entity_type="recruitment_assessment",
                entity_id=str(candidate.candidate_id),
                entity_name=candidate.player_name,
                metric="minutes_played",
                value=candidate.minutes_played,
                unit="minutes",
                source="fio-decision-engine",
                method="recruitment target engine (hard constraints first)",
                model_version="recruitment_v1",
                sample_size=candidate.minutes_played,
                epistemic_status=EpistemicStatus.MODELLED,
            )
            for candidate in result.top_recommendations
        ]
        return ToolResult(
            tool="find_recruitment_candidates",
            data=_dump(result),
            evidence=evidence,
            message=(
                f"{len(result.top_recommendations)} candidate(s) passed the hard constraints; "
                f"{result.decision.excluded_candidates_count} excluded."
            ),
            service="decisions.recruitment.RecruitmentTargetEngine",
        )

    registry.register(
        ToolSpec(
            name="find_recruitment_candidates",
            family="recruitment",
            summary="Recruitment candidates for a position/role with explicit hard constraints.",
            description=(
                "Rank candidates for a recruitment mandate. The ranking inputs, the hard "
                "constraints and the excluded candidates are part of the result."
            ),
            input_model=RecruitmentInput,
            handler=find_recruitment_candidates,
            service="decisions.recruitment.RecruitmentTargetEngine",
            data_source="canonical players / player_season_stats / role profiles",
        )
    )

    async def find_replacements(session, principal, call_id, **kwargs):
        from app.decisions.replacement import ReplacementDecisionEngine
        from app.decisions.schemas import ReplacementDecisionRequest

        engine = ReplacementDecisionEngine(session=session)
        request = ReplacementDecisionRequest(
            player_id_to_replace=kwargs["player_id"],
            limit=kwargs.get("limit", 5),
            max_value_eur=kwargs.get("max_value_eur"),
        )
        result = await engine.evaluate_replacement(request)
        evidence = [
            Evidence(
                entity_type="replacement_assessment",
                entity_id=str(candidate.candidate_id),
                entity_name=candidate.player_name,
                metric="similarity",
                value=candidate.similarity.overall_similarity,
                unit="score",
                source="fio-decision-engine",
                method="replacement decision engine",
                model_version="replacement_v1",
                epistemic_status=EpistemicStatus.MODELLED,
            )
            for candidate in result.top_replacements
        ]
        return ToolResult(
            tool="find_replacements",
            data=_dump(result),
            evidence=evidence,
            message=f"{len(result.top_replacements)} replacement candidate(s) returned.",
            service="decisions.replacement.ReplacementDecisionEngine",
        )

    registry.register(
        ToolSpec(
            name="find_replacements",
            family="recruitment",
            summary="Replacement candidates for a departing player.",
            description=(
                "Return scored replacement candidates. Similarity and fit are model outputs; "
                "a missing valuation stays missing."
            ),
            input_model=ReplacementsInput,
            handler=find_replacements,
            service="decisions.replacement.ReplacementDecisionEngine",
            data_source="canonical players / role profiles / transfers",
        )
    )

    async def evaluate_tactical_fit(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(
            await _call_route(rc.get_player_tactical_fit, 
                player_id=kwargs["player_id"],
                context_id=kwargs.get("context_id"),
                session=session,
            )
        )
        evidence = [
            Evidence(
                entity_type="player_tactical_fit",
                entity_id=str(kwargs["player_id"]),
                metric="fit_score",
                value=payload.get("fit_score"),
                unit="score",
                source="fio-tactical-engine",
                method="tactical fit calculator",
                model_version=payload.get("calculation_version"),
                confidence=payload.get("confidence") and 1.0 or None,
                epistemic_status=EpistemicStatus.MODELLED,
            )
        ]
        return ToolResult(
            tool="evaluate_tactical_fit",
            data=payload,
            evidence=evidence,
            message=f"Fit status: {payload.get('fit_status')} / confidence {payload.get('confidence')}.",
            service="routes_canonical.get_player_tactical_fit",
        )

    registry.register(
        ToolSpec(
            name="evaluate_tactical_fit",
            family="recruitment",
            summary="Tactical compatibility of a player with a system/role context.",
            description=(
                "Return the stored tactical fit for a player against a tactical context, with "
                "its fit_status and confidence."
            ),
            input_model=TacticalFitInput,
            handler=evaluate_tactical_fit,
            service="routes_canonical.get_player_tactical_fit",
            data_source="canonical player_tactical_fits",
        )
    )

    async def compare_candidate_tradeoffs(session, principal, call_id, **kwargs):
        from app.decisions.service import UnifiedDecisionService
        from app.decisions.schemas import CandidateComparisonRequest

        engine = UnifiedDecisionService(session=session)
        result = await engine.compare_candidates(
            CandidateComparisonRequest(candidate_ids=kwargs["candidate_ids"])
        )
        evidence = [
            Evidence(
                entity_type="candidate_comparison",
                entity_id=str(candidate.get("candidate_id")),
                entity_name=candidate.get("player_name"),
                metric="tactical_fit",
                value=(candidate.get("tactical") or {}).get("tactical_fit_score"),
                unit="score",
                source="fio-decision-engine",
                method="candidate comparison engine",
                model_version="decision_v1",
                epistemic_status=EpistemicStatus.MODELLED,
            )
            for candidate in result.candidates
        ]
        return ToolResult(
            tool="compare_candidate_tradeoffs",
            data=_dump(result),
            evidence=evidence,
            message=f"{len(result.candidates)} candidate(s) compared.",
            service="decisions.service.UnifiedDecisionService",
        )

    registry.register(
        ToolSpec(
            name="compare_candidate_tradeoffs",
            family="recruitment",
            summary="Side-by-side trade-off analysis of shortlisted candidates.",
            description=(
                "Compare shortlisted candidates dimension by dimension, keeping the observed "
                "statistics and the modelled dimensions distinguishable."
            ),
            input_model=CandidateIdsInput,
            handler=compare_candidate_tradeoffs,
            service="decisions.service.UnifiedDecisionService",
            data_source="canonical players / decision engines",
        )
    )

    # ------------------------------------------------------------ financial tools
    async def get_player_valuation(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(
            await _call_route(rc.get_player_valuation_baseline, player_id=kwargs["player_id"], session=session)
        )
        status = payload.get("valuation_status")
        epistemic = EpistemicStatus.MODELLED
        if status and status != "VALUATION_AVAILABLE":
            epistemic = EpistemicStatus.INSUFFICIENT_DATA
        evidence = [
            Evidence(
                entity_type="player_valuation",
                entity_id=str(kwargs["player_id"]),
                metric="estimated_value_eur",
                value=payload.get("estimated_value_eur"),
                unit="EUR",
                source="fio-market-engine",
                method="comparable-median baseline valuation",
                model_version="valuation_baseline_v1",
                confidence=payload.get("coverage_level"),
                epistemic_status=epistemic,
            )
        ]
        return ToolResult(
            tool="get_player_valuation",
            data=payload,
            evidence=evidence,
            message=f"Valuation status: {status}.",
            service="routes_canonical.get_player_valuation_baseline",
        )

    registry.register(
        ToolSpec(
            name="get_player_valuation",
            family="financial",
            summary="Canonical valuation baseline with its sufficiency status.",
            description=(
                "Return the deterministic comparable-median valuation for a player. When the "
                "comparable sample is too small the tool reports INSUFFICIENT_DATA - never a zero."
            ),
            input_model=PlayerIdInput,
            handler=get_player_valuation,
            service="routes_canonical.get_player_valuation_baseline",
            data_source="canonical transfers / valuation engine",
        )
    )

    async def analyze_transfer_risk(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(
            await _call_route(rc.get_player_transfer_risk, player_id=kwargs["player_id"], session=session)
        )
        evidence = [
            Evidence(
                entity_type="transfer_risk",
                entity_id=str(kwargs["player_id"]),
                metric="overall_risk_score",
                value=payload.get("overall_score"),
                unit="score",
                source="fio-market-engine",
                method="multi-dimensional transfer risk",
                model_version="transfer_risk_v1",
                epistemic_status=EpistemicStatus.MODELLED,
            )
        ]
        return ToolResult(
            tool="analyze_transfer_risk",
            data=payload,
            evidence=evidence,
            message=f"Risk level: {payload.get('risk_level')}.",
            service="routes_canonical.get_player_transfer_risk",
        )

    registry.register(
        ToolSpec(
            name="analyze_transfer_risk",
            family="financial",
            summary="Multi-dimensional transfer risk for a player.",
            description="Return the stored transfer-risk assessment with its data-quality state.",
            input_model=PlayerIdInput,
            handler=analyze_transfer_risk,
            service="routes_canonical.get_player_transfer_risk",
            data_source="canonical transfers / role profiles",
        )
    )

    # --------------------------------------------------------------- squad tools
    async def analyze_squad_balance(session, principal, call_id, **kwargs):
        from app.api import routes_canonical as rc

        payload = _dump(
            await _call_route(rc.build_squad_get, 
                club_id=kwargs.get("club_id"),
                formation=kwargs.get("formation", "4-3-3"),
                session=session,
            )
        )
        evidence = [
            Evidence(
                entity_type="squad_balance",
                entity_id=None,
                metric="role_coverage",
                value=payload.get("role_coverage_score"),
                unit="score",
                source="fio-squad-engine",
                method="squad build (greedy role allocation)",
                model_version="squad_build",
                epistemic_status=EpistemicStatus.MODELLED,
            ),
            Evidence(
                entity_type="squad_balance",
                entity_id=None,
                metric="depth_risk",
                value=payload.get("depth_risk_level"),
                unit="level",
                source="fio-squad-engine",
                method="squad build (greedy role allocation)",
                model_version="squad_build",
                epistemic_status=EpistemicStatus.MODELLED,
            ),
        ]
        return ToolResult(
            tool="analyze_squad_balance",
            data=payload,
            evidence=evidence,
            message=(
                f"Squad quality {payload.get('squad_quality_score')}, "
                f"role coverage {payload.get('role_coverage_score')}, "
                f"depth risk {payload.get('depth_risk_level')}."
            ),
            service="routes_canonical.build_squad_get",
        )

    registry.register(
        ToolSpec(
            name="analyze_squad_balance",
            family="squad",
            summary="Squad composition, role coverage and depth risk for a formation.",
            description=(
                "Return the squad engine's view of a squad: quality, role coverage, depth risk "
                "and the position gaps it found."
            ),
            input_model=SquadInput,
            handler=analyze_squad_balance,
            service="routes_canonical.build_squad_get",
            data_source="canonical players / squad engine",
        )
    )

    # ------------------------------------------------------------ platform tools
    async def get_data_coverage(session, principal, call_id, **kwargs):
        from app.coverage.service import compute_coverage

        payload = await compute_coverage(session)
        evidence = [
            Evidence(
                entity_type="coverage",
                entity_id=None,
                metric="canonical_players",
                value=payload["canonical"]["players"],
                unit="players",
                source="fio-coverage-service",
                method="canonical row counts",
                epistemic_status=EpistemicStatus.OBSERVED,
            )
        ]
        return ToolResult(
            tool="get_data_coverage",
            data={
                "canonical": payload["canonical"],
                "competitions": payload["competitions"],
                "countries": {
                    "selected_countries": payload["countries"]["selected_countries"],
                    "countries_with_covered_players": payload["countries"][
                        "countries_with_covered_players"
                    ],
                    "ranking_source": payload["countries"]["ranking_source"],
                    "ranking_snapshot_date": payload["countries"]["ranking_snapshot_date"],
                    "coverage_denominator": payload["countries"]["coverage_denominator"],
                },
                "profile_completeness": payload["profile_completeness"],
                "statistic_completeness": payload["statistic_completeness"],
            },
            evidence=evidence,
            message="Measured coverage of the canonical database.",
            service="coverage.service.compute_coverage",
        )

    registry.register(
        ToolSpec(
            name="get_data_coverage",
            family="platform",
            summary="Measured coverage of the canonical database (counts with denominators).",
            description=(
                "Return how much data the platform actually holds: canonical players, per "
                "competition-season coverage, profile/statistic completeness and the "
                "priority-country coverage with its denominator."
            ),
            input_model=type("NoInput", (_Input,), {}),
            handler=get_data_coverage,
            service="coverage.service.compute_coverage",
            data_source="canonical database",
        )
    )

    async def get_data_freshness(session, principal, call_id, **kwargs):
        from app.observability.system_health import check_data_health

        payload = await check_data_health(session)
        metrics = payload.get("metrics") or {}
        evidence = [
            Evidence(
                entity_type="data_layer",
                entity_id=None,
                metric="last_successful_ingestion_age_hours",
                value=metrics.get("last_successful_ingestion_age_hours"),
                unit="hours",
                source="fio-observability",
                method="max(finished_at) over successful ingestion runs",
                epistemic_status=EpistemicStatus.OBSERVED,
            )
        ]
        return ToolResult(
            tool="get_data_freshness",
            data=payload,
            evidence=evidence,
            message=f"Data layer status: {payload.get('status')}.",
            service="observability.system_health.check_data_health",
        )

    registry.register(
        ToolSpec(
            name="get_data_freshness",
            family="platform",
            summary="How fresh the canonical data is (last successful ingestion, schema version).",
            description="Return the measured data-layer status and the age of the last ingestion.",
            input_model=type("NoInput", (_Input,), {}),
            handler=get_data_freshness,
            service="observability.system_health.check_data_health",
            data_source="canonical database + ingestion runs",
        )
    )

    async def get_model_status(session, principal, call_id, **kwargs):
        from app.observability.system_health import check_model_health

        payload = await check_model_health()
        evidence = [
            Evidence(
                entity_type="model_artifact",
                entity_id=str(artifact.get("model_id")),
                metric="release_status",
                value=artifact.get("release_status"),
                unit="status",
                source="fio-model-registry",
                method="model registry",
                model_version=artifact.get("model_version"),
                epistemic_status=EpistemicStatus.MODELLED,
            )
            for artifact in payload.get("artifacts") or []
        ]
        return ToolResult(
            tool="get_model_status",
            data=payload,
            evidence=evidence,
            message=f"Model status: {payload.get('status')}.",
            service="observability.system_health.check_model_health",
        )

    registry.register(
        ToolSpec(
            name="get_model_status",
            family="platform",
            summary="Registered model artifacts, their release status and blockers.",
            description="Return what the model registry actually says, including release blockers.",
            input_model=type("NoInput", (_Input,), {}),
            handler=get_model_status,
            service="observability.system_health.check_model_health",
            data_source="model registry",
        )
    )

    async def get_provider_health(session, principal, call_id, **kwargs):
        from app.ingestion.sources import source_policies

        payload = {"providers": await source_policies(session)}
        evidence = [
            Evidence(
                entity_type="data_source",
                entity_id=None,
                entity_name=item["name"],
                metric="enabled",
                value=item["enabled"],
                unit="boolean",
                source="fio-source-registry",
                method="registered source policy",
                epistemic_status=EpistemicStatus.OBSERVED,
            )
            for item in payload["providers"]
        ]
        return ToolResult(
            tool="get_provider_health",
            data=payload,
            evidence=evidence,
            message="Registered data sources with their licence and enablement state.",
            service="ingestion.sources.source_policies",
        )

    registry.register(
        ToolSpec(
            name="get_provider_health",
            family="platform",
            summary="Registered providers, their licence state and whether ingestion is enabled.",
            description=(
                "Return the data-source registry: which providers are enabled, their licence and "
                "attribution, and when the terms were reviewed."
            ),
            input_model=type("NoInput", (_Input,), {}),
            handler=get_provider_health,
            service="ingestion.sources.source_policies",
            data_source="source registry",
        )
    )

    async def get_field_provenance(session, principal, call_id, **kwargs):
        """Which provider supplied a field, and which values disagree."""
        from app.coverage.service import entity_provenance

        payload = await entity_provenance(
            session, kwargs["entity_type"], str(kwargs["entity_id"])
        )
        fields = payload.get("fields") or []
        if not fields and not payload.get("conflicts"):
            raise _insufficient(
                "no field-level provenance is recorded for this entity; the value predates the "
                "provenance recorder"
            )
        evidence = [
            Evidence(
                entity_type="field_provenance",
                entity_id=str(kwargs["entity_id"]),
                entity_name=field.get("field"),
                metric=field.get("field"),
                value=(field.get("value") or {}).get("value"),
                source=field.get("provider"),
                method=field.get("transformation") or "provider field value",
                confidence=field.get("confidence"),
                provenance_ref=f"{field.get('provider')}:{field.get('provider_entity_id')}",
                epistemic_status=EpistemicStatus.OBSERVED,
            )
            for field in fields
        ]
        return ToolResult(
            tool="get_field_provenance",
            data=payload,
            evidence=evidence,
            message=(
                f"{len(fields)} field(s) with provenance, "
                f"{len(payload.get('conflicts') or [])} unresolved conflict(s)."
            ),
            service="coverage.service.entity_provenance",
        )

    registry.register(
        ToolSpec(
            name="get_field_provenance",
            family="platform",
            summary="Which provider supplied a field, and which providers disagree.",
            description=(
                "Return the field-level provenance of a canonical entity: the provider behind "
                "each field, the transformation applied, and the values that conflict."
            ),
            input_model=FieldProvenanceInput,
            handler=get_field_provenance,
            service="coverage.service.entity_provenance",
            data_source="field_provenance / source_conflicts",
        )
    )

    async def get_analytics_methodology(session, principal, call_id, **kwargs):
        from app.llm.tools.docs import retrieve_documentation

        passages = retrieve_documentation(kwargs["query"])
        if not passages:
            raise _insufficient(
                "no documentation section matches this question; the methodology is not documented "
                "for it"
            )
        evidence = [
            Evidence(
                entity_type="documentation",
                entity_id=passage["ref"],
                entity_name=passage["title"],
                metric="methodology",
                value=passage["section"],
                source="fio-documentation",
                method="documentation retrieval",
                provenance_ref=passage["ref"],
            )
            for passage in passages
        ]
        return ToolResult(
            tool="get_analytics_methodology",
            data={"passages": passages},
            evidence=evidence,
            message=f"{len(passages)} documentation passage(s).",
            service="llm.tools.docs.retrieve_documentation",
        )

    registry.register(
        ToolSpec(
            name="get_analytics_methodology",
            family="platform",
            summary="How a FIO metric or engine is actually computed (from the docs).",
            description=(
                "Retrieve the FIO documentation for a methodology question (how a score is "
                "computed, what a coverage number means, which limitations apply)."
            ),
            input_model=DocsQueryInput,
            handler=get_analytics_methodology,
            service="llm.tools.docs.retrieve_documentation",
            data_source="docs/*.md",
        )
    )


def build_tool_registry() -> ToolRegistry:
    """The registry used by the grounded copilot."""
    from app.llm.tools.hints import apply_tool_hints

    registry = ToolRegistry()
    _register(registry)
    return apply_tool_hints(registry)
