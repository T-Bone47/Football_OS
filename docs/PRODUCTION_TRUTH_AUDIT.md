# Production Truth Audit & Remediation Register

Audit date: 2026-10-11 · Baseline: `Football_OS-main.zip` as uploaded (no `.git`; a local baseline commit `d131953` was created so every change is diffable) · Handoff: `FOOTBALL_INTELLIGENCE_OS_CLAUDE_HANDOFF.md`

This file is the verified-evidence companion to `docs/DEVELOPMENT_STATUS.md`. The handoff's findings were treated as claims and re-checked against the code; several were worse than reported, one did not reproduce, and some defects the handoff did not list were found.

## 1. Evidence tiers (read this before trusting any "fixed")

| Tier | Meaning |
|---|---|
| **EXECUTED** | Ran in the audit sandbox using a *local stand-in* for `pytest` (and, for 3 files, a minimal `pydantic` stub). Verifies logic and control flow. **Not** a real-pytest result: re-run under real pytest. |
| **STATIC** | Verified by AST/grep, `py_compile`, or the TypeScript compiler (JSX syntax only). Not executed. |
| **UNVERIFIED** | Written but cannot run in the sandbox (needs PostgreSQL, FastAPI, SQLAlchemy, pydantic, lightgbm, Docker, `node_modules`, network). Treat as untested code. |

Sandbox limits (all verified): Python 3.12 with numpy/pandas/scikit-learn/scipy/PyJWT only; **no** pytest, FastAPI, pydantic, SQLAlchemy, Alembic, lightgbm, PostgreSQL, Docker, `node_modules`, or network (pip/npm cannot install). Consequently **the repository's own 600+ test suite was not run**, and the `564 passed` / `608 passed` claims remain unreproduced. Only 16 of the 84 original test files import in the sandbox (the rest need FastAPI, SQLAlchemy, pytest fixtures or PostgreSQL).

### Executed results (stand-in runner; same files, original vs current)

| | passed | failed | skipped |
|---|---|---|---|
| Original code (files that import in the sandbox) | 169 | 27 | 0 |
| Current code (same files + new regression tests) | 299 | 25 | 4 |

No pre-existing file lost a passing test. All 25 remaining failures are sandbox limits (missing `fastapi`/`starlette`/`sqlalchemy`, a custom fixture the stand-in cannot run) and are present in the baseline except 2 runtime tests in `test_route_protection.py` that need Starlette. Red/green evidence: the new guards were run against the **original** code and fail there (fabricating ingestion module, unauthenticated routers, zero-fill in the valuation service, unpinned/over-claimed manifest).

## 2. Repository facts

- No `.git` in the archive; branch, commits and dirty state are unverifiable. `FOOTBALL_INTELLIGENCE_OS_ARCHITECTURE.md` (called the "source of truth" by the README) is **not in the archive**; ADRs are in `docs/ARCHITECTURE_DECISIONS.md`.
- 249 Python modules under `apps/api`; 227 routes at baseline, none of which verified an identity (7 consumed a caller-supplied `user_id`); 13 Alembic migrations (0001–0013); 36 module-level in-memory singletons hold all Phase 9–16 operational state.
- Two backends: `apps/api` (FastAPI + PostgreSQL) and `Football_OS-frontend/backend` (FastAPI + MongoDB: Google sign-in sessions, shortlists, LLM copilot). They define overlapping routes (`/api/auth/*`, `/api/copilot/query`, `/api/status`) and no gateway configuration exists in the repo.
- `data/bronze` is gitignored and absent. The only trained artifact is the valuation LightGBM model (`val_lightgbm_20260920.joblib`, SHA-256 `288f662f…c821`; `active_model.joblib` was a byte-identical duplicate and was removed). **There is no match-prediction artifact.**

## 3. Handoff findings: verification and status

Severity: C critical, H high, M medium, L low. "Status" is after this pass.

