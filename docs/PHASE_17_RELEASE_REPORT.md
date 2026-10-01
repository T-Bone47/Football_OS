# Phase 17 Release Report — Live Football Intelligence Operations

**Date**: 2026-10-01
**Branch**: `claude/zealous-babbage-k8mugx` (base `eb2ad0d`)
**Environment**: Claude Code cloud sandbox (Linux, Python 3.11.15, PostgreSQL 16.14, Redis 7, Node 22, Chromium via Playwright). Egress through a policy proxy. No Docker daemon. No deployment target.
**Final state**: **`PHASE_17_RELEASE_BLOCKED`** (§38)

Evidence files are in `docs/evidence/phase17/`. Every number in this report comes from one of them or from a test run recorded here.

---

## 1. Executive Summary

Phase 17 asked whether the Football Intelligence OS can operate against real providers, data, workloads, users and outcomes. The answer, with evidence:

- **It can operate reliably on real data from the one provider this environment can reach** (StatsBomb Open Data). 511/511 real ingestion jobs succeeded and 478 matches reached Silver with complete lineups. Idempotency held on every re-run. Quality was PASS with real cross-checks (goal events vs final scores). 100/100 sampled records traced to Bronze files whose SHA-256 re-verified. Replay is deterministic. Eight incident drills (four using real outages) recovered without fabrication or partial writes, and backup/restore verified byte- and hash-level integrity.
- **It cannot yet be called live.** API-Football (the configured live provider; key present) is blocked by this environment's egress policy, so there is no live fixture, no live prediction, no live outcome and no live calibration. StatsBomb is a historical archive.
- **The match prediction model fails validation on real data.** In a walk-forward over 330 Premier League 2015/16 matches its log loss is 1.183 against 1.080 for base rates. The gate kept it unservable; the declared metrics in its registry (log loss 0.94) are not reproducible from the repository.
- **The Phase 16 certification was not supported by the code.** Reconnaissance found fabricated status endpoints, an ingestion trigger that invented provider data and wrote it to Bronze, a dummy model, caller-asserted identity, seeded users and capabilities, and a 608-test baseline that does not reproduce from Git (`PHASE_17_RECONNAISSANCE.md` R1–R24). Phase 17 removed every one of those fabrications from production paths and documented the rest.

Phase 17 is therefore **not** certifiable as `LIVE_FOOTBALL_INTELLIGENCE_OPERATIONAL`. What it delivers is an operations layer that tells the truth about the system, and the evidence of where the system stands.

## 2. Actual Repository Baseline

| | Fresh checkout of `eb2ad0d` | After Phase 17 |
|---|---|---|
| `pip install -r requirements.txt` | broken: no greenlet, moto or python-dotenv (R2) | fixed |
| `alembic upgrade head` | fails on SQLAlchemy 2.1 (R3) | fixed; head `0014` |
| Unit tests | 589 passed, **10 failed, 2 errors**, 7 skipped | **641 passed, 0 failed**, 20 skipped |
| Integration tests (real PostgreSQL) | 55 passed, **6 errors**, 1 skipped | **99 passed, 5 failed (R22)**, 1 skipped |

Phase 16's "608 passed" was produced on a machine with gitignored Bronze files (R1). The 13 tests that need those files now skip with an explicit `NOT_TESTED: requires Bronze evidence … never committed` reason; they run wherever the files exist. The 5 failing integration tests are real Phase 7 production defects (R22), left failing so the CI gate blocks.

## 3. Environment Matrix

See `PHASE_17_LIVE_DATA_OPERATIONS.md` §1. DEVELOPMENT, TEST, STAGING and PRODUCTION have separate databases, Redis DBs, object stores and artifact locations, and `${…}` secrets. Isolation is checked by `audit_isolation()` (tested on the four templates). Staging and production refuse to start with default or empty secrets, wildcard or localhost CORS, or local Bronze (tested). Production is never a default. Status: **VERIFIED** (configuration); **NOT_TESTED** in a deployed staging/production.

## 4. Provider Connectivity

