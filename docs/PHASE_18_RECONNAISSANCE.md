# Phase 18 — Reconnaissance (Production Truth)

**Date**: 2026-10-01 · **Branch**: `claude/zealous-babbage-k8mugx` · **HEAD at start**: `c8860c8`
**Method**: repository and executable behaviour only. Earlier release reports (Phases 8–17) are not treated as evidence. Every finding below was observed with a command or by reading code. The commands are listed with each finding.

## 1. Actual current state

| Area | Observed |
|---|---|
| Runtime | Python 3.11.15, Node 22.22, PostgreSQL 16.14, Redis 7.0.15 (sandbox) |
| API surface | 272 operations in 11 routers (`app.openapi()`): canonical `/api/v1/*` (DB-backed), legacy `/api/phase10…phase16`, `/api/v1/ops/*` (Phase 17, DB-backed, authenticated) |
| Migrations | `0001` → `0014`, linear, `alembic upgrade head` succeeds on an empty database |
| Schema parity | **`alembic check` FAILS**: 32 pending operations (NOT NULL on 14 timestamp columns, 9 indexes missing in the DB, 6 indexes the ORM does not declare) |
| Dependencies | `requirements.txt` is entirely unpinned (`>=` or no constraint); no lock file |
| Tests (Phase 17 close) | unit 641 passed, 20 skipped; integration 99 passed, **5 failed (R22)**, 1 skipped; CI run 7 red for the same reasons plus the frontend audit |
| Providers | StatsBomb open data reachable; API-Football and football-data.org blocked by the sandbox egress proxy (`PROVIDER_BLOCKED`) |

## 2. New findings (beyond Phase 17's R1–R24)

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| **N1** | **Critical** | **About 60 seeding sites across phases 10–16 put invented football content into production routes.** Each engine is a module-level singleton that seeds itself at import: players, trajectories, transfers, research cohorts, hypotheses, alerts, outcomes, decision records and Pareto frontiers. Examples: `phase12/emerging_players.py` ("Gonçalo Inácio"), `phase14/outcome_ledger.py` ("verified outcomes"), `phase15/league_translation.py` (ten hand-typed "realistic Bundesliga → EPL transitions"), `phase13/squad_baseline.py` (Arsenal roster). Nothing marks any of it as a fixture. | `grep -rnE "self\._seed[a-z_]*\(\)\|# Seed" apps/api/app` |
| **N2** | **Critical** | **The model governance registry hardcodes six models as `MODEL_VALIDATED`** with literal metrics (`observability/model_governance.py`). `/model-status` reports them as active engines. | file read |
| **N3** | **Critical** | **The match prediction registry defaults every model to `status="MODEL_VALIDATED"`** (`prediction/registry.py`). The served "trained" model is five hand-typed weights in `prediction/models.py`, with no artifact and no training code. On `INSUFFICIENT_DATA` the service still answers with priors and a fixed xG of 1.35 / 1.15. | file read |
| **N4** | **Critical** | **`/data-status` hardcodes** `provenance_coverage_rate: 1.0`, `data_freshness_status: FRESH`, `status: HEALTHY` and `schema_version: "0013"` (head is 0014). | `observability/system_health.py` |
| **N5** | **Critical** | **`/api/auth/me` returns a hardcoded user** ("Head of Scouting"). The frontend's `ProtectedRoute` trusts it, so every page is "authenticated". `/api/copilot/query` is unauthenticated. | `main.py:104` |
| **N6** | High | The valuation model is registered `MODEL_VALIDATED` with **test R² −0.09 and validation R² −0.01**. Its artifact path is a Windows path from another machine, and it was trained on the open-transfers dataset whose provenance is self-asserted (R21). | `data/models/valuation/registry_manifest.json` |
| **N7** | High | Four model registries disagree: `observability/model_governance.py`, `prediction/registry.py`, `market/ml/registry.py` (JSON file), and `ops_model_registry` (DB, Phase 17). This is R20 widened. | grep |
| **N8** | High | Phase 12 and 14 mutating routes take `created_by` from the request body. Phase 16 legacy routes take `user_id` from the body (development only since Phase 17). Phase 10 recruitment projects, watchlists and scenarios have **no authentication at all**. | `routes_phase1*.py` |
| **N9** | Medium | The frontend calls `/api/shortlists*`, which the backend does not implement (404). | `lib/footballApi.js:342` |
| **N10** | Medium | `requirements.txt` has no pins and no lock. The Python dependency set is whatever the resolver picks on the day. | file |
| **N11** | Medium | Tracked `scratch/` directory (`debug_hash.py`, `run_pipeline.py`, `extract_prompt.py`) contains developer debugging scripts. | `git ls-files scratch` |

## 3. Status of Phase 17 findings at Phase 18 start