| ID | Sev | Verified finding | Status | Tier |
|---|---|---|---|---|
| R1 | M | Confirmed. 6 tests need untracked `data/bronze` (4 in the `test_phase9_validation` coverage audit; 2 through one `sample_payload` fixture in `test_transfer_normalization`) and fail on a clean checkout. `moto`/`python-dotenv` were undeclared. | Fixed: explicit skip with reason + synthetic-fixture tests of the same audit code. | EXECUTED |
| R2 | M | Confirmed. `requirements.txt` lacked numpy, joblib, greenlet, PyJWT, moto, python-dotenv; pytest was a runtime dep. | Fixed: `requirements.txt` + `requirements-dev.txt`. **Open:** no lock file (needs network: `pip-compile`). | STATIC |
| R3 | M | **Not reproduced as described.** `env.py` already mapped `+asyncpg` to a bare `postgresql://` (psycopg2, which is declared). But `env.py` imported only `provenance`, so `alembic check`/autogenerate was blind to `canonical`/`capability`. | Hardened: explicit `postgresql+psycopg2` / `+asyncpg` helpers (`app/db/urls.py`) used by app and Alembic; all models imported. **Open:** clean `alembic upgrade head` on empty Postgres. | EXECUTED (helpers) / UNVERIFIED (migration) |
| R4 | C | Confirmed and worse. With no payload the "cycle" invented an Arsenal 2–1 Chelsea fixture, wrote it to `data/bronze/` as a provider snapshot and marked 8 stages complete that never ran. The trigger accepted a caller-supplied `payload` (unauthenticated Bronze injection) and used request `provider`/`resource` as directory names (path traversal). | Fixed: pipeline deleted; trigger delegates to the real `IngestionService`; per-stage truth (`COMPLETED`/`FAILED`/`NOT_EXECUTED`); downstream stages are never reported complete; scalar-only params; storage path-segment guard. | EXECUTED (view, guards) / UNVERIFIED (route+DB) |
| R5/R6 | H | Confirmed. `/health` and `/data-status` returned hardcoded `HEALTHY`/`FRESH`/`zero_fabrication_policy: ENFORCED`; Phase 16 returned latency 1.2 ms, cache hit-ratio 0.84, 4 workers (no Redis or worker pool exists in the code), 1,420 predictions, PSI 0.038, a fixed timestamp. | Fixed: values are measured or `null`/`UNKNOWN`/`NOT_CONFIGURED`; liveness (`ALIVE`) is separate from readiness; readiness without a session is `UNKNOWN`, not `READY`. | EXECUTED (status logic) / UNVERIFIED (DB probes) |
| R7 | H | Confirmed in four places: Phase 10 manager (EPL "760 matches, PRODUCTION_READY, log loss 0.9418"; La Liga valuation `MODEL_VALIDATED`), Phase 16 `/data/readiness`, Phase 16 copilot ("4 of 5 competitions certified"), Phase 12 discovery. | Fixed in Phase 10, Phase 16 endpoint and copilot (`NOT_ASSESSED`, counts `None`). **Open:** `phase12/recruitment_discovery.py` (lines ~35, ~109) still hardcodes `PRODUCTION_READY`; no evidence-derived assessor exists. | EXECUTED (Phase 10) |
| R8/R20 | C | Confirmed. Serving seeded two fictional models (a shadow "v2" with no artifact) and returned `base_metric * 1.05`; seeded profile metadata contradicted the manifest; the manifest pinned no hash and stored `C:\Users\…` as the artifact path. | Fixed: serves only the registry's active, SHA-256-verified, `MODEL_VALIDATED` artifact, strict feature schema, declared-competition check, sufficiency gate; otherwise a coded refusal. Hash pinned; path portable; hash verified **before** `joblib.load` (pickle executes code). | EXECUTED (control flow, fake registry) / UNVERIFIED (real artifact load) |
| R9/R10 | C | Confirmed. `/api/auth/me` returned a fake `scout_01` to everyone; no route verified an identity (7 of 227 consumed a caller-supplied `user_id`); model promotion trusted `user_id: "admin_01"` from the request body; projects/watchlists listed by caller-supplied `org_id`/`user_id` (a missing filter returned everyone's); client-chosen ids overwrote existing objects. | Fixed (main API): every router requires a verified HS256 bearer token; only `/health`, `/readiness`, `/health/ready`, `/api/status` are public; permission checks from the token; Phase 16 projects org-scoped, watchlists owner-only (404 not 403), duplicates 409; audit log admin-only. Identity service: sign-in allowlist (fail closed) + `POST /api/auth/token`. **Open:** Phase 10 registries are authenticated-only (no per-object ownership); no token revocation; end-to-end login → token → API flow untested. | EXECUTED (token/ownership/contract) / STATIC (wiring) / UNVERIFIED (HTTP) |
| R11/R13 | H | Not addressed. Provider capability profiles are seeded in `phase16/provider_orchestrator.py`; no StatsBomb Bronze→Silver path was built. | **Open.** (Real `IngestionService` fixed, see N6.) | — |
| R12 | H | Confirmed (36 singletons; migrations stop at 0013). | **Open.** Needs PostgreSQL to implement and prove restart persistence. Responses now label `PROCESS_LOCAL_IN_MEMORY`. | STATIC |
| R14 | L | **Not reproduced** for navigation: every Sidebar/CommandPalette target exists in `App.js`. Separate verified defect: 6 frontend calls have no backend route (fixed: Operations `model-lifecycle`; open: 4 under `/api/phase11/…`, `/api/v1/outcomes` — static match, confirm at runtime). | Partly fixed. | STATIC |
| R15/R16 | M | Not examined in depth. | **Open.** | — |
| R17 | H | Confirmed in **both** backends (`*` with credentials; identity backend used an allow-all regex). | Fixed: explicit origins from settings; a wildcard is a startup error; methods/headers whitelisted. | EXECUTED (parser) / STATIC (wiring) |
| R18 | H | Confirmed unverifiable: no match-prediction artifact; `app/prediction/registry.py` hand-types metrics and defaults `temporal_validation_passed`/`leakage_tests_passed` to `True`; tests assert those constants. | **Open.** The governance registry no longer asserts them and Phase 16 serving refuses non-valuation domains. | STATIC |
| R19 | M | Not measured (needs a real database). | CI now runs `alembic upgrade head` + `alembic check` (with `compare_type`). **Open:** read the drift it reports and fix by migration 0014. | UNVERIFIED |
| R21 | H | Confirmed unverifiable: training transfers are hand-authored Python literals (`tools/curate_open_transfers*.py`, ~178 KB) with synthetic ids, an asserted licence and a constructed source URL, no per-record citations. | Valuation artifact flagged `training_data_provenance: UNVERIFIED` (release-gate FAIL). **Open:** rebuild from verifiable sources. | STATIC |
| R22/R23 | H | Confirmed. Phase 10 `CandidateAddRequest` invents age 24, €25M, fit 80, contribution 75, risk 0.30; the manager uses `.get(…, 20_000_000.0)`, and unknown risk becomes `0.0`, which then reports `tolerance_met: True`. | **Open** for Phase 10 recruitment/reports. Fixed for the ML valuation path (N2). | STATIC |
| R24 | H | Confirmed: seeded Arsenal roster (`phase13/squad_baseline.py`), seeded "verified" outcomes (`phase14`), seeded `proj_cb_summer_2027` (`phase10`). | **Open.** (Phase 16 project/user/watchlist seeds removed.) | STATIC |

## 4. Additional findings (not in the handoff)

| ID | Sev | Finding | Status |
|---|---|---|---|
| N1 | **C** | **The valuation model's training features are synthetic.** In `market/ml/dataset.py`, 22 of the 30 model features are position constants (`rating 7.05` for every midfielder), age proxies (`minutes = age × 95`) or literals (`starter_ratio 0.85`); only 8 carry information (age, age curve, position, tier weight, 4 market-cohort statistics). The model is a function of age, position and trailing market medians, not performance; its SHAP attributions on those columns are artifacts. (AST-verified; `tests/unit/test_feature_provenance.py` keeps the declaration in sync.) | Declared in `feature_provenance.py`; release gate fails it. **Open:** retrain on real point-in-time features. |
| N2 | **C** | **The production valuation service fabricated model inputs** (`rating 7.15`, goals/90 by position, `club_tier 1.0`, cohort medians €25M/€18M, 365 days since transfer…) and 23 of the 30 model feature names were absent from its dict, so `.get(name, 0.0)` silently zero-filled them. The sufficiency gate saw `null_count = 0`. It also read attributes that do not exist on `MarketContextResponse`. | Fixed: real values only; missing → NaN, counted, gate refuses. The valuation endpoint therefore reports `INSUFFICIENT_DATA` until real features are wired (**open**, shared train/serve builder). |
| N3 | H | The release gate hard-coded 7 of 10 checks `True` and compared MAE only. Re-measured on the artifact's own recorded results it fails: test log-MAE 0.4914 vs baseline 0.4907, test R² −0.0904, 80% intervals cover 23.8% of >70M transfers (n=21). `MODEL_VALIDATED` was false. | Fixed: measured gate (`release_gate.py`); manifest status `MODEL_RELEASE_BLOCKED` with reasons. |
| N4 | H | Artifact loaded with `joblib.load` and no integrity check. | Fixed (hash pinned and verified first; ids validated against path traversal). |
| N5 | H | Governance registry: all five "models" `MODEL_VALIDATED` with hand-typed metrics; the valuation record used **train** metrics; the "artifact hash" was SHA-256 of a spec *string*. | Fixed: derived from the manifest; others `MODEL_UNVALIDATED`. |
| N6 | H | `IngestionService` marked schema-**INVALID** snapshots `SUCCESS`, set `record_count = 1` unconditionally and recorded capability evidence for invalid payloads. | Fixed (`PARTIAL`, `NULL`, no evidence). |
| N7 | M | Operations UI always showed a green "Cycle Complete", swallowed errors, and called a non-existent endpoint (one 404 emptied the whole page). | Fixed; JSX syntax-checked only. |
| N8 | M | Frontend `getCurrentUser()` fabricated `scout_01` on any error (dead code). | Removed. |
| N9 | M | Copilot SSE (both backends) returned `str(exc)`; `/health/ready` echoed exception text (can embed the DSN); `/health` exposed pid/memory. | Fixed. |
| N10 | M | Identity service: any Google account could sign in; wildcard CORS regex with credentials. | Fixed (allowlist, explicit CORS). |
| N11 | L | Phase 9 coverage audit sets `provenance_completeness=1.0`, `missingness_rate=0.0`, `VALIDATED` whenever a file has records (constants). | **Open.** |
| N12 | L | `ContinuousIntelligencePage` turns non-OK responses into empty lists (hides failures); two env names for the backend URL with localhost fallbacks. | **Open.** |
| N13 | L | `setup_pg.sh` opens Postgres to all hosts and creates a SUPERUSER with a trivial password (dev only). | **Open** (document/remove). |
| N14 | L | `/api/v1/ingestion/runs` forwards arbitrary `params` into provider URL templates. | **Open.** |
| N15 | M | `predict_player`/comparables return `0.0` (not `None`) for unknown values; callers must read `data_status`. | **Open.** |
| N16 | M | Two backends with overlapping routes and different persistence (MongoDB shortlists vs "PostgreSQL is the source of truth"); needs an ADR and a gateway. | **Open.** |
| N17 | L | Docs drift: `DEVELOPMENT_STATUS.md` stops at Phase 2 while the README claimed Phase 15. | Header corrected; historical sections kept. |

## 5. What changed (by stage)

**Stage 1: foundation.** `requirements.txt` split + `requirements-dev.txt`; `app/db/urls.py` (explicit drivers) used by `session.py` and `env.py`; `env.py` imports all models; `conftest.py` sets `AUTH_JWT_SECRET` and runs functional API tests as an authenticated admin via FastAPI's dependency override (tests of authentication carry `@pytest.mark.real_auth` and mint real tokens, `tests/auth_helpers.py`); CI now migrates an empty DB, runs `alembic check` and `pytest`, and builds the frontend.

**Stage 2: fabricated behaviour removed.** Phase 10 ingestion; health/readiness/data-status; Phase 16 operations/health/readiness/models/drift/copilot; governance registry; Phase 10 readiness; ingestion-service truth; valuation service inputs.

**Stage 4: security.** `app/security/` (tokens, permissions, deps, CORS); router-level authentication; Phase 16 org/owner scoping; identity service allowlist + token endpoint; frontend bearer-token plumbing (axios + fetch, in memory only).

**Stage 5: model serving.** `artifact_integrity.py`, `release_gate.py`, `feature_provenance.py`, hash-verified registry, truthful serving engine, manifest re-measured and pinned.

### Existing tests changed, and why

Each replaced test asserted a fabricated value; each replacement is at least as demanding and asserts the truthful behaviour. Nothing was deleted without a replacement.

| Test | Asserted (fabricated) | Now asserts |
|---|---|---|
| `test_phase10_operations::TestOperationalIngestion` (3) | a fake cycle "completes all 11 stages" with `records_accepted > 0` | moved to `test_phase10_ingestion_truth.py` (18 tests) |
| `test_phase10_operations::TestCompetitionReadiness` (2) | EPL `PRODUCTION_READY`, 760 matches; La Liga valuation `MODEL_VALIDATED` | everything `NOT_ASSESSED`, counts `None`, no engine authorized |
| `test_observability` governance + health (5) | `HEALTHY`/`READY` without a session/`MODEL_VALIDATED` seeds/`zero_fabrication_policy` | measured/`UNKNOWN`; unvalidated models are blocked; hash required for `MODEL_VALIDATED` |
| `test_phase8_e2e_workflows` Workflow D step 1 | `BivariatePoisson_v1` is `MODEL_VALIDATED` with `log_loss` | blocked, `MODEL_UNVALIDATED`, no metrics |
| `test_phase9_validation` manifest test | `status == "MODEL_VALIDATED"` | honest status + pinned hash (consistency with the gate is in `test_release_gate.py`) |
| `test_phase16_production_platform` (12 tests) | seeded users, fictional models, `base_metric*1.05`, `HEALTHY`, `LIVE_TELEMETRY`, body-supplied `user_id` | principal-based RBAC, refusal paths, `real_auth` HTTP tests (401/403/409) |
| `integration/test_ingestion_lifecycle` | `record_count == 1` | `record_count is None` |

## 6. Open backlog (priority order)

1. **Run the real suite** on a machine with PostgreSQL (commands below) and fix whatever the blind edits broke. Highest-risk unexecuted edits: `routes_phase10.py` (DB queries), `routes_phase16.py`, `system_health.py` SQL, `main.py`, the rewritten Phase 16 tests.
2. **Valuation model (N1/N2/R21):** build point-in-time features from real match data with one builder shared by training and serving; rebuild the transfer dataset from verifiable sources with an immutable manifest (rows, coverage, checksum); retrain; re-run the gate; only then declare `supported_competitions`.
3. **Persistence (R12):** migration 0014+ for users/orgs/projects/watchlists/ingestion cycles/decisions/alerts/audit; repository layer; restart-persistence integration tests.
4. **Authorization depth:** per-object ownership in Phase 10 registries; token revocation/refresh policy; admin-managed roles in the identity service.
5. **Provider truth and StatsBomb Bronze→Silver (R11/R13)**, evidence-derived competition readiness (R7), Phase 12 hardcodes, Phase 9 coverage constants (N11).
6. Remove invented defaults/seeds in Phase 10 recruitment, Phase 13 squads, Phase 14 outcomes (R22–R24).
7. Schema drift (R19), lock file (R2), gateway/ADR for the two backends (N16), UI error handling (N12).

## 7. Reproduce and verify (on a machine with network and PostgreSQL 16)

```bash
pip install -r requirements-dev.txt
export AUTH_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL=postgresql+asyncpg://fios:fios@localhost:5432/fios_test
export TEST_DATABASE_URL=$DATABASE_URL
alembic upgrade head && alembic check      # R3 / R19
pytest -v                                  # record the REAL count in DEVELOPMENT_STATUS.md
(cd Football_OS-frontend/frontend && yarn install --frozen-lockfile && yarn build)
python - <<'PY'                            # artifact integrity, independent of any test
import hashlib, json
m = json.load(open("data/models/valuation/registry_manifest.json")); e = m["models"][m["active_model_id"]]
print(e["status"], hashlib.sha256(open(f"data/models/valuation/{e['model_id']}.joblib","rb").read()).hexdigest() == e["artifact_sha256"])
PY
```

Identity service (`Football_OS-frontend/backend`) needs `AUTH_JWT_SECRET` (same value), `AUTH_ALLOWED_EMAILS` and/or `AUTH_ALLOWED_EMAIL_DOMAINS` (empty = nobody can sign in), optional `AUTH_DEFAULT_ROLE` (default `viewer`), and `CORS_ORIGINS` as explicit origins. A gateway must route `/api/auth/*` and `/api/shortlists*` to it and the rest to `apps/api`.
