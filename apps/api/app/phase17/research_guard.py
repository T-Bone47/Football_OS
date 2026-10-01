"""Research dataset manifests with an enforced cutoff (§30, adversarial 20).

A research experiment declares a cutoff; the dataset it receives contains
only matches strictly before that cutoff. The manifest states the cutoff,
a dataset version (hash of the exact rows), whether the data is live or
historical, competition coverage and sample size — and re-checks that no
row is at or after the cutoff before returning.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Competition, CompetitionSeason, Match
from app.phase17.match_state import PROVIDER_TIMING
from app.phase17.model_ops import FINISHED, competition_key


class FutureDataContamination(RuntimeError):
    pass


async def research_dataset(session: AsyncSession, cutoff: datetime, competitions: list[str] | None = None) -> dict[str, Any]:
    stmt = (select(Match, Competition).join(CompetitionSeason, Match.competition_season_id == CompetitionSeason.id)
            .join(Competition, CompetitionSeason.competition_id == Competition.id)
            .where(Match.date < cutoff, Match.status.in_(FINISHED)).order_by(Match.date.asc()))
    rows = (await session.execute(stmt)).all()
    if competitions:
        rows = [(m, c) for m, c in rows if competition_key(c) in competitions]
    if any(m.date >= cutoff for m, _ in rows):
        raise FutureDataContamination("dataset contains a match at/after the declared cutoff")
    records = [[str(m.id), m.date.isoformat(), m.home_score, m.away_score] for m, _ in rows]
    coverage: dict[str, int] = {}
    providers: set[str] = set()
    for m, c in rows:
        coverage[competition_key(c)] = coverage.get(competition_key(c), 0) + 1
        providers.add(m.provider)
    modes = {PROVIDER_TIMING.get(p, {}).get("data_mode", "UNKNOWN") for p in providers}
    return {
        "declared_cutoff": cutoff.isoformat(),
        "dataset_version": hashlib.sha256(json.dumps(records).encode()).hexdigest()[:16],
        "sample_size": len(records),
        "max_observation": records[-1][1] if records else None,
        "competition_coverage": coverage,
        "data_mode": "HISTORICAL" if modes <= {"HISTORICAL_ARCHIVE"} else "MIXED_OR_LIVE",
        "providers": sorted(providers),
        "future_data_check": "PASS",
    }
