"""Phase 17 rollback drill (§48).

1. Application rollback: the previous commit's API (git worktree) is started
   against the migrated live database and exercised. Migration 0014 is
   additive, so N-1 code must still run on the N schema.
2. Migration rollback: on a data-bearing copy of the live database,
   downgrade 0014 -> 0013 and upgrade again. Canonical data must survive;
   Phase 17 operational evidence does not (documented: never roll back
   0014 in production; forward-fix instead).
3. Model rollback: SHADOW -> REGISTERED through the audited demote endpoint.
4. Configuration rollback: NOT_TESTED (no deployed configuration store).

Usage:  python tools/phase17/rollback_drill.py [--previous-commit eb2ad0d]
Writes: docs/evidence/phase17/rollback_drill.json
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time

import httpx
from common import PG_ADMIN, ROOT, api_server, now, write_evidence
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.phase17 import OpsRole
from app.phase17.auth import issue_user

LIVE = "fios_p17_live"
COPY = "fios_p17_rollback_copy"
BASE = "postgresql+asyncpg://fios:fios@localhost:5432"


def app_rollback(commit: str) -> dict:
    tree = tempfile.mkdtemp(prefix="fios-prev-")
    shutil.rmtree(tree)
    subprocess.run(["git", "worktree", "add", "--detach", tree, commit], cwd=ROOT, check=True, capture_output=True)
    port = 8021
    log = open(f"/tmp/fios-uvicorn-{port}.log", "ab")
    env = {**os.environ, "DATABASE_URL": f"{BASE}/{LIVE}", "ENVIRONMENT": "development"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", f"{tree}/apps/api",
                             "--port", str(port), "--log-level", "warning"], cwd=tree, env=env, stdout=log, stderr=log)
    out: dict = {"previous_commit": commit}
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        checks = {"/health/ready": None, "/api/v1/players?limit=5": None, "/api/v1/matches?limit=5": None,
                  "/api/v1/competitions": None}
        for path in checks:
            r = httpx.get(base + path, timeout=30)
            checks[path] = {"status": r.status_code, "rows": len(r.json()) if r.status_code == 200 and isinstance(r.json(), list) else None}
        out["checks"] = checks
        out["passed"] = all(c["status"] == 200 for c in checks.values())
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()
        subprocess.run(["git", "worktree", "remove", "--force", tree], cwd=ROOT, capture_output=True)
    return out


async def counts(url: str, tables: list[str]) -> dict:
    engine = create_async_engine(url)
    async with engine.connect() as c:
        existing = set((await c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all())
        out = {t: (await c.execute(text(f'SELECT count(*) FROM "{t}"'))).scalar_one() if t in existing else None for t in tables}
        out["_alembic"] = (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    await engine.dispose()
    return out


def migration_rollback() -> dict:
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"DROP DATABASE IF EXISTS {COPY} WITH (FORCE);"], check=True)
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"CREATE DATABASE {COPY} TEMPLATE {LIVE} OWNER fios;"], check=True)
    url = f"{BASE}/{COPY}"
    tables = ["matches", "match_lineups", "match_events", "players", "clubs", "data_snapshots", "ingestion_runs",
              "ops_job_runs", "ops_inference_log", "ops_audit_events"]
    before = asyncio.run(counts(url, tables))
    env = {**os.environ, "DATABASE_URL": url}
    t0 = time.perf_counter()
    down = subprocess.run(["alembic", "downgrade", "0013"], cwd=ROOT, env=env, capture_output=True, text=True)
    mid = asyncio.run(counts(url, tables))
    up = subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, env=env, capture_output=True, text=True)
    after = asyncio.run(counts(url, tables))
    canonical = ["matches", "match_lineups", "match_events", "players", "clubs", "data_snapshots", "ingestion_runs"]
    result = {"before": before, "after_downgrade": mid, "after_reupgrade": after,
              "downgrade_exit": down.returncode, "upgrade_exit": up.returncode,
              "seconds": round(time.perf_counter() - t0, 2),
              "canonical_data_preserved": all(before[t] == mid[t] == after[t] for t in canonical),
              "operational_evidence_lost_on_downgrade": {t: before[t] for t in ("ops_job_runs", "ops_inference_log", "ops_audit_events")},
              "policy": "Do not downgrade 0014 in production: it drops immutable operational evidence. Roll application "
                        "code back (N-1 runs on the N schema) and forward-fix migrations."}
    result["passed"] = down.returncode == 0 and up.returncode == 0 and result["canonical_data_preserved"] and \
        mid["ops_audit_events"] is None and after["_alembic"] == "0014"
    return result


def model_rollback() -> dict:
    url = f"{BASE}/{COPY}"

    async def prep():
        engine = create_async_engine(url)
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            await s.execute(text("UPDATE ops_model_registry SET deployment_state='SHADOW' WHERE domain='match_outcome'"))
            _, token = await issue_user(s, "Rollback Org", f"rb+{int(time.time())}@rb.test", "RB", OpsRole.ADMIN)
            await s.commit()
        await engine.dispose()
        return token

    # the copy lost its ops rows on downgrade; re-register the model there first
    async def register():
        from app.phase17.model_ops import ensure_match_model_registered
        engine = create_async_engine(url)
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            await ensure_match_model_registered(s)
            await s.commit()
        await engine.dispose()

    asyncio.run(register())
    token = asyncio.run(prep())
    with api_server(url, 8022) as (base, _):
        h = {"Authorization": f"Bearer {token}"}
        first = httpx.post(f"{base}/api/v1/ops/models/calibrated_multinomial_logit_v1/demote", headers=h).json()
        second = httpx.post(f"{base}/api/v1/ops/models/calibrated_multinomial_logit_v1/demote", headers=h)
        audit = httpx.get(f"{base}/api/v1/ops/audit", headers=h).json()
    return {"demote": first, "second_demote_http": second.status_code,
            "audit_event_recorded": any(e["event_type"] == "MODEL_DEMOTED" for e in audit),
            "passed": first.get("to") == "REGISTERED" and second.status_code == 409}


def main(commit: str) -> None:
    ev = {"started_at": now()}
    ev["application_rollback"] = app_rollback(commit)
    ev["migration_rollback"] = migration_rollback()
    ev["model_rollback"] = model_rollback()
    ev["configuration_rollback"] = {"status": "NOT_TESTED",
                                    "reason": "no deployed configuration store exists; templates are versioned in git (deploy/env)"}
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"DROP DATABASE IF EXISTS {COPY} WITH (FORCE);"])
    ev["finished_at"] = now()
    print("wrote", write_evidence("rollback_drill", ev))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous-commit", default="eb2ad0d")
    main(ap.parse_args().previous_commit)
