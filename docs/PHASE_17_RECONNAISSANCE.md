# Phase 17 — Live Reconnaissance

**Date**: 2026-10-01
**Inspected commit**: `eb2ad0d` (branch `claude/zealous-babbage-k8mugx`)
**Execution environment**: Claude Code cloud container (Linux, Python 3.11.15, PostgreSQL 16.14, Redis 7, Node 22). No Docker daemon. Outbound HTTPS goes through an egress policy proxy.
**Method**: the repository and this container were the source of truth. Every claim below was checked by running a command; nothing is copied forward from earlier phase reports.

---

## 1. Headline findings

Phase 16 reports `PRODUCTION_FOOTBALL_INTELLIGENCE` with 608 passing tests. Inspection does **not** support that certification:

| # | Finding | Evidence | Severity |
|---|---|---|---|
| R1 | The 608-test baseline does not reproduce from Git. A fresh checkout gives **589 passed, 10 failed, 2 errors, 7 skipped** (608 collected). | 12 tests read `data/bronze/**` snapshot files, but `.gitignore` excludes them, so they never reached the repository. The Phase 16 run was on `platform win32` with local files. | High |
| R2 | `requirements.txt` does not install a working stack. | SQLAlchemy 2.1 no longer pulls in `greenlet`, so every async import fails. `moto` (used by tests) and `python-dotenv` (used by `tests/conftest.py`) are not listed. | High |
| R3 | `alembic upgrade head` fails on a fresh install. | SQLAlchemy 2.1 maps a bare `postgresql://` URL to `psycopg` (v3), but the repo ships `psycopg2`. `database/migrations/env.py` removed `+asyncpg` and left the driver unnamed. | High |
| R4 | **`POST /api/phase10/operations/ingestion/trigger` fabricates provider data.** | `OperationalIngestionPipeline.execute_cycle()` invents an API-Football fixture (`Arsenal 2–1 Chelsea`, id `1035999`, dated *now*), writes it to `data/bronze/api-football/fixtures/<sha>.json` as if the provider returned it, records stages `authentication_verified`, `silver_normalized`, `features_refreshed` and `model_readiness_confirmed` without running them, and returns `SUCCESS`. The `/operations` page's **Trigger ingestion** button calls this. | **Critical** |
| R5 | Operational status endpoints are hardcoded. | `/api/v1/operations/health` returns `latency_ms: 1.2`, `hit_ratio: 0.84`, `active_workers: 4`, `rate_limit_headroom_pct: 92.5`. `/api/v1/system/status` always returns `HEALTHY` / `environment: "production"`. `/api/v1/operations/status` returns a fixed timestamp `2026-09-27T00:00:00Z`. None of these probe anything. | **Critical** |
| R6 | Model health and drift are hardcoded. | `/api/v1/models/health` returns `prediction_volume_24h: 1420`, `ood_rate_pct: 1.4` and `calibration_status: CALIBRATED`. `/api/v1/models/drift` returns fixed PSI values. No inference telemetry is recorded anywhere. | **Critical** |
| R7 | Competition readiness is hardcoded and inconsistent. | `/api/v1/data/readiness` declares EPL `PRODUCTION_READY` for 8 engines. Copilot V6 declares La Liga, Bundesliga and Serie A `PRODUCTION_READY` at `confidence: 0.98`, contradicting the endpoint above (which says `MODEL_VALIDATED` / `DATA_AVAILABLE`). The Phase 10 readiness profile hardcodes `matches_count: 760`. | **Critical** |
| R8 | Model serving returns a fabricated prediction. | `ModelServingEngine.serve_inference()` returns `base_metric * 1.05` for model `valuation_ml_v1:1.2.0`, which does not exist. The only real artifact is `data/models/valuation/val_lightgbm_20260920.joblib`, with **validation R² = −0.011** (`registry_manifest.json`). Out-of-distribution requests are still served (`WARN_AND_SERVE`). | **Critical** |
| R9 | No authentication. Authorization trusts the caller. | Identity is a `user_id` field in the JSON body, so anyone can send `"user_id": "admin_01"`. `GET /api/v1/projects` and `GET /api/v1/watchlists` have no access check (IDOR). `/api/auth/me` returns a hardcoded `scout_01`. | **Critical** |
| R10 | Users, organisations and a project are seeded in the production path. | `ProjectAndAuthManager._seed_default_users_and_projects()` creates `admin_01`, `scout_01` and `analyst_01` at `org_arsenal`, plus a "Summer 2024" project. | High |
| R11 | Provider capabilities are seeded as `AVAILABLE` without any request. | `ProviderOrchestrator._seed_default_capabilities()` marks API-Football `transfers/fixtures/injuries` and football-data.org `fixtures/standings` as `AVAILABLE`. Both hosts are unreachable from this environment (§4). | High |
| R12 | All Phase 10–16 operational state is in process memory. | Projects, watchlists, alerts, audit log, jobs, freshness, incidents and the cache are Python dicts in module-level singletons, lost on restart. Phases 10–16 added **no migrations**: the head is still `0013`. | High |
| R13 | There is no StatsBomb → Silver path. | `NormalizationService` only calls `transform_api_football_*`. StatsBomb, the only provider reachable here, stops at Bronze. | High |
| R14 | `/data-ops` and `/model-ops` frontend routes do not exist. | `Football_OS-frontend/frontend/src/App.js` has no such routes. | Medium |
| R15 | The Phase 16 "26-step production workflow" test uses hand-written records. | `test_phase16_complete_production_workflow` ingests `{"player": "Martinelli", ...}` literals and calls them "real source data". `test_adversarial_24_database_unavailable` asserts `HEALTHY` without making the database unavailable. | High |
| R16 | 6 integration tests are broken. | `tests/integration/test_decision_intelligence_api.py` calls `NormalizationService.upsert_player_season_stats`, which does not exist. | Medium |
| R17 | CORS allows `*` together with `allow_credentials=True`. | `apps/api/app/main.py`. | Medium |
| R18 | The match model's registered metrics cannot be verified. | `prediction/registry.py` declares `calibrated_multinomial_logit_v1` was trained on 1,520 matches from "2026-08-01 to 2026-08-31" (dataset `bronze_2026_09_20`), with log loss 0.9418 and ECE 0.0385. One month cannot hold 1,520 top-flight matches, and that dataset is not in the repository. The model code is real; its metrics are **declared, not evidenced**. | High |
| R19 | ORM models and migrations have drifted. | `alembic.autogenerate.compare_metadata` against a freshly migrated database reports 32 pre-existing differences: nullability on 10 tables, and 6 indexes present in migrations but not in the models. | Low |
| R21 | The "open-transfers" Bronze dataset has self-asserted provenance. | `tools/curate_open_transfers*.py` contain hand-typed transfer records as Python literals. They write them to `data/bronze/open-transfers/` with metadata claiming `source_url: https://github.com/football-data/transfer-benchmarks/...`, a hardcoded `retrieval_date: 2026-09-21T01:00:00Z`, and `zero_fabrication_audit: "PASSED"`. No request is ever made: the URL is never fetched, and from this environment it cannot be reached or confirmed to exist. The records may describe real transfers, but the provenance chain (provider → request → snapshot) does not exist. The valuation LightGBM artifact (R8) was trained on this dataset, so its data lineage is **UNVERIFIED**. Phase 17 does not regenerate these files: doing so would write unverified provenance claims into Bronze. | **Critical** |
| R22 | The DB-backed Phase 7 decision endpoints fail against the real schema. | Once the R16 fixture is repaired (nonexistent `NormalizationService.upsert_player_season_stats` and `NormalizedPlayer(age=...)` removed), `/api/v1/decisions/recruitment` fails as follows. It first raised on a nonexistent `Player.club` relationship (fixed in Phase 17). It then fails reading `PlayerSeasonStats.minutes_played` / `matches_played`, while the real columns are `minutes` / `appearances`. `/replacement` and `/transfer-scenario` return 422 for the documented payloads. Result: 5 of 6 integration tests fail. They are left failing on purpose so the CI gate blocks deployment; they are not skipped. | High |
| R23 | The decision engine substitutes invented defaults when data is missing. | `decisions/recruitment.py` and `replacement.py` default to 900 minutes, 10 matches and age 24.0, and derive a contribution rating as `68 + minutes/100`. In a real recruitment workflow these defaults would be indistinguishable from data. **Observed on live data:** `GET /api/v1/decisions/recruitment` against the StatsBomb-loaded database returned HTTP 200. Its first candidate was "Franck Tabanou" (a left-back in the source lineups) as a "Free Agent" CM, age 24.0, 900 minutes, contribution rating 78.2, all of them defaults (`docs/evidence/phase17/workflow_e2e.json`, step 11). Phase 17 records the RECRUITMENT step as **UNVERIFIED** rather than routing evidence through it. | **Critical** |
| R24 | The Phase 13 scenario engine runs on a seeded roster. | `phase13/squad_baseline.py` seeds a hardcoded Arsenal roster with ratings and valuations. Scenario simulation never reads Silver. `GET /api/v1/decision-lab/squad/{club}` also returned a 500 for an unknown club (`get_baseline` returns None); Phase 17 changed that to a 404. | High |
| R20 | `ModelServingEngine` metadata does not match the real artifact. | It serves `valuation_ml_v1:1.2.0` (`features_v14.0`, `CALIBRATED`). The real artifact is `val_lightgbm_20260920` (`VALUATION_ML_V1`, feature set `1.0.0`). | High |

