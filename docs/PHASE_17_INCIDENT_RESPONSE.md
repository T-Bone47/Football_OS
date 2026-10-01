# Phase 17 — Incident Response and Degraded Mode

Evidence: `docs/evidence/phase17/incident_drills.json` (`tools/phase17/incident_drills.py`). Incident records: `ops_incidents` / `GET /api/v1/ops/incidents`.

Every drill walks **DETECT → ALERT → ISOLATE → DEGRADED → RECOVER → VERIFY → AUDIT**, timestamping each stage when it is observed. A drill is `CLOSED` only if every stage happened **and** its verification passed; otherwise it is `INCOMPLETE`. Real actions were used wherever this machine allows them. Where an outage cannot be caused for real (GitHub serving StatsBomb data, a provider hanging), the fault was injected at the HTTP transport and is labelled `SIMULATED_FAULT` in the timeline.

## 1. Drill results (final run)

| # | Drill | How the fault was produced | Detection | Degraded behaviour | Recovery | Verified | Detect→recover |
|---|---|---|---|---|---|---|---|
| 1 | Provider outage | SIMULATED_FAULT: HTTP 503 from the transport | job FAILED after 3 bounded attempts | last-valid Silver served with its timestamps; no snapshot, no Silver write | **real** request succeeded | payload byte-identical; Silver unchanged | 0.9 s |
| 2 | Database outage | **real**: `service postgresql stop` | `/health/ready` 503; system status UNAVAILABLE | liveness 200; data endpoints fail closed (500); nothing written | **real** restart; API ready again without an app restart (`pool_pre_ping`) | row counts identical; audit chain valid | 2.5 s |
| 3 | Worker outage | **real** `SIGKILL` of a worker mid-request (SIMULATED_FAULT: provider made to hang) | job row visible as RUNNING (committed before the request) | only the lost job missing; no partial Silver | reaper marked it `FAILED: WORKER_LOST` | 0 RUNNING orphans; Silver unchanged | 0.1 s |
| 4 | Model artifact failure | **real** registry digest corruption | `MODEL_UNAVAILABLE: ARTIFACT_INTEGRITY_FAILED` | no probabilities emitted; nothing substituted | digest restored | inference served again | <0.1 s |
| 5 | Bad data snapshot | **real**: Bronze file truncated on disk | SHA-256 re-verification rejected the bytes | corrupt bytes never reached Silver | **real** re-fetch; store detected and rewrote the bad copy | file hashes to its name; replay clean | 0.8 s |
| 6 | Rate-limit exhaustion | **real** budget of 2/min against real requests | 3rd job `RATE_LIMIT_DEFERRED`, no request sent | deferred work waits; nothing marked successful | window rolled over; job ran | budget never exceeded (3 requests in 2 windows) | 60.8 s |
| 7 | Cache (Redis) failure | **real**: `redis-cli shutdown` | Redis probe UNAVAILABLE; system DEGRADED | rate limiting switched to a process-local window; requests still served and still limited | **real** restart | Redis HEALTHY and back in use | <0.1 s (+30 s re-check interval) |
| 8 | Notification failure | **real** closed port as webhook endpoint | webhook `FAILED` after 3 attempts; never reported SENT | in-app delivery succeeded; alert DELIVERED via IN_APP | endpoint restored; operator requeue (audited) | exactly one delivery received | <0.1 s |

All 8 drills: complete, `passed: true`. Recovery times are wall-clock times in this sandbox at this data volume; they are not production RTOs.

**Correction recorded.** The first run of drill 4 was invalid. The model was `REGISTERED`, so inference refused it for that reason before ever reaching the artifact gate, yet the drill was marked complete. That run is now labelled `INVALID_DRILL` in `ops_incidents`. Drills now require an explicit passing verification, and the re-run used `VALIDATION_BACKTEST` mode, the only mode that may execute an unvalidated model, so the gate is reached.

## 2. Operational alerts

Failed or blocked ingestion jobs raise a platform alert automatically (`live_ingestion._finish`): category `INGESTION_<STATUS>`, with evidence (job, run, snapshot, errors), deduplicated per provider/resource/error class per hour, and delivered in-app. Platform alerts are visible to ADMIN and DATA_ENGINEER. The drills raise alerts the same way for worker loss, artifact integrity and Bronze integrity.

## 3. Degraded-mode guarantees (§36)

| Failure | What the system does | What it never does |
|---|---|---|
| Provider unavailable | serves last-valid Silver with its own timestamps; job FAILED; alert | invent or cache-substitute a payload |
| Model unavailable / untrusted | `MODEL_UNAVAILABLE` | fall back to priors or another model |
| Competition unsupported | `OUT_OF_DISTRIBUTION` / `INSUFFICIENT_DATA` | borrow another competition's validation |
| Database down | readiness 503, data endpoints fail closed | report HEALTHY (Phase 16's status endpoints did) |
| Redis down | process-local rate limits; status DEGRADED | drop rate limiting |
| Object storage down | ingestion FAILED (`SnapshotStoreError`), Silver untouched | leave a run RUNNING forever (the pre-Phase 17 behaviour) |
| Webhook down | in-app delivery; webhook FAILED after 3 attempts | report SENT |

## 4. Fixes made because of the drills
- `pool_pre_ping=True` on the API engine, so a database restart doesn't fail the first requests on dead pooled connections.
- `RUNNING` committed before the network call (IngestionService and the job runner), so a lost worker leaves a trace.
- `reap_stale_jobs()` marks orphans `FAILED: WORKER_LOST`.
- The local Bronze store verifies an existing file's hash before skipping a write, so a re-fetch heals corruption.
- `requeue_notification()` gives an audited operator retry after a channel outage.
- A storage failure during ingestion lands the run as FAILED instead of raising with the run stuck in RUNNING.
