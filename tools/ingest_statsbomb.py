#!/usr/bin/env python3
"""StatsBomb Open Data ingestion.

The second structured source. StatsBomb's open data needs no key and has no request
quota, so it can be ingested while the API-Football daily budget is exhausted.

What it contributes to the canonical layer:

* **matches** — fixtures with competition, season, clubs, kick-off and score;
* **lineups** — the players who played, their position, jersey number and starter
  flag, resolved onto canonical players (StatsBomb player ids are per match, so the
  human is resolved by name + country + shared club, never by id);
* **events** — the match event stream, with the source-native event type preserved;
* **player match statistics** — minutes *derived* from the lineup position
  intervals, and goals/assists counted from the event stream. Both are labelled as
  derived in the stored row.

Every processed match is checkpointed, so an interrupted run resumes instead of
restarting, and the processed subset is always explicit.

Examples
--------
List the competition-seasons StatsBomb publishes::

    python tools/ingest_statsbomb.py catalogue

Ingest 20 matches of a competition-season (lineups + events)::

    python tools/ingest_statsbomb.py run --competition-id 2 --season-id 27 --max-matches 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun  # noqa: E402
from app.ingestion.capability_registry import CapabilityRegistry  # noqa: E402
from app.ingestion.checkpoints import COMPLETE, PARTIAL, PENDING, CheckpointStore  # noqa: E402
from app.ingestion.service import IngestionService  # noqa: E402
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore  # noqa: E402
from app.normalization.statsbomb import StatsbombNormalizer  # noqa: E402
from app.providers.registry import default_registry  # noqa: E402

STATSBOMB = "statsbomb"


async def _fetch(provider_name: str, resource: str, **params: Any) -> dict[str, Any]:
    provider = default_registry.get(provider_name)
    try:
        raw = await provider.fetch(resource, **params)
        return json.loads(raw.content.decode("utf-8"))
    finally:
        await provider.close()


async def catalogue() -> int:
    """Print the competition-season catalogue StatsBomb publishes."""
    payload = await _fetch(STATSBOMB, "competitions")
    print(f"competition-seasons: {len(payload)}")
    for entry in payload:
        print(
            f"competition_id={entry.get('competition_id')} season_id={entry.get('season_id')} "
            f"{entry.get('competition_name')} {entry.get('season_name')} ({entry.get('country_name')})"
        )
    return 0


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    summary: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "provider": STATSBOMB,
        "competition_id": args.competition_id,
        "season_id": args.season_id,
        "matches": [],
    }
    try:
        async with Session() as session:
            store = CheckpointStore(session)
            normalizer = StatsbombNormalizer(session)
            service = IngestionService(
                session=session,
                provider_registry=default_registry,
                snapshot_store=LocalFilesystemSnapshotStore(settings.snapshot_storage_path),
                capability_registry=CapabilityRegistry(session),
            )

            matches = await _fetch(
                STATSBOMB,
                "matches",
                competition_id=args.competition_id,
                season_id=args.season_id,
            )
            summary["matches_available"] = len(matches)

            processed = 0
            for match_payload in matches:
                match_id = match_payload.get("match_id")
                if match_id is None:
                    continue
                scope_params = {"match_id": match_id}
                state = await store.state(STATSBOMB, "match", scope_params)
                if state and state.status == COMPLETE and not args.force:
                    summary["matches"].append(
                        {"match_id": match_id, "action": "SKIPPED_ALREADY_COMPLETE"}
                    )
                    continue
                if args.max_matches and processed >= args.max_matches:
                    summary["matches"].append({"match_id": match_id, "action": "SKIPPED_MATCH_LIMIT"})
                    continue

                match, counters = await normalizer.normalize_match(match_payload)
                if match is None:
                    summary["matches"].append({"match_id": match_id, "action": "SKIPPED_INVALID"})
                    continue

                lineups = await _fetch(STATSBOMB, "lineups", match_id=match_id)
                lineup_counters = await normalizer.normalize_lineups(lineups, match)

                event_counters = {"events": 0, "goals": 0, "assists": 0}
                if not args.skip_events:
                    events = await _fetch(STATSBOMB, "events", match_id=match_id)
                    event_counters = await normalizer.normalize_events(events, match)

                await session.commit()
                processed += 1
                await store.record(
                    provider=STATSBOMB,
                    entity_type="match",
                    params=scope_params,
                    status=COMPLETE,
                    page=1,
                    records_seen=len(lineups),
                    records_written=lineup_counters.get("player_match_stats", 0),
                )
                summary["matches"].append(
                    {
                        "match_id": match_id,
                        "action": "INGESTED",
                        "counters": {**counters, **lineup_counters, **event_counters},
                    }
                )
                if args.request_interval:
                    await asyncio.sleep(args.request_interval)
    finally:
        await engine.dispose()

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["status"] = "COMPLETE"
    print(json.dumps(summary, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["catalogue", "run"])
    parser.add_argument("--competition-id", type=int, required=False)
    parser.add_argument("--season-id", type=int, required=False)
    parser.add_argument("--max-matches", type=int, default=20)
    parser.add_argument("--request-interval", type=float, default=0.4)
    parser.add_argument("--skip-events", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "catalogue":
        return asyncio.run(catalogue())
    if args.competition_id is None or args.season_id is None:
        parser.error("--competition-id and --season-id are required for `run`")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