## 2. Actual repository baseline

| Item | Verified value |
|---|---|
| Migration head | `0013_valuation_ml_engine` (13 migrations; 28 public tables after `alembic upgrade head` on PostgreSQL 16.14) |
| Unit tests (fresh checkout, deps fixed) | 608 collected: **589 passed, 10 failed, 2 errors, 7 skipped** |
| Integration tests (real PostgreSQL) | **55 passed, 1 skipped, 6 errors** (R16) |
| Backend packages | `apps/api/app/{providers, ingestion, normalization, features, roles, tactical, prediction, market, decisions, phase9..phase16}` |
| Frontend | CRA/Craco app in `Football_OS-frontend/frontend`, 24 pages, 2 operations routes (`/operations`, `/operations/global`) |
| CI | `.github/workflows/ci.yml`: Postgres service, `alembic upgrade head`, `pytest -v`. Header says "NOT executed here". With R1–R3 it cannot pass as written. |

## 3. Classification of capabilities

| Capability | Classification | Basis |
|---|---|---|
| StatsBomb adapter (`providers/statsbomb.py`) | **Production-capable, live-verified** | Real HTTP 200 from `raw.githubusercontent.com` in 0.48 s (§4) |
| API-Football adapter | **Externally dependent; requires credentials; never tested live from here** | No `API_FOOTBALL_KEY`; host blocked by egress policy |
| football-data.org adapter | **Externally dependent; requires credentials; dormant (ADR-008)** | No `FOOTBALL_DATA_TOKEN`; host blocked |
| `IngestionService` (DB-backed runs → Bronze → validation) | **Production-capable** | Real code path with `ingestion_runs` / `data_snapshots` rows |
| Local filesystem snapshot store | **Local-only** | Writes to `./data/bronze` |
| S3/MinIO snapshot store | **Mocked only** (moto) | No Docker daemon, so MinIO cannot run here |
| `NormalizationService` (Silver) | **Production-capable for API-Football payloads only** | R13 |
| Feature, role, tactical and contribution engines | **Production-capable code, unexercised on live data** | Integration tests use fixtures |
| Match prediction (`prediction/`) | **Implemented; trained only on whatever data a run supplies** | No persisted match model artifact in the repo |
| Valuation LightGBM artifact | **Real artifact, weak model** | Validation R² −0.011 |
| Phase 16 provider orchestrator | **Simulated** (seeded statuses) | R11 |
| Phase 16 ingestion orchestrator | **Simulated** (in-memory dict) | R12 |
| Phase 16 model serving | **Fabricated output** | R8 |
| Phase 16 health / system / models / drift / readiness endpoints | **Fabricated output** | R5–R7 |
| Phase 16 RBAC | **Implemented logic, no authentication** | R9 |
| Phase 16 audit log | **Implemented hash chain, in memory only** | R12 |
| Phase 16 alerting, jobs, cache | **In memory only** | R12 |
| Copilot V6 | **Partially grounded**: some families read in-memory engines; competition readiness is hardcoded | R7 |
| Redis | **Configured, unused** | Nothing in `apps/api` imports a Redis client |
| Scheduler / worker | **Absent** | `apps/worker` does not exist (README, ADR-004) |
| Docker Compose stack | **Never run** (file header says so); cannot run here | No Docker daemon |
| Object storage (MinIO) | **Cannot be verified here** | No Docker daemon |
| CI/CD | **Defined, never verified** | R2/R3 would fail it |

