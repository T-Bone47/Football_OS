"""Shared helpers for the Phase 17 evidence harness.

Every harness script writes JSON evidence to docs/evidence/phase17/. The
JSON records what actually happened, including failures; a script never
rewrites a failed observation as success.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
EVIDENCE = ROOT / "docs" / "evidence" / "phase17"
EVIDENCE.mkdir(parents=True, exist_ok=True)

PG_ADMIN = os.environ.get("PG_ADMIN_URL", "postgresql://fios:fios@localhost:5432/postgres")
PG_BASE = "postgresql+asyncpg://fios:fios@localhost:5432"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_evidence(name: str, payload: dict[str, Any]) -> Path:
    path = EVIDENCE / f"{name}.json"
    payload = {"generated_at": now(), "environment": "claude-code-cloud-sandbox (development)", **payload}
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def recreate_database(name: str) -> str:
    """Drops and recreates `name`, then migrates it with Alembic to head."""
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"DROP DATABASE IF EXISTS {name} WITH (FORCE);"], check=True)
    subprocess.run(["psql", PG_ADMIN, "-q", "-c", f"CREATE DATABASE {name} OWNER fios;"], check=True)
    url = f"{PG_BASE}/{name}"
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(["alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True)
    return url


class Timer:
    def __init__(self) -> None:
        self.stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = round(time.perf_counter() - t0, 2)
            print(f"[{now()}] stage {name}: {self.stages[name]}s", flush=True)


@contextmanager
def api_server(database_url: str, port: int, extra_env: dict[str, str] | None = None, workers: int = 1):
    """Runs the real FastAPI app under uvicorn against `database_url`."""
    import httpx

    env = {**os.environ, "DATABASE_URL": database_url, "ENVIRONMENT": "development",
           "SNAPSHOT_STORAGE_PATH": str(ROOT / "data" / "bronze"), **(extra_env or {})}
    log_path = Path(os.environ.get("PHASE17_SERVER_LOG", f"/tmp/fios-uvicorn-{port}.log"))
    log = open(log_path, "ab")  # a file, not a pipe: an unread pipe stalls the server under errors
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "apps" / "api"),
         "--port", str(port), "--workers", str(workers), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=log, stderr=log)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise RuntimeError(f"uvicorn did not start; see {log_path}")
        yield base, proc
    finally:
        log.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
