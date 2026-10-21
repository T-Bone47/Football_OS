# Football Intelligence OS — UI/UX Transformation Plan

**Date:** 2026-10-21
**Status:** Implemented and verified in this checkout (see `UI_UX_VALIDATION_REPORT.md` for evidence).
**Scope:** Transform the existing React 19 + FastAPI/PostgreSQL Football Intelligence OS into a
premium, cohesive, evidence-driven scouting workstation — in the real repository, without
replacing the stack or fabricating data.

> This plan is the source of truth for *what was intended and why*. The route-by-route result is
> `UI_UX_ROUTE_ACCEPTANCE_MATRIX.md`; the visual language is `UI_UX_DESIGN_SYSTEM.md`; the
> executed checks and honest blockers are `UI_UX_VALIDATION_REPORT.md`. It does **not** contradict
> `DEVELOPMENT_STATUS.md`, `KNOWN_LIMITATIONS.md`, or `PRODUCTION_READINESS.md` — where this
> document and those disagree on *readiness*, those documents win.

---

## 1. Baseline audit (what we found before changing anything)

### 1.1 Architecture baseline (unchanged)

The transformation **kept the installed stack**. No framework swap, no new charting library, no
package-manager change, no lockfile regeneration.

```
React 19 SPA (CRA + Craco, Tailwind + Radix + Recharts + Lucide)
        │  Axios/fetch via src/lib/footballApi.js (single API layer)
        ▼
FastAPI (canonical /api/v1/* + phase routers)  —  dev gateway :8004 → API :8002
        ▼
SQLAlchemy 2.0 async + PostgreSQL (18 Alembic migrations)
```

- **Frontend:** `Football_OS-frontend/frontend` (React 19, react-router v7, TanStack Query,
  Radix UI, Recharts, Tailwind, Lucide).
- **API:** `apps/api` — FastAPI, Pydantic V2, async SQLAlchemy; served by `app.main` on **:8002**.
- **Dev gateway:** `scratch/dev_gateway.py` on **:8004** — a thin reverse proxy implementing the
  ownership table in `docs/ADR-0004-backend-ownership-and-gateway.md`. It is *not* a second
  backend; it forwards to :8002.
- **Auth:** bearer-JWT on every router, fail-closed when `AUTH_JWT_SECRET` is unset; identity
  service mints short-lived tokens. Tokens are held **in memory only** (never localStorage).

### 1.2 Route inventory

`App.js` declares **41 routes** (26 distinct navigation destinations plus nested parameter and
variant routes). The sidebar exposes 26; the remainder are nested detail/variant routes reached
from those (player profile, match detail, shortlist detail, market/decision/research/squad
variants). Full list: `UI_UX_ROUTE_ACCEPTANCE_MATRIX.md` §1.

### 1.3 Verified defects found in the audit (fixed in this effort)

| # | Defect | Root cause | Fix |
|---|---|---|---|
| D1 | Player list capped at 50 with no true total | Client-side slice; server total ignored | Server-side pagination via `/api/v1/players/search`; UI shows `1–25 / 109` and real page math |
| D2 | Missing statistics rendered as `0` | Falsy-coalescing (`value \|\| 0`) | Null-safe rendering; unknown → `—`, `0` reserved for observed zeros |
| D3 | Tactical fit stuck on “Select player” after selection | Selection not wired to refetch | Selection triggers canonical fit call; recalculation verified live |
| D4 | Role discovery showed chart shells with no data | Rendered regardless of classification coverage | Renders only persisted classifications; reports not-classified/insufficient counts |
| D5 | Similarity used uninterpretable scores | No per-axis breakdown surfaced | Ranked comparables with real score + “Why?” axis breakdown (why similar / why different) |
| D6 | Copilot rendered partial text as a complete answer | No stream/error state machine | Explicit streaming state, abort, error surfaces; provider status read from backend |
| D7 | Market screens implied valuations the data cannot support | Missing hard-gate surfacing | `INSUFFICIENT_TRANSFER_DATA` / `HARD_GATE` states surfaced truthfully |

### 1.4 Data-availability root causes (not styling problems)

Per the evidence-first rule, insufficient-data states were traced to root cause before any UI
work. The dominant causes in this deployment:

- **Provider plan cap** (`KNOWN_LIMITATIONS.md` L1): API-Football free plan caps `page` at 3, so
  the player universe is a documented subset. Coverage is reported as `BLOCKED_BY_PLAN`, not
  hidden.
- **Demo-gated modules** (`KNOWN_LIMITATIONS.md` L2): four Phase 11–14 routers answer
  `409 {"code":"DEMO_ONLY"}` outside demo mode. The UI shows a truthful module-state banner
  (`ModuleStateBanner.js`) instead of a blank screen.
- **Genuine sample-size gates:** <600 minutes → `INSUFFICIENT_SAMPLE`; uncalibrated valuation →
  `MODEL_UNCALIBRATED` / `MODEL_RELEASE_BLOCKED`.

---

## 2. Design direction

### 2.1 Principles

1. **The AI is the interface; the data, models, and provenance are the product.** Every screen
   exposes its evidence, not just a conclusion.
2. **Zero fabrication.** No invented stats, fees, scores, or provider-health claims. Unknowns
   stay unknown (`—`), never `0`.
3. **Epistemic labels are first-class.** `MEASURED`, `MODELLED`, `OBSERVED`, `INSUFFICIENT_DATA`,
   `OUT_OF_DISTRIBUTION`, `MODEL_UNCALIBRATED` are rendered, not suppressed.
4. **Every interactive control does real work.** No dead buttons, fake toggles, or placeholder
   search fields.
5. **Restraint.** Dark operations aesthetic, semantic colour, tabular numerals, no decorative
   neon/gradient/glass clutter.

### 2.2 Architecture decisions

- **Single API layer preserved.** All screens keep going through `src/lib/footballApi.js`;
  no screen calls a competing endpoint.
- **Shared components extracted from real reuse**, not a speculative framework: `AppShell`,
  `Sidebar`, `CommandPalette`, `ModuleStateBanner`, `EvidenceDrawer`, `AddToShortlistButton`,
  `PerformanceRadar`, `PitchHeatmap`, plus the Radix `ui/*` primitives.
- **Server-side pagination** for the player universe (`lib/playerPagination.js` + unit test);
  the browser never fetches the whole index to filter locally.
- **Route-level state honesty:** loading / empty / error / partial / demo-gated are explicit on
  every data screen.

---

## 3. Phases (as executed)

| Phase | Focus | State |
|---|---|---|
| 1 | Baseline & architecture: inventory, build/test baseline, contract trace | Done |
| 2 | Design foundation: tokens, typography, shell refactor | Done (`UI_UX_DESIGN_SYSTEM.md`) |
| 3 | Shared data components: tables, pagination, filters, status/evidence panels, states | Done |
| 4 | Intelligence workspaces: players, profile, comparison, similarity, roles, tactical fit, dashboard | Done |
| 5 | Recruitment & decision: projects, watchlists, decisions, market, opportunities, replacements, risk, squad | Done |
| 6 | Match intelligence & Copilot: match routes, provider status, streaming, provenance | Done |
| 7 | End-to-end verification: tests, browser, responsive, reconcile inventory | Done (`UI_UX_VALIDATION_REPORT.md`) |

---

## 4. What this plan explicitly does NOT claim

- It does **not** change the release gate. `PRODUCTION_READINESS.md` remains
  `PRODUCTION_TRUTH_BLOCKED` because valuation/match-prediction models are not verified and much
  operational state is still process-local. A premium UI does not lift a data/model blocker.
- It does **not** claim live data. Historical/periodic datasets are never labelled “live”.
- It does **not** claim the demo-gated Phase 11–14 modules work on canonical data.

## 5. How to run

```bash
# Postgres (dev) — repo .env points at localhost:55432
docker start fios_pg

# API (:8002)
cd apps/api        && python -m uvicorn app.main:app --host 127.0.0.1 --port 8002

# Dev gateway (:8004) — what the frontend talks to
cd scratch         && python -m uvicorn dev_gateway:app --host 127.0.0.1 --port 8004

# Frontend (:3005)
cd Football_OS-frontend/frontend && yarn start
```

Backend tests need `TEST_DATABASE_URL=postgresql+asyncpg://fios:fios@localhost:55432/fios_test`.
Run unit and integration **in one sequential pytest process**; two concurrent processes contend on
the shared test database (see `UI_UX_VALIDATION_REPORT.md` §3).