## 4. Live provider reachability (real probes, 2026-10-01 ~14:55 UTC)

| Provider | Host | Result | Proxy / server evidence |
|---|---|---|---|
| StatsBomb Open Data | `raw.githubusercontent.com` | **HTTP 200**, 34,887 bytes, 0.478 s | Real competitions payload (first record: 1. Bundesliga 2023/2024) |
| API-Football | `v3.football.api-sports.io` | **BLOCKED**: proxy answered 403 to CONNECT | `recentRelayFailures: connect_rejected … v3.football.api-sports.io:443` |
| football-data.org | `api.football-data.org` | **BLOCKED**: proxy answered 403 to CONNECT | `recentRelayFailures: connect_rejected … api.football-data.org:443` |

The request never reached API-Football or football-data.org, so nothing can be concluded about their credentials, quotas or payloads. They are `BLOCKED`, not `AUTH_FAILED` and not `UNAVAILABLE`.

Credentials present in the environment: **none** (`API_FOOTBALL_KEY` and `FOOTBALL_DATA_TOKEN` are unset).

## 5. Infrastructure available in this environment

| Component | State |
|---|---|
| PostgreSQL 16.14 | Running locally (`setup_pg.sh`); `fios` and `fios_test` databases migrated to `0013` |
| Redis 7 | Running locally (`redis-server --daemonize yes`); answers `PONG` |
| Docker | CLI installed; **daemon not running** (`/var/run/docker.sock` absent), so no MinIO and no Compose |
| Object storage | Local filesystem only |
| Network | Egress policy proxy: GitHub raw content allowed; commercial football APIs denied |

