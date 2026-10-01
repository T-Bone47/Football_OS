"""Phase 17 performance and load measurement (§32, §33).

Everything here is SIMULATED_LOAD in the Claude Code sandbox: one uvicorn
worker, one local PostgreSQL, synthetic concurrent clients. It is not
REAL_PRODUCTION_TRAFFIC and must not be reported as such.

Measures, against the real API and the live-ingested database:
- per-endpoint latency, cold (first request after start) and warm (p50/p95/p99)
- 10 / 25 / 50 / 100 concurrent users: throughput, latency, error rate,
  PostgreSQL connections and commits, API process CPU/RSS
- ingestion latency with a normal provider (StatsBomb) and a degraded one
  (API-Football, blocked at egress in this environment)

Usage:  python tools/phase17/load_test.py
Writes: docs/evidence/phase17/load_test.json
"""
from __future__ import annotations

import asyncio
import math
import statistics
import time

import httpx
import psutil
from common import api_server, now, write_evidence
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.canonical import Match, MatchLineup
from app.phase17 import OpsRole
from app.phase17.auth import issue_user

URL = "postgresql+asyncpg://fios:fios@localhost:5432/fios_p17_live"
PORT = 8019
LEVELS = (10, 25, 50, 100)
REQUESTS_PER_USER = 8


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return round(s[f] + (s[c] - s[f]) * (k - f), 2)


async def setup(n_users: int) -> dict:
    engine = create_async_engine(URL)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        tokens = []
        stamp = int(time.time())
        for i in range(n_users):
            _, t = await issue_user(s, "Load Org", f"load{i}+{stamp}@load.test", f"Load {i}", OpsRole.ADMIN)
            tokens.append(t)
        await s.commit()
        match = (await s.execute(select(Match).order_by(desc(Match.date)).limit(1))).scalar_one()
        player = (await s.execute(select(MatchLineup.player_id).where(MatchLineup.match_id == match.id).limit(1))).scalar_one()
    await engine.dispose()
    return {"tokens": tokens, "match": str(match.id), "player": str(player)}


def endpoints(ctx: dict) -> dict[str, tuple[str, str, dict]]:
    m, p = ctx["match"], ctx["player"]
    return {
        "player_search": ("GET", "/api/v1/players", {"params": {"position": "M", "limit": 50}}),
        "player_intelligence": ("GET", f"/api/v1/players/{p}/intelligence", {}),
        "similarity": ("GET", f"/api/v1/players/{p}/similar", {}),
        "tactical_fit": ("GET", f"/api/v1/players/{p}/tactical-fit", {}),
        "market": ("GET", "/api/v1/market/readiness", {}),
        "recruitment": ("GET", "/api/v1/decisions/recruitment", {"params": {"target_position": "CM", "limit": 5}}),
        "scenario": ("GET", "/api/v1/decision-lab/squad/arsenal_fc", {}),
        "match_prediction": ("POST", f"/api/v1/ops/inference/match/{m}", {"params": {"mode": "HISTORICAL_REPLAY",
                                                                                      "as_of": "2016-05-17T19:00:00+00:00"}}),
        "copilot": ("POST", "/api/v1/ops/copilot", {"json": {"query": "What data was ingested recently?"}}),
        "operations_dashboard": ("GET", "/api/v1/ops/competitions/readiness", {}),
        "system_status": ("GET", "/api/v1/ops/system/status", {}),
    }


async def timed(client: httpx.AsyncClient, method: str, path: str, kw: dict, token: str) -> tuple[float, int | str]:
    t0 = time.perf_counter()
    try:
        r = await client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kw)
        status: int | str = r.status_code
    except httpx.HTTPError as exc:
        status = type(exc).__name__
    return (time.perf_counter() - t0) * 1000, status


def summarize(samples: list[tuple[float, int | str]]) -> dict:
    lat = [s[0] for s in samples]
    codes: dict[str, int] = {}
    for _, c in samples:
        codes[str(c)] = codes.get(str(c), 0) + 1
    server_errors = sum(n for c, n in codes.items() if not c.isdigit() or int(c) >= 500)
    return {"n": len(samples), "p50_ms": pct(lat, 0.5), "p95_ms": pct(lat, 0.95), "p99_ms": pct(lat, 0.99),
            "mean_ms": round(statistics.mean(lat), 2) if lat else None, "status_codes": codes,
            "server_error_rate": round(server_errors / len(samples), 4) if samples else None}