| Provider | State | Evidence |
|---|---|---|
| StatsBomb Open Data | **LIVE_VERIFIED** | HTTP 200, 404–2,026 ms, 3 resources |
| API-Football | **BLOCKED** (key present, never transmitted) | egress proxy refused `CONNECT` to `v3.football.api-sports.io` |
| football-data.org | **BLOCKED** (no token) | egress proxy refused `CONNECT` |

Details: `PHASE_17_PROVIDER_MATRIX.md`.

## 5. Live Provider Capability Matrix

StatsBomb: competitions, matches, lineups and events are LIVE_AVAILABLE; 3 of 80 indexed competition-seasons were ingested; the other 77 are UNVERIFIED. API-Football: every resource UNVERIFIED (blocked). Transfers, injuries, standings, statistics and odds have no reachable source. `PHASE_17_PROVIDER_MATRIX.md` §2.

## 6. Real Ingestion Results

511 jobs, 511 SUCCESS. 3 matches files (478 matches), 478 lineup files, 24 event files and 1 competitions index, plus idempotency re-runs. Silver: 478 matches, 70 clubs, 1,802 players, 18,275 lineup rows, 360 discrete events. Peak 50 requests/min against a self-imposed budget of 60; 0 retries, 0 × 429. `PHASE_17_LIVE_DATA_OPERATIONS.md` §3.

## 7. Bronze/Silver Verification

Content-addressed Bronze with provider retrieval time, HTTP status, source URL, licence, schema fingerprint and run ID. All 5 idempotency re-runs gave identical SHA-256s and a zero Silver delta. Bytes are re-verified before Silver and replay. The new StatsBomb → Silver path handles real provider quirks: shootout goals, `"Tactical Shift"` starters, `position_id`. Silver quality is PASS for all 3 pilots.

## 8. Data Quality

`DataQualityReport` (PASS/WARN/FAIL with counts) for every payload and Silver scope. Checks that cannot run are reported WARN with `evaluated: false`. Score/event reconciliation passed on all 24 matches with events. Contract drift blocks Silver (adversarial 3). `PHASE_17_LIVE_DATA_OPERATIONS.md` §9–10.

## 9. Freshness

Timestamps at 8 layers, from the provider's own `last_updated` through Bronze, Silver, features, model, inference, decision and alert. Archive data reports `is_live: false` however recently it was retrieved. Staleness compares against when content first arrived, so identical re-ingestion doesn't mark Silver stale. `PHASE_17_FRESHNESS.md`.

## 10. Feature Refresh

Dependency-hashed versions. First pass: 70 clubs REFRESHED. Second pass: 70 UNCHANGED, **0 recomputed**. A stale feature refuses inference with `STALE_DATA` (adversarial 9).

## 11. Model Operations

Registry, gated inference (MODEL_UNAVAILABLE, TEMPORAL_VIOLATION, OUT_OF_DISTRIBUTION, STALE_DATA, INSUFFICIENT_DATA), an immutable inference log, artifact-integrity and feature-version checks, ADMIN-only promotion gated on live evidence, and an audited demotion. Phase 16's dummy serving was removed. `PHASE_17_MODEL_OPERATIONS.md`.

## 12. Competition Pilot

Premier League 2015/16, World Cup 2022 and Bundesliga 2023/24 (Leverkusen only). All three are **DATA_AVAILABLE**; none is MODEL_VALIDATED, SHADOW or PRODUCTION_READY, and nothing was inherited. `PHASE_17_COMPETITION_PILOT.md`.

## 13. Live Predictions

**0 live predictions served.** Every LIVE-mode request was refused: `MODEL_UNAVAILABLE` (no validated model), or `TEMPORAL_VIOLATION` (archive kickoffs are in the past; backdated LIVE requests are refused). 480 validation-backtest requests (334 served) are labelled `VALIDATION_BACKTEST`, never live.

## 14. Live Outcomes

**0 live outcomes.** 335 historical-replay outcomes, linked by timestamp-derived observation mode. Predictions are never edited. `PHASE_17_LIVE_OUTCOMES.md`.

