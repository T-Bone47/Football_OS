"""Match state with explicit data timing (§14).

LIVE / HALFTIME are only reported for a provider whose live capability has
been verified AND whose data is younger than LIVE_MAX_AGE_S. No provider
reachable from this environment qualifies, so in practice a match is
SCHEDULED / PRE_MATCH / FINAL, or DATA_DELAYED / DATA_UNAVAILABLE when its
kickoff has passed and no result has arrived.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Match
from app.db.models.provenance import DataSnapshot
from app.phase17 import MatchState

LIVE_MAX_AGE_S = 120
PRE_MATCH_WINDOW = timedelta(hours=2)
EXPECTED_DURATION = timedelta(hours=2, minutes=30)

# What each provider can deliver in principle, and whether that was verified
# by a live request from this deployment. Archive data is never live.
PROVIDER_TIMING = {
    "statsbomb": {"data_mode": "HISTORICAL_ARCHIVE", "live_capable": False, "live_verified": False},
    "api-football": {"data_mode": "NEAR_REAL_TIME_DOCUMENTED", "live_capable": True, "live_verified": False},
    "football-data-org": {"data_mode": "DELAYED_DOCUMENTED", "live_capable": False, "live_verified": False},
}


def _source_timestamp(snapshot: DataSnapshot | None, provider_fixture_id: str | None) -> str | None:
    """StatsBomb stamps every match record with last_updated."""
    if snapshot is None or not snapshot.storage_location or snapshot.storage_location.startswith("s3://"):
        return None
    try:
        payload = json.loads(Path(snapshot.storage_location).read_bytes())
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, list):
        for rec in payload:
            if isinstance(rec, dict) and str(rec.get("match_id")) == str(provider_fixture_id):
                return rec.get("last_updated")
    return None


def derive_state(status: str, kickoff: datetime, now: datetime, timing: dict[str, Any],
                 data_age_s: float | None) -> tuple[MatchState, str]:
    if status in ("FINISHED", "FT", "AET", "PEN"):
        return MatchState.FINAL, "provider reports a final score"
    if now < kickoff - PRE_MATCH_WINDOW:
        return MatchState.SCHEDULED, "kickoff more than 2 h away"
    if now < kickoff:
        return MatchState.PRE_MATCH, "within 2 h of kickoff"
    live_ok = timing.get("live_capable") and timing.get("live_verified") and data_age_s is not None \
        and data_age_s <= LIVE_MAX_AGE_S
    if live_ok and status in ("HT", "HALFTIME"):
        return MatchState.HALFTIME, "verified live provider reports half-time"
    if live_ok and status in ("1H", "2H", "ET", "LIVE", "IN_PLAY"):
        return MatchState.LIVE, f"verified live provider, data age {data_age_s:.0f}s"
    if now < kickoff + EXPECTED_DURATION:
        return MatchState.DATA_DELAYED, "kickoff passed; no verified live feed for this provider"
    return MatchState.DATA_UNAVAILABLE, "expected end passed and no final result received"


async def match_state(session: AsyncSession, match_id: uuid.UUID, now: datetime | None = None) -> dict[str, Any] | None:
    now = now or datetime.now(timezone.utc)
    match = await session.get(Match, match_id)
    if match is None:
        return None
    snapshot = await session.get(DataSnapshot, match.snapshot_id) if match.snapshot_id else None
    timing = PROVIDER_TIMING.get(match.provider, {"data_mode": "UNKNOWN", "live_capable": False, "live_verified": False})
    retrieved = snapshot.provider_retrieved_at if snapshot else None
    age = (now - retrieved).total_seconds() if retrieved else None
    state, why = derive_state(match.status, match.date, now, timing, age)
    return {
        "match_id": str(match.id), "provider": match.provider, "provider_fixture_id": match.provider_fixture_id,
        "state": state.value, "reason": why, "kickoff": match.date.isoformat(),
        "score": {"home": match.home_score, "away": match.away_score},
        "data_mode": timing["data_mode"], "real_time": False if not timing.get("live_verified") else age is not None and age <= LIVE_MAX_AGE_S,
        "source_timestamp": _source_timestamp(snapshot, match.provider_fixture_id),
        "retrieval_timestamp": retrieved.isoformat() if retrieved else None,
        "data_age_seconds": round(age, 1) if age is not None else None,
        "snapshot_sha256": snapshot.sha256 if snapshot else None,
    }
