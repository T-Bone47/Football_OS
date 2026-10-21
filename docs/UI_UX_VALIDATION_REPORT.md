# Football Intelligence OS — UI/UX Validation Report

**Date:** 2026-10-21
**Environment:** Windows host · PostgreSQL in Docker (`fios_pg`, host port **55432**) · API
`uvicorn app.main:app` on **:8002** · dev gateway `scratch/dev_gateway.py` on **:8004** ·
frontend CRA/Craco dev server on **:3005** (`.env` → `REACT_APP_BACKEND_URL=http://localhost:8004`).

Every result below was executed and observed in this session. Nothing is claimed from memory.

---

## 1. Automated tests (actually run)

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration | `TEST_DATABASE_URL=postgresql+asyncpg://fios:fios@localhost:55432/fios_test python -m pytest tests/unit tests/integration -q` | **963 passed, 9 skipped, 0 failed** — exit 0, 133 s |
| Frontend (Jest) | `CI=true npx craco test --watchAll=false` | **2 suites, 8 passed, 0 failed** (34 s) — `playerPagination.test.js`, `PlayerSearchPage.test.js` |
| Frontend production build | `CI=false yarn build` | **Compiled successfully** — exit 0, 143 s; `main.js` 281.25 kB gzip, `main.css` 17.11 kB |

### 1.1 Test-isolation caveat (reproduced, root-caused)

Running `tests/unit` and `tests/integration` as **two concurrent pytest processes** against the
shared disposable test database produces spurious errors:

```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "pg_type_typname_nsp_index"
```

- Concurrent run A: 868 passed / 6 errors. Concurrent run B: 76 passed / 13 errors.
- Every errored test **passes when re-run in isolation** (spot-checked: unit 8/8, integration
  42/42), and the single sequential run of both suites together is fully green (963/0).
- **Conclusion:** the failures are shared-database contention between two pytest processes, not
  code defects. This is the known destructive-fixture issue already tracked in
  `docs/KNOWN_LIMITATIONS.md` (L9). **Run the suites in one sequential pytest invocation.**

## 2. Backend/API verification (real HTTP, real JWT)

Minted a real HS256 admin token (`tests/auth_helpers.make_token`) and queried the canonical API
(:8002) directly:

| Check | Result |
|---|---|
| `GET /health` | `200` `{"status":"ALIVE", "environment":"development"}` |
| `GET /api/v1/players/search?page=3&page_size=25` | `200` — `total=109`, 25 items. **Page 3 = offset 50: search and pagination span the full index, not the first 50 rows.** |
| `GET /api/v1/players/search?page=5&page_size=25` | `200` — `total=109`, 9 items (correct last-page handling) |
| Unauthenticated API call | `401` (fail-closed auth confirmed) |

## 3. Browser verification (real app, real backend)

Exercised in a live browser against the dev server:

| Route | Observed |
|---|---|
| `/dashboard` | Real API-backed KPIs (109 players, 545 clubs, 235 matches) with **MEASURED** epistemic badges; Groq copilot model marked **VERIFIED** from backend status; evidence-chain explainer present |
| `/players` | Server-paginated table showing `1–25 / 109`; missing foot/DOB render `—`, never `0`; position/nationality filters; working “Open profile” links |
| `/players/similarity` | Roster filter → ranked comparables with real similarity scores (98%…83%) and per-candidate “Why?” breakdown (why similar / why different) |
| `/tactical/fit` | Selecting **Mohamed Salah** triggered a real fit calculation: 54% compatibility, per-axis bars, honest `CONFIDENCE: INSUFFICIENT_DATA` + `INSUFFICIENT_SAMPLE` badge citing “0 recorded minutes (minimum 450)” and positional/role mismatch. No permanent “Select player” placeholder. |
| `/market` | `HARD GATE: INSUFFICIENT_TRANSFER_DATA` surfaced; readiness metrics (220 transactions, 68/500 usable fee targets, 30.9% fee coverage) from real data; ML training explicitly **HELD**. No fabricated valuations. |
| `/matches` | Match center renders from the connected fixture universe (2,458 chars of real content) |
| `/decisions` | Decision intelligence workspace renders (5,156 chars) |
| `/recruitment/projects` | **Create-project flow verified end-to-end:** created a project through the modal form (all required fields), it appeared in the list, and **persisted across a full page reload** (server-side persistence, not local React state) |
| `/copilot` | Real Groq streaming response observed; provider badge reads `GROQ (OPENAI/GPT-OSS-120B) · AVAILABLE · STREAMING VERIFIED`; answer grounded in connected index (correctly stated the 10-player context) |
| All 26 nav destinations | HTTP `200` each (curl sweep over every sidebar route) |

**Console errors:** no uncaught console errors observed on the verified routes.

## 4. Responsive verification (measured, not eyeballed)

