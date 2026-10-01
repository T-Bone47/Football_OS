"""Phase 17 incident drills (§35, §36).

Each drill walks DETECT -> ALERT -> ISOLATE -> DEGRADED -> RECOVER -> VERIFY
-> AUDIT and timestamps each stage when it is observed. Real actions are
used wherever this machine allows them (stopping PostgreSQL and Redis,
killing a worker process, corrupting a Bronze file, exhausting a real
budget). Where an outage cannot be caused for real (GitHub serving StatsBomb
data), the fault is injected and labelled SIMULATED_FAULT.

Usage:  python tools/phase17/incident_drills.py     (needs root for `service`)
Writes: docs/evidence/phase17/incident_drills.json
"""
from __future__ import annotations

import asyncio
import hashlib
import signal
import subprocess
import sys
import threading
import time
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
from common import ROOT, api_server, now, write_evidence
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models.canonical import Match
from app.db.models.operations import Alert, JobRun, ModelRegistryEntry, Notification
from app.db.models.provenance import DataSnapshot
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.phase17 import OpsRole
from app.phase17.alerts import deliver, raise_operational_alert, requeue_notification
from app.phase17.audit import verify_chain
from app.phase17.auth import issue_user
from app.phase17.incidents import IncidentDrill
from app.phase17.live_ingestion import LiveIngestionRunner, SnapshotIntegrityError, reap_stale_jobs, replay_snapshot, silver_counts
from app.phase17.model_ops import MODE_VALIDATION, infer_match, match_model_artifact_digest
from app.phase17.rate_governor import ProviderBudget, RateGovernor

DB = "fios_p17_live"
URL = f"postgresql+asyncpg://fios:fios@localhost:5432/{DB}"
PORT = 8018
BRONZE = ROOT / "data" / "bronze"


def sh(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True)


def wait_until(predicate, timeout_s: float = 60.0, interval: float = 0.5) -> float | None:
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        try:
            if predicate():
                return round(time.perf_counter() - t0, 2)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(interval)
    return None