## 15. Calibration

LIVE: **NOT_ENOUGH_LIVE_OUTCOMES** (0 of 100). Historical replay, n = 334: log loss 1.181 (baseline 1.079), Brier 0.701, ECE 0.210, MCE 0.367, accuracy 0.473. Poorly calibrated and worse than base rates.

## 16. Drift

LIVE: NOT_ENOUGH_OBSERVATIONS. Validation backtest: DRIFT (`elo_diff` PSI 0.418), consistent with Elo warm-up across a season. Gives `RETRAIN_RECOMMENDED`, routed to the governed challenger workflow; nothing retrains automatically.

## 17. Watchlists

Conditions on real Silver data (player starts, appearances, goals, cards; club points, goals). Evidence carries match IDs and Bronze SHA-256s. Data sufficiency is explicit: `EVENTS_NOT_INGESTED` is reported instead of "0 goals". Workflow: "started ≥ 3 of last 5" was genuinely met for a real player and alerted once.

## 18. Alerts

Alerts need evidence (DB CHECK constraint) and a dedup key, and fire only on a not-met → met transition. States: TRIGGERED → DELIVERED → ACKNOWLEDGED / DISMISSED → RESOLVED, with illegal transitions rejected. Operational alerts are raised automatically for failed or blocked ingestion (hourly dedup). Notifications: IN_APP always; WEBHOOK only when configured, SENT only on 2xx, at most 3 attempts, audited requeue; EMAIL NOT_CONFIGURED (no delivery path exists).

## 19. User Workflows

