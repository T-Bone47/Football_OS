"""Country-priority registry (Phase 3B).

The priority countries come from a *dated snapshot file*, never from a hardcoded list
in code. Administrators change the selection by pointing the loader at another
snapshot; the ingestion planner reads the registry from the database.

Two coverage measures are kept apart on purpose:

* ``national-team coverage`` — players identified with a nationality in the registry.
* ``club coverage`` — players discovered through club competitions and squad
  registrations for clubs in the selected countries.

A player of a selected nationality may play anywhere in the world, so the second
measure can only be a sample of the first population — never a replacement for it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.expansion import CountryPriority

DEFAULT_SNAPSHOT_NAME = "country_priority_snapshot_2026-10-07.json"


@dataclass(frozen=True)
class CountrySnapshot:
    snapshot_id: str
    ranking_name: str
    scope: str
    ranking_source: str
    ranking_snapshot_date: date
    countries: tuple[dict[str, Any], ...]


def registry_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "data" / "registry"


def load_snapshot(path: str | Path | None = None) -> CountrySnapshot:
    """Load a country-priority snapshot from disk."""
    target = Path(path) if path else registry_dir() / DEFAULT_SNAPSHOT_NAME
    payload = json.loads(target.read_text(encoding="utf-8"))
    return CountrySnapshot(
        snapshot_id=payload["snapshot_id"],
        ranking_name=payload["ranking_name"],
        scope=payload["scope"],
        ranking_source=payload["ranking_source"],
        ranking_snapshot_date=date.fromisoformat(payload["ranking_snapshot_date"]),
        countries=tuple(payload["countries"]),
    )


async def seed_country_priorities(
    session: AsyncSession, snapshot: CountrySnapshot | None = None
) -> dict[str, Any]:
    """Load a snapshot into `country_priorities`.

    Existing rows for the same country are updated in place (rank, source, date), so
    the registry keeps a single, auditable row per country.
    """
    snapshot = snapshot or load_snapshot()
    inserted = 0
    updated = 0
    for entry in snapshot.countries:
        existing = (
            await session.execute(
                select(CountryPriority).where(
                    CountryPriority.country_code == entry["country_code"]
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                CountryPriority(
                    country_code=entry["country_code"],
                    country_name=entry["country_name"],
                    rank=entry["rank"],
                    ranking_source=snapshot.ranking_source,
                    ranking_snapshot_date=snapshot.ranking_snapshot_date,
                    scope_label=snapshot.scope,
                    is_active=True,
                    notes=entry.get("provider_nationality"),
                )
            )
            inserted += 1
            continue
        existing.country_name = entry["country_name"]
        existing.rank = entry["rank"]
        existing.ranking_source = snapshot.ranking_source
        existing.ranking_snapshot_date = snapshot.ranking_snapshot_date
        existing.scope_label = snapshot.scope
        existing.notes = entry.get("provider_nationality")
        updated += 1
    await session.commit()
    return {
        "snapshot_id": snapshot.snapshot_id,
        "ranking_source": snapshot.ranking_source,
        "ranking_snapshot_date": snapshot.ranking_snapshot_date.isoformat(),
        "scope": snapshot.scope,
        "inserted": inserted,
        "updated": updated,
        "countries": len(snapshot.countries),
    }


async def active_priorities(session: AsyncSession) -> list[CountryPriority]:
    rows = (
        await session.execute(
            select(CountryPriority)
            .where(CountryPriority.is_active.is_(True))
            .order_by(CountryPriority.rank.asc())
        )
    ).scalars().all()
    return list(rows)


async def provider_nationalities(session: AsyncSession) -> list[str]:
    """Provider spellings for the selected countries (used for nationality filters)."""
    rows = await active_priorities(session)
    names: list[str] = []
    for row in rows:
        if row.notes:
            names.append(row.notes)
        names.append(row.country_name)
    return names