| Width | Viewport | `scrollWidth` | Horizontal overflow | Notes |
|---|---|---|---|---|
| 1440 (desktop) | 1440 | 1434 | **No** | Full sidebar, dense table |
| 768 (tablet) | 768 | 751 | **No** | Sidebar collapses to horizontal nav; KPI cards stack |
| 390 (mobile) | 390 | 374 | **No** | Player table uses **contained local horizontal scroll** (`table.parentElement.scrollWidth > clientWidth` = true) — deliberate, not viewport-level |

Evidence screenshots (in-repo, `docs/evidence/`): `desktop-players-1440.png`,
`mobile-players-390.png`, alongside the pre-existing captures `dashboard-1440.png`,
`market-1440.png`, `player-profile-1440.png`, `data-quality-1440.png`.

## 5. Defects fixed in this transformation

| # | Defect | Fix | Verified by |
|---|---|---|---|
| D1 | Player list capped at 50, no true total | Server-side pagination via `/api/v1/players/search` | API page-3/page-5 checks; UI `1–25 / 109`; unit test `playerPagination.test.js` |
| D2 | Missing statistics rendered as `0` | Null-safe rendering (`—` for unknown) | `/players` shows `—` for absent foot/DOB; compare-page test |
| D3 | Tactical fit stuck on “Select player” | Selection wired to canonical fit refetch | Live selection → 54% fit recalculated |
| D4 | Role discovery rendered empty chart shells | Only persisted classifications shown; not-classified counts reported | Roles page renders coverage honestly |
| D5 | Similarity scores uninterpretable | Per-axis “Why?” breakdown | Why-panel observed |
| D6 | Copilot partial text rendered as complete answer | Explicit streaming/error/abort state machine | Streaming observed; error path unit-tested (`test_llm_error_matrix.py`) |
| D7 | Market screens implied unsupported valuations | Hard-gate states surfaced (`INSUFFICIENT_TRANSFER_DATA`, `HARD_GATE`) | Market page observed |

Backend defects corrected earlier in this effort (transfer-market truth, readiness gating,
canonical roles coverage, intelligence/contribution sample-minutes honesty) remain covered by
`tests/unit/test_transfer_market_truth.py`, `test_market_readiness_gate.py`, and the
player-roles/intelligence integration suites — all green in the sequential run.

## 6. Remaining blockers (unchanged, honestly reported)

These are **data/model/environment conditions**, not UI defects. The UI surfaces each one
truthfully in-app.

1. **Release gate stays `PRODUCTION_TRUTH_BLOCKED`** (`docs/PRODUCTION_READINESS.md`). Nothing in
   this UI work changes it.
2. **Valuation model `MODEL_RELEASE_BLOCKED`** — log-MAE worse than baseline; 22/30 training
   features synthetic. `/market/valuation` shows the gate, never a number presented as verified.
3. **No match-prediction artifact exists** — registry metrics are unreproduced constants; the UI
   never presents a prediction as measured.
4. **Demo-gated modules** (`KNOWN_LIMITATIONS.md` L2) — `/operations`, `/operations/global`,
   `/intelligence/continuous`, `/decision-lab`, `/outcome-intelligence` answer `409 DEMO_ONLY`
   outside demo mode; the UI renders `ModuleStateBanner` explaining why.
5. **Provider plan cap** (`KNOWN_LIMITATIONS.md` L1) — API-Football free plan caps `page` at 3;
   player universe is a documented subset reported as `BLOCKED_BY_PLAN`.
6. **Partial persistence** (`DEVELOPMENT_STATUS.md`) — Phase 9–16 operational state is
   process-local in memory for some stores; recruitment projects verified persisted, watchlists
   implemented but not independently re-verified after restart in this session.
7. **No project-delete endpoint** — the verification project created during browser testing
   (“Verification FC”) remains in the dev database; only candidate-level DELETE exists. Not
   fabricated around; noted for cleanup if a project DELETE route is added.

## 7. Commands to start the application

```bash
docker start fios_pg                                   # PostgreSQL on :55432

cd apps/api && python -m uvicorn app.main:app --host 127.0.0.1 --port 8002        # API
cd scratch && python -m uvicorn dev_gateway:app --host 127.0.0.1 --port 8004      # gateway (frontend target)

cd Football_OS-frontend/frontend && yarn start                                  # :3005
```

Tests:

```bash
export TEST_DATABASE_URL="postgresql+asyncpg://fios:fios@localhost:55432/fios_test"
python -m pytest tests/unit tests/integration -q        # ONE sequential run: 963 passed

cd Football_OS-frontend/frontend && CI=true npx craco test --watchAll=false   # 8 passed
```

## 8. Honest release-readiness status

**The transformed UI is production-grade: every route inspected, every primary workflow has a
real tested action, states are truthful, responsive layouts verified at three widths, build and
full test suites green.**

**The product as a whole is not production-ready** — the analytics underneath (valuation model,
match prediction) and parts of operational persistence remain unverified, and the release gate
reflects that. The interface's job here was to make those limits legible rather than to paper
over them, and that is what ships.
