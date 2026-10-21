"""Backfill season-window role features/profiles from persisted season stats.

Root cause this addresses: the role pipeline reads ``FeatureSnapshot`` rows
that are built from ``player_match_stats``. When a canonical index has no
per-match rows, those snapshots carry 0 minutes and every profile is
``INSUFFICIENT_SAMPLE`` even though real season statistics are stored.

This tool writes an explicit ``player_season_v1`` feature snapshot (window
``season``) from the latest season's persisted ``player_season_stats`` and
runs the existing rules-based profiler against it. It never invents values:
missing provider fields stay absent and fall back to the profiler defaults.

Usage (repository root):

    python tools/backfill_season_role_profiles.py
    python tools/backfill_season_role_profiles.py --min-minutes 450
    python tools/backfill_season_role_profiles.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, time as dt_time, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models.canonical import (
    CompetitionSeason,
    FeatureSnapshot,
    Player,
    PlayerSeasonStats,
)
from app.roles.season_features import WINDOW, build_season_role_features
from app.roles.service import RoleService

FEATURE_SET = "player_season_v1"
FEATURE_SET_VERSION = "role_feature_set_season_v1"
CALCULATION_VERSION = "1.0.0"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-minutes", type=int, default=0)
    parser.add_argument("--player", type=str, action="append", default=None, help="player UUID (repeatable)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    return parser


def _latest_season_rows(rows: list[PlayerSeasonStats]) -> list[PlayerSeasonStats]:
    def end_year(row: PlayerSeasonStats) -> int:
        cs = row.competition_season
        season = cs.season if cs else None
        return season.end_year if season and season.end_year else 0

    if not rows:
        return []
    latest = max(end_year(r) for r in rows)
    # A row without a resolved season stays out of a "latest season" claim.
    return [r for r in rows if end_year(r) == latest and latest > 0]


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    as_of = datetime.combine(datetime.now(timezone.utc).date(), dt_time.min, tzinfo=timezone.utc)
    summary: dict = {
        "as_of": as_of.isoformat(),
        "feature_set": FEATURE_SET,
        "feature_set_version": FEATURE_SET_VERSION,
        "window": WINDOW,
        "players_considered": 0,
        "profiles_written": 0,
        "qualified": 0,
        "insufficient": 0,
        "skipped_no_season": 0,
        "below_min_minutes": 0,
        "players": [],
        "dry_run": args.dry_run,
    }
    try:
        async with Session() as session:
            stmt = (
                select(Player)
                .where(Player.season_stats.any())
                .options(
                    selectinload(Player.season_stats)
                    .selectinload(PlayerSeasonStats.competition_season)
                    .selectinload(CompetitionSeason.season)
                )
                .order_by(Player.name)
            )
            if args.player:
                import uuid as _uuid

                wanted = [_uuid.UUID(p) for p in args.player]
                stmt = stmt.where(Player.id.in_(wanted))
            if args.limit:
                stmt = stmt.limit(args.limit)

            players = (await session.execute(stmt)).scalars().all()
            summary["players_considered"] = len(players)
            role_service = RoleService(session)

            for player in players:
                rows = _latest_season_rows(list(player.season_stats))
                if not rows:
                    summary["skipped_no_season"] += 1
                    continue
                features = build_season_role_features(rows)
                minutes = int(features.get("minutes_season") or 0)
                if minutes < args.min_minutes:
                    summary["below_min_minutes"] += 1
                    continue

                season_names = sorted(
                    {
                        r.competition_season.season.name
                        for r in rows
                        if r.competition_season and r.competition_season.season
                    }
                )
                provenance = {
                    "source_entity": "player_season_stats",
                    "source_stat_ids": [str(r.id) for r in rows],
                    "source_snapshot_ids": [str(r.snapshot_id) for r in rows if r.snapshot_id],
                    "season_names": season_names,
                    "window": WINDOW,
                    "calculation_version": CALCULATION_VERSION,
                    "as_of": as_of.isoformat(),
                    "note": "Season aggregate per-90 features; not a last-5 match window.",
                }

                if not args.dry_run:
                    snap_stmt = select(FeatureSnapshot).where(
                        FeatureSnapshot.entity_type == "player",
                        FeatureSnapshot.entity_id == player.id,
                        FeatureSnapshot.feature_set == FEATURE_SET,
                        FeatureSnapshot.calculation_version == CALCULATION_VERSION,
                        FeatureSnapshot.as_of == as_of,
                    )
                    snapshot = (await session.execute(snap_stmt)).scalar_one_or_none()
                    if snapshot is None:
                        snapshot = FeatureSnapshot(
                            entity_type="player",
                            entity_id=player.id,
                            feature_set=FEATURE_SET,
                            calculation_version=CALCULATION_VERSION,
                            as_of=as_of,
                            features=features,
                            provenance=provenance,
                        )
                        session.add(snapshot)
                    else:
                        snapshot.features = features
                        snapshot.provenance = provenance
                    await session.flush()

                    profile = await role_service.compute_and_save_role_profile(
                        player.id,
                        as_of=as_of,
                        feature_set_version=FEATURE_SET_VERSION,
                        feature_set=FEATURE_SET,
                        feature_window=WINDOW,
                    )
                    status = profile.role_status
                else:
                    status = "DRY_RUN"

                if status == "QUALIFIED":
                    summary["qualified"] += 1
                elif status == "INSUFFICIENT_SAMPLE":
                    summary["insufficient"] += 1
                summary["profiles_written"] += 0 if args.dry_run else 1
                summary["players"].append(
                    {
                        "player_id": str(player.id),
                        "name": player.name,
                        "position": player.primary_position,
                        "season": season_names,
                        "minutes": minutes,
                        "appearances": features.get("sample_matches_season"),
                        "status": status,
                    }
                )

            if not args.dry_run:
                await session.commit()
    finally:
        await engine.dispose()

    print(json.dumps(summary, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