## 6. What has never been tested against a live provider

- Any API-Football resource (fixtures, lineups, events, statistics, players, transfers, injuries, standings, odds).
- Any football-data.org resource.
- Near-real-time match state (no reachable provider publishes live matches; StatsBomb Open Data is a historical archive).
- S3/MinIO snapshot storage.
- Notification delivery (no email or webhook provider is configured).
- Any multi-user production traffic.

## 7. What cannot currently be verified from this environment

- Live commercial provider connectivity, quotas and rate-limit behaviour (egress block plus missing keys).
- Live fixtures, live match state, and live pre-match prediction → real outcome loops.
- Production deployment (no deployment target is configured; no Dockerfile run).
- Real users and real field telemetry.
- Real provider billing or cost.

## 8. Consequences for Phase 17

1. Before any new capability, Phase 17 must **remove fabrication from production paths** (R4–R11). A system that reports invented health cannot be validated against reality.
2. The only real provider path available is **StatsBomb Open Data**: real, keyless, but **historical**. Everything built on it is `REAL DATA / HISTORICAL ARCHIVE`, never `LIVE`.
3. Commercial-provider capabilities stay **`BLOCKED` / `UNVERIFIED`** until a session with egress allowed and keys configured re-runs the evidence harness.
4. Operational state that must survive restarts (users, projects, watchlists, alerts, audit, inference log, outcomes, decisions, incidents, probes) has to move into PostgreSQL.