21-step workflow over real HTTP: 17 VERIFIED / LIVE_VERIFIED, 1 VERIFIED_REFUSAL (prediction), 2 **UNVERIFIED** (recruitment R23, scenario R24), and 0 failed in the final run. Persistent organizations, users, projects, watchlists and decisions with API-level authorization (user A cannot see user B's private project; another organization cannot see either). `PHASE_17_FIELD_VALIDATION.md` §1.

## 20. Copilot

Copilot V7 answers 10/10 required operational queries from registered read-only tool calls, with result digests. It refuses injection and exfiltration with no tool call, answers UNVERIFIED when tools return nothing that supports a claim, and answers UNVERIFIED for unsupported questions. Copilot V6's hardcoded readiness answer and its `LIVE_TELEMETRY` label were removed.

## 21. Observability

Correlation IDs (existing middleware), measured per-route latency (`/telemetry/latency`), real component probes (`/system/status`), job, quality, probe, inference and incident tables, and a hash-chained audit log. A failed workflow is traceable request → job → ingestion run → snapshot → provider error. Limitations: metrics are process-local, there is no distributed tracing backend, and no external alerting sink.

## 22. Incident Drills

8/8 drills complete and passing; 4 used real outages (PostgreSQL stop, Redis shutdown, worker SIGKILL, file corruption) plus a real exhausted budget, a real closed webhook port and a real registry tamper. One invalid first run was relabelled `INVALID_DRILL`. `PHASE_17_INCIDENT_RESPONSE.md`.

## 23. Security

Bearer-token authentication, organization/project/role authorization, no enumeration, per-user rate limits, idempotency keys, and append-only audit with tamper detection. Secret scan: 0 findings, including the configured key, git history and the production bundle. pip-audit: no known vulnerabilities. **Frontend: 79 advisories (60 high), 17 of them in runtime dependencies (axios, react-router-dom).** `PHASE_17_SECURITY.md`.

## 24. Backup/Restore

pg_dump/pg_restore with 0 row mismatches across 47 tables and 27,212 rows; audit chain head hash identical; all 506 Bronze files re-hashed. Measured recovery ≈1.8 s at this volume. Object-store restore NOT_TESTED. `PHASE_17_DISASTER_RECOVERY.md`.

## 25. Rollback

Application rollback (N-1 on the N schema) VERIFIED. Migration downgrade/upgrade VERIFIED on a data-bearing copy; it destroys operational evidence, so production policy is forward-fix only. Model demotion VERIFIED. Configuration rollback NOT_TESTED.

## 26. Performance

Warm p95 under 25 ms for most endpoints on one worker; operations-dashboard readiness p95 87 ms; cold starts up to 296 ms. **SIMULATED** in the sandbox. `PHASE_17_FIELD_VALIDATION.md` §3.

## 27. Load Testing

**SIMULATED_LOAD.** 10/25/50 users: 0% errors, 45–53 req/s (one worker CPU-bound). **100 users: 8.4% server errors, p95 30 s**, from SQLAlchemy pool exhaustion. The shipped configuration does not support 100 concurrent users.

## 28. Provenance

100/100 sampled Silver records traced to a provider request and a Bronze file whose SHA-256 re-verified; 0 orphans across matches, lineups and events. Not covered: the open-transfers dataset and the valuation model trained on it (R21), whose provenance chain does not exist.

## 29. Model Lineage

Each inference row records model ID and version, feature version, dataset version, data cutoff, features used, missing features, reasons, and evidence (the history match IDs). `GET /inference/{id}/provenance` resolves the history to Bronze snapshots and providers. Tested via the API.

## 30. Decision Lineage

Decision → evidence graph (built server-side) → inference → model → Silver matches → Bronze SHA-256 → ingestion run → provider, plus the outcome. Content hash re-verified; staleness computed; immutable at the database level, with revisions as `supersedes_id` rows. Tested (adversarial 13; workflow step 17).

## 31. Replay

The deterministic boundary is the Bronze snapshot. Replay re-verifies SHA-256 and re-normalizes. Silver digests, features, inference outputs and input digests are identical (adversarial 21; workflow step 20).

## 32. Frontend

`/operations` rewritten; `/data-ops` and `/model-ops` added. Every value comes from `/api/v1/ops`, behind a bearer-token gate kept in session storage only. States are truthful: loading, error with HTTP reason, empty. Validated in Chromium at desktop and 390 px: 0 error states and 0 px overflow. Production build clean except 2 pre-existing lint warnings in other pages. `/decision-lab`, `/outcome-intelligence` and `/research` were not exercised.

## 33. Adversarial Tests

`tests/integration/test_phase17_adversarial.py`, **30/30 passing** against a migrated PostgreSQL:

| # | Scenario | # | Scenario |
|---|---|---|---|
| 1 | Duplicate live ingestion | 16 | Prompt injection |
| 2 | Conflicting provider payload | 17 | Secret exfiltration attempt |
| 3 | Provider schema drift | 18 | Fake alert insertion |
| 4 | Provider outage | 19 | Fake operational status |
| 5 | Rate-limit exhaustion | 20 | Future-data contamination |
| 6 | Invalid provider credential | 21 | Replay divergence |
| 7 | Partial provider response | 22 | Cache poisoning |
| 8 | Corrupt Bronze snapshot | 23 | Worker retry storm |
| 9 | Stale feature used for prediction | 24 | Duplicate notification |
| 10 | Unsupported competition prediction | 25 | Database outage |
| 11 | OOD prediction request | 26 | Object-storage outage |
| 12 | Historical prediction mutation | 27 | Model artifact corruption |
| 13 | Historical decision mutation | 28 | Configuration secret leakage |
| 14 | Unauthorized project access | 29 | Audit log tampering |
| 15 | Unauthorized model promotion | 30 | Rollback inconsistency |

## 34. Full Regression

| Suite | Result |
|---|---|
| Unit (`tests/unit`) | **641 passed, 0 failed**, 20 skipped (13 `NOT_TESTED` out-of-repo Bronze, 7 pre-existing) |
| Integration (`tests/integration`, real PostgreSQL 16) | **99 passed, 5 failed**, 1 skipped. The 5 failures are R22 (Phase 7 DB path), pre-existing and intentionally not masked |
| New Phase 17 tests | 95 (52 unit including 2 API-contract, 13 functional integration, 30 adversarial) |
| Frontend production build | success, locally and in CI. Four pre-existing `exhaustive-deps` warnings outside the Phase 17 pages failed the first CI build under `CI=true`; they are now annotated in place (§37, CI result) |

Phase 16/10 tests changed by Phase 17. Each asserted behaviour reconnaissance found fabricated, and each is marked `Phase 17:` in place:
- `test_phase16_production_platform.py`: seeded `AVAILABLE`, dummy predictions, `LIVE_TELEMETRY`, constant `HEALTHY`, failover with invented payloads.
- `test_phase10_operations.py`: the 11-stage cycle built on an invented fixture.

## 35. Limitations

1. No live provider reachable. API-Football is blocked by egress; its key is configured but unverified.
2. StatsBomb is a historical archive, so nothing here is real-time.
3. The match model fails validation; no model is servable.
4. Phase 7 recruitment returns defaults as data (R23) and its DB path is broken (R22). Phase 13 scenarios run on a seeded roster (R24).
5. The valuation model and open-transfers data have unverified provenance (R21).
6. Capacity: one worker; fails at 100 concurrent users.
7. Process-local rate governor and metrics; no worker daemon (cron entrypoint only).
8. Silver promotion reads Bronze from local storage only; S3/MinIO is untested.
9. No production deployment, real users or user telemetry.
10. Frontend runtime dependency advisories (axios, react-router-dom).
11. Schema drift between ORM and migrations (R19, pre-existing).

## 36. Unsupported Capabilities

Near-real-time match state; live pre-match prediction; live outcomes and calibration; transfer-market monitoring (§17); injuries, standings and odds; email notifications; live player market context; cost in currency (`monetary_cost: UNAVAILABLE`); multi-instance rate limiting.

## 37. Release Gate Audit

Status vocabulary per §63.

| Gate | Implementation | Live evidence | Test evidence | Limitation | Status |
|---|---|---|---|---|---|
| G1 Live Reconnaissance | `PHASE_17_RECONNAISSANCE.md`, R1–R24 | real installs, migrations, probes, test runs | – | – | **VERIFIED** |
| G2 Environment Separation | `phase17/environments.py`, 4 templates, startup policy | – | 6 unit tests | no deployed staging/prod | **VERIFIED** (config) |
| G3 Provider Connectivity | `provider_probe.py` | StatsBomb 200; API-Football and football-data BLOCKED | 14 unit tests | commercial providers unreachable | **BLOCKED** (live provider) / LIVE_VERIFIED (StatsBomb) |
| G4 Provider Capability | `readiness.capability_matrix` | 3/80 StatsBomb competition-seasons | integration | API-Football UNVERIFIED | **PARTIAL → UNVERIFIED** for live provider |
| G5 Real Ingestion | `live_ingestion.py` | 511/511 real jobs | 13 integration + adversarial 1–8 | archive data only | **LIVE_VERIFIED** (archive) |
| G6 Bronze Integrity | SHA-256, re-verify, self-heal | 100/100 provenance hashes | adversarial 8, drill 5 | S3 untested | **VERIFIED** |
| G7 Idempotency | content addressing + upserts | 5/5 re-runs, delta 0 | adversarial 1 | – | **VERIFIED** |
| G8 Rate Limiting | `rate_governor.py`, 429 cooldown | 511 requests, budget never exceeded | adversarial 5, 23; drill 6 | process-local | **VERIFIED** |
| G9 Failure Handling | runner statuses, storage failure fix | drills 1–3, 5 | adversarial 4–7, 25, 26 | – | **VERIFIED** |
| G10 Data Quality | `data_quality.py` | 3 Silver PASS; 1 real quirk caught | unit + adversarial 2, 7 | single-provider conflicts not evaluable | **VERIFIED** |
| G11 Freshness | `freshness_chain` | 8-layer chain per pilot | integration | archive only | **VERIFIED**; live NOT_TESTED |
| G12 Feature Refresh | `feature_refresh.py` | 70 REFRESHED → 70 UNCHANGED | integration, adversarial 9 | one feature family | **VERIFIED** |
| G13 Model Readiness | registry + gates | model correctly REGISTERED | adversarial 10, 11, 27 | – | **VERIFIED** |
| G14 Live Inference | `infer_match` LIVE mode | 15 LIVE requests, all refused truthfully | integration | no servable model; no live fixtures | **BLOCKED** |
| G15 Match State | `match_state.py` | FINAL / archive / `real_time: false` | unit | no live provider | **IMPLEMENTED**; live **UNVERIFIED** |
| G16 Transfer Monitoring | – (Phase 4 taxonomy unchanged) | none reachable | – | no source | **NOT_TESTED** |
| G17 Competition Pilot | 3 pilots, readiness matrix | all DATA_AVAILABLE | integration | model fails | **VERIFIED** (data) / BLOCKED (model) |
| G18 Live Outcomes | `record_outcome` | 0 live, 335 replay | integration | no live predictions | **BLOCKED** |
| G19 Calibration | `calibration_report` | live NOT_ENOUGH; replay measured | unit | – | **NOT_TESTED** (live) |
| G20 Drift | `drift_report` | live NOT_ENOUGH; validation DRIFT | unit | – | **NOT_TESTED** (live) |
| G21 Watchlists | `alerts.measure/evaluate_item` | real condition met, real evidence | integration, adversarial 24 | – | **VERIFIED** |
| G22 Alerts | dedup, CHECK, transitions, notifications | 1 watchlist + operational alerts | integration, adversarial 18, 24; drill 8 | email not configured | **VERIFIED** |
| G23 User Workflow | `workflow_e2e.py` | 21 steps: 17 verified, 1 refusal, 2 unverified | adversarial 14 | recruitment/scenario not data-backed; no real users | **UNVERIFIED** (2 steps) |
| G24 Copilot | `copilot_v7.py` | 10/10 grounded; injection refused | unit, integration, adversarial 16, 17 | keyword routing | **VERIFIED** |
| G25 Observability | probes, telemetry, audit, tables | used in all drills | contract tests | process-local metrics, no tracing backend | **VERIFIED** (single instance) |
| G26 Incident Response | `incidents.py`, 8 drills | 8/8 passed (4 real outages) | – | sandbox scale | **VERIFIED** |
| G27 Security | auth, authz, audit, secret scan | 0 secret findings; authz over HTTP | 30 adversarial, contract tests | frontend advisories; no pen test | **DEGRADED** |
| G28 Backup/Restore | `dr_drill.py` | 0 mismatches; Bronze re-hashed | – | S3 untested | **VERIFIED** (local) |
| G29 Rollback | `rollback_drill.py`, demote endpoint | app, migration, model verified | adversarial 30 | config NOT_TESTED | **VERIFIED** |
| G30 Performance | telemetry + `load_test.py` | per-endpoint p50/p95/p99 | – | sandbox | **SIMULATED** |
| G31 Load Testing | `load_test.py` | 10/25/50 OK; 100 fails 8.4% | – | sandbox | **SIMULATED**, fails at 100 |
| G32 Provenance | lineage queries | 100/100, 0 orphans | integration | R21 dataset excluded | **VERIFIED** |
| G33 Model Lineage | inference log + provenance endpoint | via API | integration | – | **VERIFIED** |
| G34 Decision Lineage | evidence graph, content hash | workflow step 17 | adversarial 13 | – | **VERIFIED** |
| G35 Replay | `replay_snapshot` | workflow step 20 | adversarial 21 | – | **VERIFIED** |
| G36 Frontend | 3 consoles | Chromium at desktop and mobile | build | 3 legacy pages not exercised | **VERIFIED** (ops pages) |
| G37 CI/CD | `.github/workflows/ci.yml` (all §47 gates) | GitHub Actions run 5 on `542d478`: every gate ran; 2 red (see below) | lint, migrations, unit, pip-audit and secret scan green in CI | integration fails on R22; frontend audit fails (60 high) | **BLOCKED** (gate correctly red) |
| G38 Adversarial Tests | 30 scenarios | – | 30/30 | – | **VERIFIED** |
| G39 Documentation | 12 Phase 17 docs + evidence | – | – | – | **VERIFIED** |
| G40 Production Readiness | – | no deployment; providers blocked; model fails | – | – | **BLOCKED** |
| G41 Final Release Audit | this report | – | – | – | **PHASE_17_RELEASE_BLOCKED** |

### CI result (GitHub Actions)

The base commit `eb2ad0d` failed CI on `main` (run 3) at its migrations step, before any test ran. That is R3 observed independently: the Phase 16 suite never ran in CI.

Run 4 on `e296970`, the first Phase 17 push, exposed two defects in the new workflow. The frontend build failed under `CI=true`, which turns four pre-existing `react-hooks/exhaustive-deps` warnings (Decision Lab and Outcome Intelligence pages) into errors; the local verification build had not set `CI=true`. Each job also stopped at its first red gate, so pip-audit, the secret scan and the frontend audit never ran. Both were fixed in `542d478`: the four effects are annotated as intentionally key-scoped, and later gates now run unless the workflow is cancelled.

[Run 5](https://github.com/T-Bone47/Football_OS/actions/runs/36893259233) on `542d478`, GitHub-hosted `ubuntu-latest`, PostgreSQL 16.15 and Redis 7.4 service containers:

| Gate | Result |
|---|---|
| Lint (ruff E9,F on Phase 17 code) | pass |
| Typing | NOT_CONFIGURED (reported, not faked) |
| Migrations: upgrade → downgrade 0013 → upgrade | pass |
| Unit tests (including API contract) | pass |
| Integration, replay and adversarial (real PostgreSQL) | **fail: 5 failed, 99 passed, 1 skipped**. Identical to the local run; all 5 are R22 (`'PlayerSeasonStats' object has no attribute 'minutes_played'` and the dependent 500/422) |
| pip-audit | pass: no known vulnerabilities |
| Secret scan | pass: 0 findings |
| Frontend production build | pass |
| Frontend dependency audit (high and critical) | **fail: 79 advisories (60 high, 19 moderate)** across 1,492 packages, matching the local audit |

The deployment gate is red for exactly the two reasons this report names, and for no other.

## 38. Final Certification

| State | Achieved | Why |
|---|---|---|
| LIVE_PROVIDER_VALIDATED | **No** | The only live-capable provider (API-Football) is blocked at egress; its configured key is unverified. StatsBomb is LIVE_VERIFIED for connectivity but is an archive. |
| LIVE_DATA_PIPELINE_VALIDATED | **No** | The pipeline is validated end to end on **real archive data**, not live data. |
| LIVE_MODEL_OPERATIONS_VALIDATED | **No** | The operations machinery works, but no model passes validation and no live inference was served. |
| LIVE_FIELD_WORKFLOW_VALIDATED | **No** | The workflow ran over real HTTP on real backend state, but recruitment and scenario steps are not data-backed, and there are no real users. |
| LIVE_OUTCOME_VALIDATED | **No** | 0 live outcomes. |
| PRODUCTION_OPERATIONAL | **No** | No deployment; capacity fails at 100 users. |
| LIVE_FOOTBALL_INTELLIGENCE_OPERATIONAL | **No** | – |

**Certified state: `PHASE_17_RELEASE_BLOCKED`.**

### What unblocks it, in order
1. **Network**: allow `v3.football.api-sports.io` in the cloud environment's network settings (the key is already configured locally), then re-run `tools/phase17/live_pipeline.py`. Probes, capability and quota become provider-reported.
2. **Live loop**: schedule API-Football fixtures (LIVE class) for one pilot league; log pre-kickoff predictions; let ≥100 live outcomes accrue.
3. **Model**: fit a challenger through the governed workflow, validate it per competition with walk-forward on real data, and promote only on live evidence.
4. **Decision engine**: fix R22 and remove R23's defaults (make missing data explicit). Back Phase 13 scenarios with Silver (R24).
5. **Capacity**: multiple workers, a pool sized to them, PgBouncer; re-run `load_test.py`.
6. **Frontend**: upgrade `axios` and `react-router-dom`; remove the third-party template scripts.
7. **Deployment**: stand up staging with S3 Bronze; re-run the DR and incident drills there.