| R | Phase 17 outcome | Still open in Phase 18 |
|---|---|---|
| R1 | fresh-checkout fixes, NOT_TESTED skips | full clean-clone certification not yet run |
| R2 | greenlet / moto / python-dotenv added | no pins, no lock (N10) |
| R3 | `+psycopg2` in `env.py` | – |
| R4 | Phase 10 trigger returns FAILED `NO_PROVIDER_PAYLOAD` | the trigger still performs no ingestion; Phase 18 makes it call the real pipeline |
| R5 | Phase 16 status endpoints real | `/data-status`, `/model-status` hardcoded (N2, N4) |
| R6 | Phase 16 model health and drift real | Phase 11 drift monitor seeded; Phase 14 calibration feedback seeded |
| R7 | one Phase 17 readiness service | Phase 10 declared profiles, Phase 11 coverage manager and data-coverage routes still answer readiness separately |
| R8 | Phase 16 serving returns MODEL_UNAVAILABLE | `/api/v1/…/prediction` serves hand-typed weights (N3) |
| R9 | bearer auth on `/api/v1/ops` | `/api/auth/me` fake (N5); legacy routes unauthenticated (N8) |
| R10 | Phase 16 demo users not seeded in hardened environments | about 60 other seeds (N1) |
| R11 | Phase 16 capabilities UNVERIFIED | – |
| R12 | Phase 17 entities in PostgreSQL | Phase 10–16 engines are in-memory singletons |
| R13 | StatsBomb → Silver implemented | competitions / seasons / clubs / players / matches / lineups / events covered; unsupported fields not yet catalogued |
| R14 | `/data-ops` and `/model-ops` built | `/system-health` missing |
| R15 | Phase 16 tests corrected | – |
| R16 | integration fixture repaired | blocked by R22 |
| R17 | CORS allowlist | – |
| R18 | model left REGISTERED | no manifests, no reproduction script, no trained artifact |
| R19 | documented only | **32 drift operations** |
| R20 | – | N7 |
| R21 | documented only | dataset not labelled SOURCE_UNVERIFIED in code; valuation model lineage not marked |
| R22 | 5 integration tests failing | **open** |
| R23 | documented only | **open** |
| R24 | 500 → 404 only | **open** |

## 4. Dependency graph (runtime)

```
frontend (CRA, axios) ──► FastAPI app.main
                              ├─ routes_canonical ──► SQLAlchemy async ──► PostgreSQL (Silver/Gold)
                              ├─ routes_phase17 (/api/v1/ops) ──► PostgreSQL ops_* + Redis (rate limit)
                              ├─ routes_phase10…16 ──► module-level singletons (in-memory, seeded)  ◄─ N1
                              ├─ prediction.service ──► prediction.registry (in-memory)            ◄─ N3
                              ├─ market.ml.service ──► data/models/valuation (joblib + JSON)       ◄─ N6
                              └─ providers.* ──► httpx ──► egress proxy ──► StatsBomb / API-Football / football-data
Bronze: local filesystem data/bronze (content-addressed), S3/MinIO adapter (moto-tested only)
```

## 5. Data flow (real path as it exists)

`provider adapter (httpx)` → `LiveIngestionRunner.run_job` → contract check → `SnapshotStore.put` (SHA-256 content address) → `DataSnapshot` row (provider_retrieved_at, http_status, source_url) → `ops_job_runs` → StatsBomb transformers → Silver (`matches`, `match_lineups`, `match_events`, `players`, `clubs`) → `ops_quality_reports` → `feature_refresh` (`team_form_v1`) → `infer_match` (gated).

Bypasses of this path: the Phase 10–16 seeds (N1), `prediction.service` (N3), the open-transfers curation scripts (R21), and the recruitment defaults (R23).

## 6. Auth flow

- `/api/v1/ops/*`: `Authorization: Bearer <token>` → SHA-256 lookup in `ops_users` → organization, role, permission → per-resource checks (`load_project_for`). 404 for invisible resources.
- Everything else: **no authentication**. `/api/auth/me` is hardcoded (N5). Phase 12 and 14 identity comes from the request body (N8).

## 7. Model flow

| Model | Registry | Artifact | Training code | Reproducible | Serving |
|---|---|---|---|---|---|
| Match outcome | `prediction.registry` (in-memory, MODEL_VALIDATED by default) + `ops_model_registry` (REGISTERED, code digest) | none (hand-typed weights) | none | no | `/api/v1/prediction`, `/matches/{id}/prediction` serve it; `/api/v1/ops/inference` refuses it |
| Valuation | `data/models/valuation/registry_manifest.json` | joblib, present locally, path from another machine | `market/ml/pipeline.py` | dataset not in repo, provenance self-asserted (R21) | `/api/v1/market/*` valuation |
| Five others (`model_governance`) | hardcoded | none | none | no | reported as active |

## 8. Persistence map

| State | Store | Survives restart |
|---|---|---|
| Silver/Gold football data, snapshots, ingestion runs | PostgreSQL | yes |
| Ops users, orgs, projects, watchlists, alerts, notifications, decisions, audit, inference log, outcomes, model registry, job runs, probes, quality reports, incidents, field validation | PostgreSQL (`ops_*`, migration 0014) | yes |
| Rate-limit counters | Redis (process-local fallback) | Redis-dependent |
| Phase 10 projects, watchlists, scenarios, decisions; Phase 11–15 engines; Phase 16 jobs, alerts, freshness | process memory (+ seeds) | **no** |
| Bronze payloads | local filesystem (S3 adapter untested against a real store) | yes (disk) |

## 9. Unresolved risks entering implementation

1. Phase 10–15 engines are large (about 9,000 lines). Re-implementing them on real data is not possible inside this phase. The truthful option is to stop them inventing content: no seeds outside an explicit `DEV_SEED=true` development mode. They then return empty or `INSUFFICIENT_DATA` until real inputs exist.
2. Only one historical provider is reachable. Live-provider gates will stay `PROVIDER_BLOCKED`.
3. No deployment target. Deployment gates will be `DEPLOYMENT_UNVERIFIED`.
4. The frontend pages built on Phase 10–15 engines will show empty states once seeds stop. That is the truthful state, not a regression.
