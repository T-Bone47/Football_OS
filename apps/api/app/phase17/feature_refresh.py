"""Dependency-driven feature refresh (§12).

Feature `team_form_v1` for a club in a competition season depends on the
set of FINISHED Silver matches involving that club. Its version is the
SHA-256 of that dependency set. A refresh recomputes only when the version
changed; otherwise it records UNCHANGED and does no computation.

`feature_staleness()` is what inference uses: if Silver has moved since the
last refresh, the stored feature version no longer matches and the feature
is STALE — inference must refuse rather than serve on it.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Match
from app.db.models.operations import FeatureRefreshRecord
from app.phase17 import FeatureRefreshState

FEATURE_NAME = "team_form_v1"
FINISHED = ("FINISHED", "FT", "AET", "PEN")


@dataclass
class RefreshOutcome:
    feature: str
    entity_id: str
    status: FeatureRefreshState
    previous_version: str | None
    new_version: str | None
    computed: bool
    values: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"feature": self.feature, "entity_id": self.entity_id, "status": self.status.value,
                "previous_version": self.previous_version, "new_version": self.new_version,
                "computed": self.computed, "values": self.values}


async def _club_matches(session: AsyncSession, club_id: uuid.UUID, competition_season_id: uuid.UUID) -> list[Match]:
    return list((await session.execute(
        select(Match).where(
            Match.competition_season_id == competition_season_id,
            Match.status.in_(FINISHED),
            or_(Match.home_club_id == club_id, Match.away_club_id == club_id),
        ).order_by(Match.date.asc())
    )).scalars().all())


def dependency_version(matches: list[Match]) -> str:
    dep = [[str(m.id), m.date.isoformat(), str(m.home_club_id), str(m.away_club_id), m.home_score, m.away_score]
           for m in matches]
    return hashlib.sha256(json.dumps(dep, sort_keys=True).encode()).hexdigest()[:16]


def compute_team_form(club_id: uuid.UUID, matches: list[Match]) -> dict[str, Any]:
    gf = ga = pts = 0
    last5: list[int] = []
    for m in matches:
        home = m.home_club_id == club_id
        f, a = (m.home_score, m.away_score) if home else (m.away_score, m.home_score)
        f, a = f or 0, a or 0
        gf += f
        ga += a
        p = 3 if f > a else 1 if f == a else 0
        pts += p
        last5 = (last5 + [p])[-5:]
    n = len(matches)
    return {
        "matches": n,
        "points_per_game": round(pts / n, 4),
        "goals_for_per_game": round(gf / n, 4),
        "goals_against_per_game": round(ga / n, 4),
        "last5_points": sum(last5),
        "last_match_date": matches[-1].date.isoformat(),
    }


async def latest_record(session: AsyncSession, entity_id: str, feature: str = FEATURE_NAME) -> FeatureRefreshRecord | None:
    return (await session.execute(
        select(FeatureRefreshRecord)
        .where(FeatureRefreshRecord.feature == feature, FeatureRefreshRecord.entity_id == entity_id,
               FeatureRefreshRecord.status.in_([FeatureRefreshState.REFRESHED.value,
                                                FeatureRefreshState.UNCHANGED.value]))
        .order_by(FeatureRefreshRecord.refreshed_at.desc()).limit(1)
    )).scalar_one_or_none()


async def refresh_club(session: AsyncSession, club_id: uuid.UUID, competition_season_id: uuid.UUID) -> RefreshOutcome:
    entity = f"{club_id}@{competition_season_id}"
    source = f"silver.matches[competition_season={competition_season_id}, club={club_id}, status=FINISHED]"
    previous = await latest_record(session, entity)
    prev_version = previous.new_version if previous else None
    now = datetime.now(timezone.utc)
    try:
        matches = await _club_matches(session, club_id, competition_season_id)
        if not matches:
            status, version, values, computed = FeatureRefreshState.INSUFFICIENT_DATA, None, {}, False
        else:
            version = dependency_version(matches)
            if version == prev_version:
                status, values, computed = FeatureRefreshState.UNCHANGED, previous.values, False
            else:
                status, values, computed = FeatureRefreshState.REFRESHED, compute_team_form(club_id, matches), True
    except Exception as exc:  # noqa: BLE001 — a failed refresh is recorded, never silently skipped
        status, version, values, computed = FeatureRefreshState.FAILED, None, {"error": str(exc)}, False
    session.add(FeatureRefreshRecord(feature=FEATURE_NAME, entity_id=entity, source_dependency=source,
                                     previous_version=prev_version, new_version=version, status=status.value,
                                     values=values, refreshed_at=now))
    await session.flush()
    return RefreshOutcome(FEATURE_NAME, entity, status, prev_version, version, computed, values)


async def refresh_competition_season(session: AsyncSession, competition_season_id: uuid.UUID) -> list[RefreshOutcome]:
    rows = (await session.execute(
        select(Match.home_club_id, Match.away_club_id).where(Match.competition_season_id == competition_season_id)
    )).all()
    clubs = sorted({c for r in rows for c in r}, key=str)
    outcomes = [await refresh_club(session, c, competition_season_id) for c in clubs]
    await session.commit()
    return outcomes


async def feature_staleness(session: AsyncSession, club_id: uuid.UUID, competition_season_id: uuid.UUID) -> dict[str, Any]:
    """FRESH if the stored version equals the current Silver dependency."""
    entity = f"{club_id}@{competition_season_id}"
    record = await latest_record(session, entity)
    matches = await _club_matches(session, club_id, competition_season_id)
    current = dependency_version(matches) if matches else None
    if record is None:
        return {"entity_id": entity, "state": "NEVER_REFRESHED", "stored_version": None, "current_version": current}
    state = "FRESH" if record.new_version == current else "STALE"
    return {"entity_id": entity, "state": state, "stored_version": record.new_version, "current_version": current,
            "refreshed_at": record.refreshed_at.isoformat()}