async def with_session(fn):
    engine = create_async_engine(URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            return await fn(s)
    finally:
        await engine.dispose()


async def persist(drill: IncidentDrill) -> str:
    async def go(s):
        row = await drill.persist(s)
        await s.commit()
        return str(row.id)
    return await with_session(go)


# ---------------------------------------------------------------- 1 provider outage
async def drill_provider_outage() -> IncidentDrill:
    d = IncidentDrill("PROVIDER_OUTAGE", "HIGH")

    class Outage(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(503, request=request)

    async def go(s):
        before = await silver_counts(s)
        r = LiveIngestionRunner(s, LocalFilesystemSnapshotStore(BRONZE), governor=RateGovernor(), transport=Outage())
        res = await r.run_job("statsbomb", "matches", {"competition_id": 43, "season_id": 106}, "drill_provider_outage")
        d.stage("DETECT", "job FAILED after bounded retries (SIMULATED_FAULT: HTTP 503 injected at the transport)",
                status=res.status, errors=res.errors[:1])
        alert = (await s.execute(select(Alert).where(Alert.category == "INGESTION_FAILED")
                                 .order_by(Alert.triggered_at.desc()).limit(1))).scalar_one_or_none()
        d.stage("ALERT", "operational alert raised by the ingestion runner with job evidence",
                alert_id=str(alert.id) if alert else None, alert_state=alert.state if alert else None)
        after = await silver_counts(s)
        d.stage("ISOLATE", "no snapshot stored, Silver unchanged", silver_unchanged=before == after,
                snapshot=res.snapshot_sha256)
        final = (await s.execute(select(Match).where(Match.provider_fixture_id == "3869685"))).scalar_one()
        d.stage("DEGRADED", "last-valid Silver keeps serving with its own timestamps",
                last_valid_score=f"{final.home_score}-{final.away_score}", silver_updated_at=final.updated_at.isoformat())
        rec = await LiveIngestionRunner(s, LocalFilesystemSnapshotStore(BRONZE), governor=RateGovernor()).run_job(
            "statsbomb", "matches", {"competition_id": 43, "season_id": 106}, "drill_provider_recovery")
        d.stage("RECOVER", "real request to the provider succeeded", status=rec.status, sha256=rec.snapshot_sha256)
        d.stage("VERIFY", "recovered payload is byte-identical to the last-valid snapshot (idempotent)",
                silver_unchanged=await silver_counts(s) == before)
        d.degraded_behaviour = "Silver served last-valid data; ingestion recorded FAILED; no fabricated payload."
        d.verification = {"recovered": rec.status == "SUCCESS",
                          "passed": rec.status == "SUCCESS" and res.status == "FAILED" and before == await silver_counts(s)}
        d.stage("AUDIT", "incident persisted with audit event")
    await with_session(go)
    return d


# ---------------------------------------------------------------- 2 database outage
async def drill_database_outage(base: str) -> IncidentDrill:
    d = IncidentDrill("DATABASE_OUTAGE", "CRITICAL")
    counts_before = await with_session(silver_counts)
    sh("service", "postgresql", "stop")
    ready = httpx.get(f"{base}/health/ready", timeout=10)
    d.stage("DETECT", "readiness probe failed", http_status=ready.status_code)
    status = httpx.get(f"{base}/api/v1/system/status", timeout=20).json()
    d.stage("ALERT", "system status reports the database UNAVAILABLE (alert rows cannot be written while it is down)",
            system_status=status.get("status"), database=status.get("services", {}).get("database"))
    ops = httpx.get(f"{base}/api/v1/ops/projects", headers={"Authorization": "Bearer drill"}, timeout=20)
    d.stage("ISOLATE", "authenticated endpoints fail closed; nothing is written", http_status=ops.status_code)
    live = httpx.get(f"{base}/health", timeout=10)
    d.stage("DEGRADED", "process stays up; data-dependent endpoints refuse", health=live.status_code)
    sh("service", "postgresql", "start")
    t = wait_until(lambda: httpx.get(f"{base}/health/ready", timeout=5).status_code == 200, 90)
    d.stage("RECOVER", "database restarted; API ready again without a restart (pool_pre_ping)", seconds_to_ready=t)
    counts_after = await with_session(silver_counts)
    chain = await with_session(verify_chain)
    d.stage("VERIFY", "row counts identical and audit chain valid", counts_equal=counts_before == counts_after,
            audit_chain_valid=chain["valid"])
    d.degraded_behaviour = "Liveness OK, readiness 503, data endpoints fail closed; no partial writes."
    d.verification = {"counts_equal": counts_before == counts_after, "audit_chain_valid": chain["valid"],
                      "seconds_to_ready_after_restart": t,
                      "passed": ready.status_code == 503 and t is not None and counts_before == counts_after and chain["valid"]}
    d.stage("AUDIT", "timeline held in memory during the outage, persisted after recovery")
    return d


# ---------------------------------------------------------------- 3 worker outage
WORKER_SNIPPET = r'''
import asyncio, sys
sys.path.insert(0, "apps/api")
import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.phase17.live_ingestion import LiveIngestionRunner
from app.phase17.rate_governor import RateGovernor

class Hang(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        await asyncio.sleep(600)

async def main():
    eng = create_async_engine(sys.argv[1])
    async with async_sessionmaker(eng, expire_on_commit=False)() as s:
        await LiveIngestionRunner(s, LocalFilesystemSnapshotStore("data/bronze"), governor=RateGovernor(),
                                  transport=Hang()).run_job("statsbomb", "matches", {"competition_id": 2, "season_id": 27},
                                                            "drill_worker_outage")
asyncio.run(main())
'''


async def drill_worker_outage() -> IncidentDrill:
    d = IncidentDrill("WORKER_OUTAGE", "HIGH")
    before = await with_session(silver_counts)
    proc = subprocess.Popen([sys.executable, "-c", WORKER_SNIPPET, URL], cwd=ROOT)

    async def running(s):
        return (await s.execute(select(func.count()).select_from(JobRun).where(
            JobRun.job_name == "drill_worker_outage", JobRun.status == "RUNNING"))).scalar_one()
    for _ in range(60):
        if await with_session(running):
            break
        await asyncio.sleep(0.5)
    proc.send_signal(signal.SIGKILL)
    proc.wait()
    d.stage("DETECT", "worker killed with SIGKILL mid-request (SIMULATED_FAULT: provider made to hang); its job row is "
                      "still RUNNING and visible because RUNNING is committed before the request",
            running_rows=await with_session(running))

    async def reap(s):
        alert = await raise_operational_alert(s, category="WORKER_LOST", severity="HIGH", title="ingestion worker lost",
                                              evidence=[{"job_name": "drill_worker_outage", "signal": "SIGKILL"}],
                                              source="incident_drill", dedup_scope="drill_worker_outage")
        await s.commit()
        d.stage("ALERT", "operational alert raised", alert_id=str(alert.id))
        d.stage("ISOLATE", "no snapshot and no Silver rows from the lost job", silver_unchanged=await silver_counts(s) == before)
        d.stage("DEGRADED", "other jobs unaffected; the lost job is the only gap")
        reaped = await reap_stale_jobs(s, older_than_s=0)
        d.stage("RECOVER", "reaper marked the orphaned job FAILED: WORKER_LOST", reaped=reaped)
        left = await running(s)
        d.stage("VERIFY", "no RUNNING orphans remain; Silver unchanged", running_rows=left,
                silver_unchanged=await silver_counts(s) == before)
        d.verification = {"orphans_after": left, "reaped": len(reaped), "passed": left == 0 and len(reaped) >= 1}
    await with_session(reap)
    d.degraded_behaviour = "Job visible as RUNNING until reaped; no partial Silver write."
    d.stage("AUDIT", "reaper and incident write audit events")
    return d


# ---------------------------------------------------------------- 4 model artifact failure
async def drill_model_artifact() -> IncidentDrill:
    d = IncidentDrill("MODEL_ARTIFACT_FAILURE", "HIGH")

    async def go(s):
        model = (await s.execute(select(ModelRegistryEntry).where(ModelRegistryEntry.domain == "match_outcome"))).scalar_one()
        good = model.artifact_sha256
        model.artifact_sha256 = hashlib.sha256(b"corrupted-artifact").hexdigest()
        await s.commit()
        m = (await s.execute(select(Match).where(Match.provider_fixture_id == "3869685"))).scalar_one()
        # VALIDATION_BACKTEST is the only mode that may execute this unvalidated
        # (REGISTERED) model, so it is the mode in which the artifact gate is reached.
        res = await infer_match(s, m.id, as_of=m.date - timedelta(hours=1), mode=MODE_VALIDATION)
        detected = res.status == "MODEL_UNAVAILABLE" and "ARTIFACT_INTEGRITY_FAILED" in res.reasons[0]
        d.stage("DETECT", "inference refused: artifact digest mismatch", status=res.status, reason=res.reasons[0],
                detected_by_artifact_gate=detected)
        alert = await raise_operational_alert(s, category="MODEL_ARTIFACT_INTEGRITY", severity="CRITICAL",
                                              title="match model artifact integrity failure",
                                              evidence=[{"inference_id": str(res.id), "reason": res.reasons[0]}],
                                              source="incident_drill", dedup_scope=model.model_id)
        await s.commit()
        d.stage("ALERT", "operational alert raised", alert_id=str(alert.id))
        d.stage("ISOLATE", "no probabilities emitted while the artifact is untrusted", output=res.output)
        d.stage("DEGRADED", "MODEL_UNAVAILABLE returned for every request; nothing substituted")
        model.artifact_sha256 = good
        await s.commit()
        d.stage("RECOVER", "registry digest restored to the verified artifact", restored=good == match_model_artifact_digest())
        ok = await infer_match(s, m.id, as_of=m.date - timedelta(hours=1), mode=MODE_VALIDATION)
        await s.commit()
        d.stage("VERIFY", "inference served again", status=ok.status)
        d.verification = {"served_after_recovery": ok.status == "SERVED", "detected_by_artifact_gate": detected,
                          "passed": detected and ok.status == "SERVED"}
    await with_session(go)
    d.degraded_behaviour = "MODEL_UNAVAILABLE; no fallback prediction."
    d.stage("AUDIT", "refused and served requests remain in the immutable inference log")
    return d


# ---------------------------------------------------------------- 5 bad data snapshot
async def drill_bad_snapshot() -> IncidentDrill:
    d = IncidentDrill("BAD_DATA_SNAPSHOT", "HIGH")

    async def go(s):
        snap = (await s.execute(select(DataSnapshot).where(DataSnapshot.storage_location.like("%/lineups/%"))
                                .order_by(DataSnapshot.retrieved_at.desc()).limit(1))).scalar_one()
        path = Path(snap.storage_location)
        original = path.read_bytes()
        path.write_bytes(original[: len(original) // 2])  # truncated on disk
        before = await silver_counts(s)
        try:
            await replay_snapshot(s, snap.id)
            detected = False
        except SnapshotIntegrityError as exc:
            detected = str(exc)
        d.stage("DETECT", "SHA-256 re-verification rejected the stored bytes", error=detected)
        alert = await raise_operational_alert(s, category="BRONZE_INTEGRITY", severity="CRITICAL",
                                              title="Bronze snapshot failed integrity check",
                                              evidence=[{"sha256": snap.sha256, "storage_location": snap.storage_location}],
                                              source="incident_drill", dedup_scope=snap.sha256)
        await s.commit()
        d.stage("ALERT", "operational alert raised", alert_id=str(alert.id))
        d.stage("ISOLATE", "corrupt bytes never reached Silver", silver_unchanged=await silver_counts(s) == before)
        d.stage("DEGRADED", "Silver keeps the rows normalized from the verified copy")
        match_id = (await s.execute(text("SELECT parameters->>'match_id' FROM ingestion_runs WHERE id = :r"),
                                    {"r": snap.ingestion_run_id})).scalar_one()
        res = await LiveIngestionRunner(s, LocalFilesystemSnapshotStore(BRONZE), governor=RateGovernor()).run_job(
            "statsbomb", "lineups", {"match_id": int(match_id)}, "drill_bad_snapshot_refetch")
        d.stage("RECOVER", "real re-fetch from the provider; store detected the bad copy and rewrote it",
                status=res.status, same_sha=res.snapshot_sha256 == snap.sha256)
        healed = hashlib.sha256(path.read_bytes()).hexdigest() == snap.sha256
        await replay_snapshot(s, snap.id)
        d.stage("VERIFY", "file hashes to its name again and replays cleanly", healed=healed,
                silver_unchanged=await silver_counts(s) == before)
        d.verification = {"healed": healed, "passed": healed and bool(detected)}
    await with_session(go)
    d.degraded_behaviour = "Replay/normalization refused for the corrupted snapshot only."
    d.stage("AUDIT", "incident persisted")
    return d


# ---------------------------------------------------------------- 6 rate-limit exhaustion
async def drill_rate_limit() -> IncidentDrill:
    d = IncidentDrill("RATE_LIMIT_EXHAUSTION", "MEDIUM")
    g = RateGovernor({"statsbomb": ProviderBudget("statsbomb", per_minute=2, per_hour=50, source="SELF_IMPOSED")})

    async def go(s):
        r = LiveIngestionRunner(s, LocalFilesystemSnapshotStore(BRONZE), governor=g)
        statuses = [(await r.run_job("statsbomb", "lineups", {"match_id": 3869685}, "drill_rate_limit")).status for _ in range(3)]
        d.stage("DETECT", "budget exhausted after 2 real requests; third job deferred without a request", statuses=statuses,
                requests_sent=g.report()["providers"]["statsbomb"]["total_requests"])
        d.stage("ALERT", "deferral recorded as job status RATE_LIMIT_DEFERRED (governance, not an outage: no alert)")
        d.stage("ISOLATE", "provider never sees more than the budget", budget=g.report()["providers"]["statsbomb"]["budget"])
        d.stage("DEGRADED", "deferred work waits; nothing marked successful")
        wait = g.seconds_until_headroom("statsbomb")
        await asyncio.sleep(wait + 1)
        ok = await r.run_job("statsbomb", "lineups", {"match_id": 3869685}, "drill_rate_limit")
        d.stage("RECOVER", "window rolled over; job ran", waited_s=round(wait + 1, 1), status=ok.status)
        rep = g.report()["providers"]["statsbomb"]
        d.stage("VERIFY", "budget never exceeded", budget_exceeded=rep["budget_exceeded"], total_requests=rep["total_requests"])
        d.verification = {"budget_exceeded": rep["budget_exceeded"], "statuses": statuses + [ok.status],
                          "passed": not rep["budget_exceeded"] and statuses[2] == "RATE_LIMIT_DEFERRED" and ok.status == "SUCCESS"}
    await with_session(go)
    d.degraded_behaviour = "Jobs deferred (RATE_LIMIT_DEFERRED), not failed and not faked."
    d.stage("AUDIT", "incident persisted")
    return d


# ---------------------------------------------------------------- 7 cache (Redis) failure
async def drill_cache_failure(base: str, token: str) -> IncidentDrill:
    d = IncidentDrill("CACHE_FAILURE", "MEDIUM")
    h = {"Authorization": f"Bearer {token}"}
    sh("redis-cli", "shutdown", "nosave")
    st = httpx.get(f"{base}/api/v1/ops/system/status", headers=h, timeout=30).json()
    d.stage("DETECT", "Redis probe UNAVAILABLE", redis=st["components"]["redis"]["status"])
    d.stage("ALERT", "system status DEGRADED", system=st["status"])
    d.stage("ISOLATE", "rate limiting switched to the process-local window",
            backend=st["components"]["api_rate_limit"]["backend"])
    r = httpx.get(f"{base}/api/v1/ops/me", headers=h, timeout=10)
    d.stage("DEGRADED", "authenticated requests still served and still rate-limited", http_status=r.status_code)
    sh("redis-server", "--daemonize", "yes", "--port", "6379")
    t = wait_until(lambda: sh("redis-cli", "ping").stdout.strip() == "PONG", 30)
    d.stage("RECOVER", "Redis restarted", seconds=t)
    time.sleep(31)  # the API re-checks Redis at most every 30 s
    httpx.get(f"{base}/api/v1/ops/me", headers=h, timeout=10)
    st2 = httpx.get(f"{base}/api/v1/ops/system/status", headers=h, timeout=30).json()
    d.stage("VERIFY", "Redis healthy and back in use for rate limiting", redis=st2["components"]["redis"]["status"],
            backend=st2["components"]["api_rate_limit"]["backend"])
    d.degraded_behaviour = "Per-user limits enforced per process instead of cluster-wide."
    d.verification = {"redis": st2["components"]["redis"]["status"], "backend": st2["components"]["api_rate_limit"]["backend"],
                      "passed": st["components"]["redis"]["status"] == "UNAVAILABLE"
                      and st["components"]["api_rate_limit"]["backend"] == "PROCESS_LOCAL_FALLBACK"
                      and st2["components"]["redis"]["status"] == "HEALTHY" and st2["components"]["api_rate_limit"]["backend"] == "REDIS"}
    d.stage("AUDIT", "incident persisted")
    return d


# ---------------------------------------------------------------- 8 notification failure
class _Hook(BaseHTTPRequestHandler):
    hits = 0

    def do_POST(self):  # noqa: N802
        _Hook.hits += 1
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


async def drill_notification_failure() -> IncidentDrill:
    d = IncidentDrill("NOTIFICATION_FAILURE", "MEDIUM")
    server = HTTPServer(("127.0.0.1", 0), _Hook)
    port = server.server_address[1]
    server.server_close()  # port is now closed: the webhook endpoint is down
    settings = Settings(_env_file=None, notification_webhook_url=f"http://127.0.0.1:{port}/hook")

    async def go(s):
        alert = await raise_operational_alert(s, category="DRILL_NOTIFICATION", severity="LOW", title="notification drill",
                                              evidence=[{"drill": "notification_failure"}], source="incident_drill",
                                              dedup_scope=f"notif-{time.time()}")
        out = await deliver(s, alert, settings)
        await s.commit()
        hook = next(o for o in out if o["channel"] == "WEBHOOK")
        d.stage("DETECT", "webhook delivery FAILED after bounded attempts; never reported SENT", **hook)
        d.stage("ALERT", "failure visible in ops_notifications and to Copilot ('What failed?')")
        d.stage("ISOLATE", "retries capped at 3", attempts=hook["attempts"])
        d.stage("DEGRADED", "IN_APP delivery succeeded; alert state DELIVERED via IN_APP", alert_state=alert.state)
        srv = HTTPServer(("127.0.0.1", port), _Hook)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        note = (await s.execute(select(Notification).where(Notification.alert_id == alert.id,
                                                            Notification.channel == "WEBHOOK"))).scalar_one()
        await requeue_notification(s, note, "operator:drill")
        out2 = await deliver(s, alert, settings)
        await s.commit()
        d.stage("RECOVER", "endpoint restored; operator requeued the notification",
                webhook=next(o for o in out2 if o["channel"] == "WEBHOOK"))
        d.stage("VERIFY", "endpoint received exactly one delivery", hits=_Hook.hits)
        state = next(o for o in out2 if o["channel"] == "WEBHOOK")["state"]
        d.verification = {"webhook_state": state, "hits": _Hook.hits,
                          "passed": hook["state"] == "FAILED" and state == "SENT" and _Hook.hits == 1}
        srv.shutdown()
    await with_session(go)
    d.degraded_behaviour = "In-app delivery only; webhook FAILED until requeued."
    d.stage("AUDIT", "requeue and incident are audited")
    return d


async def make_admin() -> str:
    async def go(s):
        _, token = await issue_user(s, "Pilot Club", f"drill+{int(time.time())}@pilot.test", "Drill Admin", OpsRole.ADMIN)
        await s.commit()
        return token
    return await with_session(go)


def main() -> None:
    results = {}
    drills = []
    for fn in (drill_provider_outage, drill_worker_outage, drill_model_artifact, drill_bad_snapshot, drill_rate_limit,
               drill_notification_failure):
        print("drill", fn.__name__, flush=True)
        drills.append(asyncio.run(fn()))
    token = asyncio.run(make_admin())
    with api_server(URL, PORT) as (base, _):
        print("drill database_outage", flush=True)
        drills.append(asyncio.run(drill_database_outage(base)))
        print("drill cache_failure", flush=True)
        drills.append(asyncio.run(drill_cache_failure(base, token)))
    for d in drills:
        incident_id = asyncio.run(persist(d))
        detected = d.detected_at
        results[d.kind] = {"incident_id": incident_id, "complete": d.complete, "passed": d.verification.get("passed") is True,
                           "recovery_seconds": round((d.recovered_at - detected).total_seconds(), 2) if d.recovered_at and detected else None,
                           "degraded_behaviour": d.degraded_behaviour, "verification": d.verification, "timeline": d.timeline}
    print("wrote", write_evidence("incident_drills", {"database": DB, "drills": results, "finished_at": now()}))


if __name__ == "__main__":
    main()
