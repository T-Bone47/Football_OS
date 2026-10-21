"""Ingestion scope planning (Phase 3/4).

A *scope* is one provider query plus the metadata needed to resume it, budget it and
report its coverage honestly. Scopes are produced from configuration (the priority
league registry and the dated country-priority snapshot), never from a hardcoded
list inside the ingestion code.

Two scope shapes are used for the player universe:

``teams``
    ``teams?league=<id>&season=<year>`` — one request, the club list of the scope.

``players``
    ``players?team=<team id>&season=<year>`` — the club's registered players.

The per-team shape is deliberate: the API-Football Free plan caps `page` at 3 for
*every* paginated endpoint, so a league-scoped player query can only ever reach 3
pages of a 51-page result set. A per-team query returns the same number of records
per request but completes the club instead of slicing the league, so the reachable
universe is maximised inside the plan limit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
from app.ingestion.checkpoints import scope_key

REGISTRY_DIR = Path(__file__).resolve().parents[4] / "data" / "registry"
DEFAULT_LEAGUE_REGISTRY = "priority_leagues.json"


@dataclass(frozen=True)
class PriorityCompetition:
    key: str
    provider: str
    provider_competition_id: str
    name: str
    country: str
    priority: int
    default_seasons: tuple[int, ...]


@dataclass
class IngestionScope:
    provider: str
    resource: str
    entity_type: str
    params: dict[str, Any]
    priority: int
    competition: str | None = None
    season: str | None = None
    max_pages: int = 3
    paginated: bool = True
    note: str = ""

    @property
    def scope_key(self) -> str:
        return scope_key(self.params)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "resource": self.resource,
            "entity_type": self.entity_type,
            "params": self.params,
            "priority": self.priority,
            "competition": self.competition,
            "season": self.season,
            "max_pages": self.max_pages,
            "paginated": self.paginated,
            "scope_key": self.scope_key,
            "note": self.note,
        }


@dataclass
class ScopePlan:
    scopes: list[IngestionScope] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_count": len(self.scopes),
            "estimated_requests": sum(scope.max_pages for scope in self.scopes),
            "scopes": [scope.to_dict() for scope in self.scopes],
            "warnings": list(self.warnings),
        }


def load_priority_competitions(path: str | Path | None = None) -> list[PriorityCompetition]:
    target = Path(path) if path else REGISTRY_DIR / DEFAULT_LEAGUE_REGISTRY
    payload = json.loads(target.read_text(encoding="utf-8"))
    competitions = [
        PriorityCompetition(
            key=entry["key"],
            provider=entry.get("provider", "api-football"),
            provider_competition_id=str(entry["provider_competition_id"]),
            name=entry["name"],
            country=entry.get("country", "Unknown"),
            priority=int(entry.get("priority", 99)),
            default_seasons=tuple(int(season) for season in entry.get("default_seasons", [])),
        )
        for entry in payload["competitions"]
    ]
    competitions.sort(key=lambda item: item.priority)
    return competitions


async def _teams_from_last_run(
    session: AsyncSession, provider: str, competition_id: str, season: int
) -> list[dict[str, Any]]:
    """Read the club list of a scope from its most recent successful `teams` snapshot."""
    rows = (
        await session.execute(
            select(IngestionRun, DataSnapshot)
            .join(DataSource, DataSource.id == IngestionRun.data_source_id)
            .join(DataSnapshot, DataSnapshot.ingestion_run_id == IngestionRun.id)
            .where(
                DataSource.name == provider,
                IngestionRun.endpoint == "teams",
            )
            .order_by(IngestionRun.finished_at.desc())
        )
    ).all()
    for run, snapshot in rows:
        parameters = dict(run.parameters or {})
        if str(parameters.get("league")) != str(competition_id):
            continue
        if str(parameters.get("season")) != str(season):
            continue
        try:
            payload = json.loads(Path(snapshot.storage_location).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        teams: list[dict[str, Any]] = []
        for entry in payload.get("response") or []:
            team = entry.get("team") or {}
            if team.get("id") is None:
                continue
            teams.append(
                {
                    "id": str(team["id"]),
                    "name": team.get("name") or team.get("shortname") or str(team["id"]),
                    "country": (entry.get("league") or {}).get("country") or "",
                }
            )
        if teams:
            return teams
    return []


async def plan_league_season(
    session: AsyncSession,
    competition: PriorityCompetition,
    season: int,
    *,
    plan_page_cap: int = 3,
    include_teams_scope: bool = True,
) -> ScopePlan:
    """Build the scope plan for one competition-season."""
    plan = ScopePlan()
    base_priority = competition.priority * 1000

    if include_teams_scope:
        plan.scopes.append(
            IngestionScope(
                provider=competition.provider,
                resource="teams",
                entity_type="teams",
                params={"league": competition.provider_competition_id, "season": season},
                priority=base_priority,
                competition=competition.name,
                season=str(season),
                max_pages=1,
                paginated=False,
                note="club discovery for the scope",
            )
        )

    teams = await _teams_from_last_run(
        session, competition.provider, competition.provider_competition_id, season
    )
    if not teams:
        plan.warnings.append(
            f"No ingested club list for {competition.name} {season}; "
            "run the `teams` scope first to discover the clubs."
        )
        return plan

    for team in teams:
        plan.scopes.append(
            IngestionScope(
                provider=competition.provider,
                resource="players",
                entity_type="players",
                params={"team": team["id"], "season": season},
                priority=base_priority + 10,
                competition=competition.name,
                season=str(season),
                max_pages=plan_page_cap,
                note=f"club squad: {team['name']}",
            )
        )
    return plan


async def discover_seasons(
    session: AsyncSession, competition: PriorityCompetition
) -> list[int]:
    """Seasons the provider actually lists for a competition.

    Read from the ingested `/leagues` catalogue; falls back to the configured default
    seasons when the catalogue has not been ingested.
    """
    rows = (
        await session.execute(
            select(IngestionRun, DataSnapshot)
            .join(DataSource, DataSource.id == IngestionRun.data_source_id)
            .join(DataSnapshot, DataSnapshot.ingestion_run_id == IngestionRun.id)
            .where(
                DataSource.name == competition.provider,
                IngestionRun.endpoint == "leagues",
            )
            .order_by(IngestionRun.finished_at.desc())
        )
    ).all()
    seasons: set[int] = set()
    for _run, snapshot in rows:
        try:
            payload = json.loads(Path(snapshot.storage_location).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for entry in payload.get("response") or []:
            league = entry.get("league") or {}
            if str(league.get("id")) != competition.provider_competition_id:
                continue
            for season in entry.get("seasons") or []:
                year = season.get("year")
                if isinstance(year, int):
                    seasons.add(year)
        if seasons:
            break
    if not seasons:
        return list(competition.default_seasons)
    return sorted(seasons, reverse=True)
