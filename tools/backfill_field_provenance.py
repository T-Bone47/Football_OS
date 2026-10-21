#!/usr/bin/env python3
"""Populate field-level provenance from the stored Bronze snapshots.

The record-level provenance already exists (every payload is content-addressed in
`data_snapshots`). The *field* level - "which provider supplied this minute value" -
is recorded by the normaliser, but the rows that were ingested before the recorder
existed have no field provenance.

This script re-normalises the **stored** snapshots. It makes no provider request: the
payloads are already on disk, so the backfill costs no quota and changes no data
other than adding provenance.

    python tools/backfill_field_provenance.py --provider api-football --resource players
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.normalization.service import NormalizationService  # noqa: E402


def snapshot_files(provider: str, resource: str) -> list[Path]:
    directory = ROOT / "data" / "bronze" / provider / resource
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


async def run(provider: str, resource: str) -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    files = snapshot_files(provider, resource)
    if not files:
        print(json.dumps({"status": "FAILED", "error": f"no snapshots for {provider}/{resource}"}))
        return 3
    totals = {"files": 0, "records": 0, "players_inserted": 0, "players_updated": 0, "errors": 0}
    try:
        async with Session() as session:
            normalizer = NormalizationService(session)
            for path in files:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    totals["errors"] += 1
                    print(f"  unreadable {path.name}: {exc}")
                    continue
                try:
                    players, counters = await normalizer.normalize_players_payload(
                        provider, payload, return_stats=True
                    )
                except Exception as exc:  # noqa: BLE001 - report, do not hide
                    totals["errors"] += 1
                    print(f"  failed {path.name}: {type(exc).__name__}: {exc}")
                    continue
                totals["files"] += 1
                totals["records"] += len(players)
                totals["players_inserted"] += int(counters.get("players_inserted", 0))
                totals["players_updated"] += int(counters.get("players_updated", 0))
    finally:
        await engine.dispose()
    print(json.dumps({"status": "OK", **totals}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="api-football")
    parser.add_argument("--resource", default="players")
    args = parser.parse_args()
    return asyncio.run(run(args.provider, args.resource))


if __name__ == "__main__":
    raise SystemExit(main())
