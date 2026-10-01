"""Captures the operational read-outs that are not produced by another
harness script (usage/cost, retention, notification channels, schedules,
system status, capability summary) through the real API.

Usage:  python tools/phase17/ops_snapshot.py
Writes: docs/evidence/phase17/ops_snapshot.json
"""
from __future__ import annotations

import asyncio
import time

import httpx
from common import api_server, now, write_evidence
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.phase17 import OpsRole
from app.phase17.auth import issue_user

URL = "postgresql+asyncpg://fios:fios@localhost:5432/fios_p17_live"


async def token() -> str:
    engine = create_async_engine(URL)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        _, t = await issue_user(s, "Pilot Club", f"snap+{int(time.time())}@pilot.test", "Snapshot", OpsRole.ADMIN)
        await s.commit()
    await engine.dispose()
    return t


def main() -> None:
    t = asyncio.run(token())
    out = {}
    with api_server(URL, 8023) as (base, _):
        c = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {t}"}, timeout=120)
        for name, path in (("usage", "/usage"), ("retention", "/retention"), ("notification_channels", "/notifications/channels"),
                           ("schedules", "/schedules"), ("system_status", "/system/status"), ("audit_verify", "/audit/verify"),
                           ("incidents", "/incidents"), ("model_health", "/models/health")):
            r = c.get(f"/api/v1/ops{path}")
            out[name] = r.json() if r.status_code == 200 else {"http_status": r.status_code}
    out["finished_at"] = now()
    print("wrote", write_evidence("ops_snapshot", out))


if __name__ == "__main__":
    main()
