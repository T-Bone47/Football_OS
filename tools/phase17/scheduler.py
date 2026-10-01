"""Phase 17 scheduler entrypoint (§7).

There is no long-running worker in this repository. This script runs every
schedule that is due and exits; a deployment invokes it from cron/systemd,
e.g. every 10 minutes:

    */10 * * * *  cd /srv/football_os && python tools/phase17/scheduler.py --once

Due-ness comes from the last ops_job_runs row for the job name. LIVE jobs
only run for providers whose last probe was AVAILABLE; ON_DEMAND jobs are
never scheduled. Every execution — including a refused or failed one — is
an ops_job_runs row.

Usage: python tools/phase17/scheduler.py --once [--database-url URL]
Writes: docs/evidence/phase17/scheduler_run.json
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from common import ROOT, now, write_evidence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models.operations import JobRun
from app.ingestion.factory import build_snapshot_store
from app.phase17 import ScheduleClass
from app.phase17.live_ingestion import SCHEDULES, LiveIngestionRunner, reap_stale_jobs
from app.phase17.provider_probe import latest_probe_states

INTERVALS = {
    ScheduleClass.LIVE: timedelta(minutes=1),
    ScheduleClass.DAILY: timedelta(days=1),
    ScheduleClass.WEEKLY: timedelta(days=7),
    ScheduleClass.SEASONAL: timedelta(days=90),
}

# Scope for parameterised jobs. Extending a pilot is a reviewed change to this
# table, never automatic (§50).
JOB_PARAMS = {
    "statsbomb_competitions_index": [{}],
    "statsbomb_season_matches": [{"competition_id": 2, "season_id": 27}, {"competition_id": 43, "season_id": 106},
                                 {"competition_id": 9, "season_id": 281}],
    "api_football_fixtures": [{"league": 39, "season": 2025}],
    "api_football_transfers": [{"team": 42}],
}


async def run_once(database_url: str) -> dict:
    settings = Settings(_env_file=ROOT / ".env", database_url=database_url)
    engine = create_async_engine(database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    out = {"started_at": now(), "executions": [], "skipped": []}
    async with Session() as s:
        out["reaped_stale_jobs"] = await reap_stale_jobs(s)
        probes = await latest_probe_states(s)
        available = {p for (p, _), r in probes.items() if r.state == "AVAILABLE"}
        runner = LiveIngestionRunner(s, build_snapshot_store(settings))
        for spec in SCHEDULES:
            if spec.schedule_class == ScheduleClass.ON_DEMAND:
                out["skipped"].append({"job": spec.job_name, "reason": "ON_DEMAND jobs are never scheduled"})
                continue
            last = (await s.execute(select(func.max(JobRun.started_at)).where(JobRun.job_name == spec.job_name))).scalar_one()
            due = last is None or datetime.now(timezone.utc) - last >= INTERVALS[spec.schedule_class]
            if not due:
                out["skipped"].append({"job": spec.job_name, "reason": f"not due (last run {last.isoformat()})"})
                continue
            if spec.schedule_class == ScheduleClass.LIVE and spec.provider not in available:
                out["skipped"].append({"job": spec.job_name, "reason": f"LIVE job needs an AVAILABLE probe for {spec.provider}"})
                continue
            for params in JOB_PARAMS.get(spec.job_name, [{}]):
                res = await runner.run_job(spec.provider, spec.resource, params, spec.job_name, spec.schedule_class)
                out["executions"].append({"job": spec.job_name, "schedule_class": spec.schedule_class.value,
                                          "provider": spec.provider, "resource": spec.resource, "params": params,
                                          "job_id": res.job_id, "status": res.status, "started_at": res.started_at,
                                          "finished_at": res.finished_at, "latency_ms": res.latency_ms,
                                          "records": res.records, "errors": res.errors[:2],
                                          "snapshot_sha256": res.snapshot_sha256})
    await engine.dispose()
    out["finished_at"] = now()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--database-url", default="postgresql+asyncpg://fios:fios@localhost:5432/fios_p17_live")
    a = ap.parse_args()
    result = asyncio.run(run_once(a.database_url))
    print("wrote", write_evidence("scheduler_run", result))