async def db_stats() -> dict:
    engine = create_async_engine(URL)
    async with engine.connect() as c:
        row = (await c.execute(text("SELECT xact_commit, xact_rollback, blks_hit, blks_read FROM pg_stat_database "
                                    "WHERE datname = current_database()"))).one()
        conns = (await c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"))).scalar_one()
    await engine.dispose()
    return {"xact_commit": row[0], "xact_rollback": row[1], "blks_hit": row[2], "blks_read": row[3], "connections": conns}


async def run_level(base: str, ctx: dict, users: int, proc: psutil.Process) -> dict:
    eps = list(endpoints(ctx).items())
    samples: list[tuple[float, int | str]] = []
    max_conns = 0
    cpu_samples: list[float] = []
    stop = asyncio.Event()

    async def sampler():
        nonlocal max_conns
        while not stop.is_set():
            try:
                max_conns = max(max_conns, (await db_stats())["connections"])
                cpu_samples.append(proc.cpu_percent(interval=None))
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.5)

    before = await db_stats()
    proc.cpu_percent(interval=None)
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(base_url=base, timeout=120, limits=limits) as client:
        async def user(i: int):
            for k in range(REQUESTS_PER_USER):
                name, (method, path, kw) = eps[(i + k) % len(eps)]
                samples.append(await timed(client, method, path, kw, ctx["tokens"][i]))

        task = asyncio.create_task(sampler())
        t0 = time.perf_counter()
        await asyncio.gather(*(user(i) for i in range(users)))
        wall = time.perf_counter() - t0
        stop.set()
        await task
    after = await db_stats()
    res = summarize(samples)
    res.update({"users": users, "wall_seconds": round(wall, 2), "throughput_rps": round(len(samples) / wall, 2),
                "db": {"max_connections_observed": max_conns, "commits": after["xact_commit"] - before["xact_commit"],
                       "rollbacks": after["xact_rollback"] - before["xact_rollback"],
                       "cache_hit_ratio": round((after["blks_hit"] - before["blks_hit"]) /
                                                max(1, (after["blks_hit"] - before["blks_hit"]) + (after["blks_read"] - before["blks_read"])), 4)},
                "api_process": {"cpu_percent_max": max(cpu_samples) if cpu_samples else None,
                                "cpu_percent_mean": round(statistics.mean(cpu_samples), 1) if cpu_samples else None,
                                "rss_mb": round(proc.memory_info().rss / 1e6, 1)},
                "queue_depth": "NOT_APPLICABLE: no job queue exists; ingestion runs synchronously per request"})
    return res


async def main_async(base: str, ctx: dict, proc: psutil.Process) -> dict:
    out: dict = {"label": "SIMULATED_LOAD", "not": "REAL_PRODUCTION_TRAFFIC",
                 "setup": "1 uvicorn worker, local PostgreSQL 16, sandbox VM; clients on the same host"}
    eps = endpoints(ctx)
    per_endpoint = {}
    async with httpx.AsyncClient(base_url=base, timeout=120) as client:
        for i, (name, (method, path, kw)) in enumerate(eps.items()):
            token = ctx["tokens"][i]
            cold = await timed(client, method, path, kw, token)
            warm = [await timed(client, method, path, kw, token) for _ in range(20)]
            per_endpoint[name] = {"cold_ms": round(cold[0], 2), "cold_status": cold[1], "warm": summarize(warm)}
    out["per_endpoint"] = per_endpoint
    out["concurrency"] = [await run_level(base, ctx, u, proc) for u in LEVELS]
    admin = ctx["tokens"][-1]
    async with httpx.AsyncClient(base_url=base, timeout=300, headers={"Authorization": f"Bearer {admin}"}) as client:
        normal, degraded = [], []
        for _ in range(3):
            t0 = time.perf_counter()
            r = await client.post("/api/v1/ops/ingestion/jobs", json={"provider": "statsbomb", "resource": "lineups",
                                                                      "params": {"match_id": 3869685}})
            normal.append(((time.perf_counter() - t0) * 1000, r.json().get("status")))
            t0 = time.perf_counter()
            r = await client.post("/api/v1/ops/ingestion/jobs", json={"provider": "api-football", "resource": "fixtures",
                                                                      "params": {"league": 39, "season": 2025}})
            degraded.append(((time.perf_counter() - t0) * 1000, r.json().get("status")))
            sys_t0 = time.perf_counter()
            await client.get("/api/v1/ops/system/status")
        out["provider_conditions"] = {
            "normal_provider_statsbomb_lineups": {"latency_ms": [round(x, 1) for x, _ in normal], "statuses": [s for _, s in normal]},
            "degraded_provider_api_football_blocked": {"latency_ms": [round(x, 1) for x, _ in degraded],
                                                       "statuses": [s for _, s in degraded],
                                                       "note": "egress-blocked host; adapter retries 3x then the job is FAILED"},
            "system_status_ms_under_degraded_provider": round((time.perf_counter() - sys_t0) * 1000, 1),
        }
        out["server_side_telemetry"] = (await client.get("/api/v1/ops/telemetry/latency")).json()
    return out


def main() -> None:
    ctx = asyncio.run(setup(max(LEVELS) + 1))
    with api_server(URL, PORT) as (base, proc):
        result = asyncio.run(main_async(base, ctx, psutil.Process(proc.pid)))
    result["finished_at"] = now()
    print("wrote", write_evidence("load_test", result))


if __name__ == "__main__":
    main()
