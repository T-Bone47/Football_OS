"""Data source registry (Phase 6, licensing and exclusion policy).

Every provider we may ingest from is registered with its licence, attribution
requirement, redistribution permission and enablement state. Ingestion must not run
against a source that is disabled, and no source is enabled without a recorded
terms review.

This registry is the single place that answers "may we store and re-serve this
data?" — it is consulted before a provider is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.provenance import DataSource


@dataclass(frozen=True)
class SourcePolicy:
    name: str
    base_url: str | None
    license: str
    license_url: str | None
    attribution: str | None
    redistribution_allowed: bool
    enabled: bool
    notes: str
    evaluated_on: str = "2026-10-21"


#: The evaluated provider set. `enabled=False` means "registered but not ingested from".
SOURCE_POLICIES: tuple[SourcePolicy, ...] = (
    SourcePolicy(
        name="api-football",
        base_url="https://v3.football.api-sports.io",
        license="Commercial API — Free plan (personal use; attribution required)",
        license_url="https://www.api-football.com/",
        attribution="Data provided by API-Football",
        redistribution_allowed=False,
        enabled=True,
        notes=(
            "Free plan: 100 requests/day, 10 requests/minute, `page` capped at 3 on every "
            "paginated endpoint, seasons 2022-2024. Internal analytics use only; the raw "
            "records are not redistributed."
        ),
    ),
    SourcePolicy(
        name="statsbomb",
        base_url="https://raw.githubusercontent.com/statsbomb/open-data/master/data",
        license="CC BY-NC-SA 4.0 (StatsBomb Open Data)",
        license_url="https://github.com/statsbomb/open-data",
        attribution="StatsBomb Open Data, retrieved from github.com/statsbomb/open-data",
        redistribution_allowed=False,
        enabled=True,
        notes=(
            "Open-data releases are non-commercial and share-alike: match events, lineups and "
            "360 data for the competitions FIFA published. Historical research data, not live "
            "coverage. Attribution must be kept with derived work."
        ),
    ),
    SourcePolicy(
        name="football-data-org",
        base_url="https://api.football-data.org/v4",
        license="Free tier — token required (not configured)",
        license_url="https://www.football-data.org/documentation/api",
        attribution="football-data.org",
        redistribution_allowed=False,
        enabled=False,
        notes=(
            "Adapter exists but no token is configured, so the source is registered but "
            "disabled. It carries fixtures/standings, not a full player universe, so it "
            "would not close the player-coverage gap on its own."
        ),
    ),
    SourcePolicy(
        name="openligadb",
        base_url="https://api.openligadb.de/",
        license="Open data (no key required)",
        license_url="https://www.openligadb.de/",
        attribution="OpenLigaDB",
        redistribution_allowed=True,
        enabled=False,
        notes=(
            "German league fixtures, results and standings only. It carries no player "
            "profiles or player statistics, so it cannot add players to the canonical "
            "universe; it is only a fixture-completeness supplement."
        ),
    ),
    SourcePolicy(
        name="thesportsdb",
        base_url="https://www.thesportsdb.com/api.php",
        license="Free API tier (test key) — descriptive metadata",
        license_url="https://www.thesportsdb.com/api.php",
        attribution="TheSportsDB",
        redistribution_allowed=False,
        enabled=False,
        notes=(
            "Descriptive team/player metadata with weaker provenance than the canonical "
            "sources. It must never overwrite a stronger canonical fact; no adapter is "
            "implemented while it cannot measurably close a coverage gap."
        ),
    ),
)


async def seed_sources(session: AsyncSession) -> dict[str, Any]:
    """Register/refresh every evaluated source with its licence metadata."""
    inserted: list[str] = []
    updated: list[str] = []
    for policy in SOURCE_POLICIES:
        row = (
            await session.execute(select(DataSource).where(DataSource.name == policy.name))
        ).scalar_one_or_none()
        if row is None:
            session.add(
                DataSource(
                    name=policy.name,
                    base_url=policy.base_url,
                    license=policy.license,
                    license_url=policy.license_url,
                    attribution=policy.attribution,
                    redistribution_allowed=policy.redistribution_allowed,
                    enabled=policy.enabled,
                    terms_reviewed_at=datetime.fromisoformat(policy.evaluated_on).replace(
                        tzinfo=timezone.utc
                    ),
                    notes=policy.notes,
                )
            )
            inserted.append(policy.name)
            continue
        row.base_url = policy.base_url
        row.license = policy.license
        row.license_url = policy.license_url
        row.attribution = policy.attribution
        row.redistribution_allowed = policy.redistribution_allowed
        row.enabled = policy.enabled
        row.notes = policy.notes
        updated.append(policy.name)
    await session.commit()
    return {"inserted": inserted, "updated": updated, "sources": len(SOURCE_POLICIES)}


async def source_policies(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(DataSource).order_by(DataSource.name))).scalars().all()
    return [
        {
            "name": row.name,
            "base_url": row.base_url,
            "license": row.license,
            "license_url": row.license_url,
            "attribution": row.attribution,
            "redistribution_allowed": row.redistribution_allowed,
            "enabled": row.enabled,
            "terms_reviewed_at": row.terms_reviewed_at.isoformat() if row.terms_reviewed_at else None,
            "notes": row.notes,
        }
        for row in rows
    ]
