"""Real ingestion evidence: StatsBomb open data, 2015/16 top-five leagues.

Runs the production pipeline (provider request -> contract check -> SHA-256
Bronze snapshot -> DataSnapshot/IngestionRun -> Silver) against the real
provider, then re-runs one job to show idempotency, and re-hashes every
stored snapshot. Usage:

    DATABASE_URL=postgresql+asyncpg://.../fios_p17_live python scripts/evidence/ingestion_evidence.py
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

from common import ROOT, write_evidence

SEASONS = [  # (competition_id, season_id, label) from the StatsBomb competitions index
    (2, 27, "Premier League 2015/2016"),
    (11, 27, "La Liga 2015/2016"),
    (9, 27, "1. Bundesliga 2015/2016"),
    (12, 27, "Serie A 2015/2016"),
    (7, 27, "Ligue 1 2015/2016"),
]


async def main() -> int:
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.models.canonical import Match
    from app.db.models.provenance import DataSnapshot
    from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
    from app.phase17.live_ingestion import LiveIngestionRunner
    from app.phase17.rate_governor import RateGovernor

    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    store_root = ROOT / "data" / "bronze"
    jobs, statuses = [], set()
    async with Session() as s:
        runner = LiveIngestionRunner(s, LocalFilesystemSnapshotStore(store_root), governor=RateGovernor())
        for comp, season, label in SEASONS:
            r = await runner.run_job("statsbomb", "matches", {"competition_id": comp, "season_id": season})
            d = r.to_dict()
            jobs.append({"label": label, "status": d["status"], "snapshot_sha256": d["snapshot_sha256"],
                         "records": d.get("records"), "errors": d.get("errors")})
            statuses.add(d["status"])
        # idempotency: the same request again must give the same bytes and no Silver delta
        before = (await s.execute(select(func.count()).select_from(Match))).scalar()
        again = (await runner.run_job("statsbomb", "matches", {"competition_id": 2, "season_id": 27})).to_dict()
        after = (await s.execute(select(func.count()).select_from(Match))).scalar()
        snaps = (await s.execute(select(DataSnapshot.sha256, DataSnapshot.storage_location))).all()
    await engine.dispose()

    rehash = {"checked": 0, "mismatches": []}
    for sha, location in snaps:
        p = Path(location)
        if not p.is_absolute():
            p = store_root / location
        if not p.exists():
            rehash["mismatches"].append({"sha256": sha, "reason": "file missing"})
            continue
        rehash["checked"] += 1
        if hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            rehash["mismatches"].append({"sha256": sha, "reason": "content hash differs"})

    first_pl = next(j for j in jobs if j["label"].startswith("Premier League"))
    idempotent = again["snapshot_sha256"] == first_pl["snapshot_sha256"] and before == after
    ok = statuses == {"SUCCESS"} and idempotent and not rehash["mismatches"]
    write_evidence(
        "ingestion_evidence", " ".join(sys.argv),
        inputs={"provider": "statsbomb (open data, historical archive)", "seasons": [s[2] for s in SEASONS],
                "database": url.rsplit("/", 1)[-1]},
        outputs={"jobs": jobs, "idempotency": {"rerun_status": again["status"], "same_sha256": idempotent,
                                                "silver_matches_before": before, "silver_matches_after": after},
                 "bronze_rehash": rehash},
        status="VERIFIED" if ok else "FAILED",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(asyncio.run(main()))
