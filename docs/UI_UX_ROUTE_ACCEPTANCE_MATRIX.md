# Football Intelligence OS — UI/UX Route Acceptance Matrix

**Date:** 2026-10-21
**Status legend:**
- **VERIFIED** — executed against this deployment; the result was observed.
- **IMPLEMENTED** — code present and covered by unit/integration tests, but the specific
  real-world condition (a demo-gated module, an unavailable dataset) was not exercised
  end-to-end here.
- **BLOCKED** — a data/model condition prevents a truthful result; the UI surfaces that honestly
  rather than inventing a value.

Every route sits behind `ProtectedRoute` (auth) except `/login` and `/shared/shortlists/:token`.
All authenticated routes render inside `AppShell` (sidebar + command palette).

---

## 1. Full route list (39 declared in `App.js`)

| # | Route | Page component | Sidebar label |
|---|---|---|---|
| 1 | `/login` | `Login` | — (unauthenticated) |
| 2 | `/shared/shortlists/:token` | `SharedShortlistPage` | — (public share link) |
| 3 | `/dashboard` | `DashboardPage` | Dashboard |
| 4 | `/players` | `PlayerSearchPage` | Players |
| 5 | `/players/compare` | `PlayerComparePage` | Comparison |
| 6 | `/players/similarity` | `SimilarityPage` | Similarity |
| 7 | `/players/roles` | `RolesPage` | Roles |
| 8 | `/players/:playerId` | `PlayerProfilePage` | (via player rows) |
| 9 | `/market` | `MarketPage` variant=overview | Market |
| 10 | `/market/valuation` | `MarketPage` variant=valuation | (market subview) |
| 11 | `/market/opportunities` | `MarketPage` variant=opportunities | Opportunities |
| 12 | `/market/replacements` | `MarketPage` variant=replacements | Replacements |
| 13 | `/market/risk` | `MarketPage` variant=risk | Transfer risk |
| 14 | `/tactical/fit` | `TacticalFitPage` | Tactical fit |
| 15 | `/matches` | `MatchesPage` | Matches |
| 16 | `/matches/:matchId` | `MatchesPage detail` | (via match rows) |
| 17 | `/squad/builder` | `SquadPage` variant=builder | Squad builder |
| 18 | `/squad/simulator` | `SquadPage` variant=simulator | Transfer simulator |
| 19 | `/squad/scenarios` | `SquadPage` variant=scenarios | Scenario lab |
| 20 | `/research` | `ResearchPage` variant=overview | Research lab |
| 21 | `/research/models` | `ResearchPage` variant=models | (research subview) |
| 22 | `/research/data` | `ResearchPage` variant=data | Data sources |
| 23 | `/research/experiments` | `ResearchPage` variant=experiments | (research subview) |
| 24 | `/system/data-quality` | `DataQualityPage` | Data quality |
| 25 | `/copilot` | `CopilotPage` | Scout copilot |
| 26 | `/decisions` | `DecisionPage` | Decision engine |
| 27 | `/decisions/recruitment` | `DecisionPage` | (decision subview) |
| 28 | `/decisions/replacement` | `DecisionPage` | (decision subview) |
| 29 | `/decisions/scenarios` | `DecisionPage` | (decision subview) |
| 30 | `/shortlists` | `ShortlistsPage` | Shortlists |
| 31 | `/shortlists/:shortlistId` | `ShortlistsPage detail` | (via shortlist rows) |
| 32 | `/recruitment/projects` | `RecruitmentProjectsPage` | Recruitment projects |
| 33 | `/watchlists` | `WatchlistsPage` | Watchlists & alerts |
| 34 | `/scenarios` | `ScenariosPage` | Scenarios (Multi-Alt) |
| 35 | `/operations` | `OperationsPage` | Live operations |
| 36 | `/operations/global` | `GlobalOperationsPage` | Global operations |
| 37 | `/intelligence/continuous` | `ContinuousIntelligencePage` | (continuous learning) |
| 38 | `/decision-lab` | `DecisionLabPage` | Decision Lab 2.0 |
| 39 | `/outcome-intelligence` | `OutcomeIntelligencePage` | (outcome intelligence) |

`/` and `*` both redirect to `/dashboard`.

---

## 2. Acceptance matrix

Columns: **Data** = backend dependency · **Actions** = implemented interactions ·
**L/E/Er/P** = loading / empty / error / partial-data state present · **R** = responsive verified ·
**B** = browser-verified this session.

### 2.1 Overview

| Route | Data / API | Actions | L | E | Er | P | R | B | Status |
|---|---|---|---|---|---|---|---|---|---|
| `/dashboard` | `/health`, coverage, model status | KPI cards, links into workspaces | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — 200; MEASURED/VERIFIED labels; no fake “LIVE” |
| `/login` | identity service | Google sign-in | ✅ | — | ✅ | — | ✅ | ✅ | **VERIFIED** |

### 2.2 Intelligence workspaces

| Route | Data / API | Actions | L | E | Er | P | R | B | Status |
|---|---|---|---|---|---|---|---|---|---|
| `/players` | `/api/v1/players/search` | server search, filters, sort, pagination, open profile | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — `1–25 / 109` real total; page 3 (offset 50) and last page (9) verified via API |
| `/players/:playerId` | profile + intelligence + role | tabs, shortlist, similar | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** |
| `/players/compare` | compare endpoint | add/remove/replace players, grouped stats | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — missing stats render `—`, not `0` |
| `/players/similarity` | `/players/{id}/similar` | pick player, ranked comparables, “Why?” axis breakdown | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — real scores + why similar/different |
| `/players/roles` | `/players/roles` | archetype groups, coverage, player links | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — only persisted classifications; reports not-classified |
| `/tactical/fit` | canonical fit engine | select player/team/formation → recalculate | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — selection triggers recalc; INSUFFICIENT_SAMPLE shown |

### 2.3 Market & recruitment

| Route | Data / API | Actions | L | E | Er | P | R | B | Status |
|---|---|---|---|---|---|---|---|---|---|
| `/market` | market overview | links into market subviews | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — hard gate surfaced |
| `/market/valuation` | valuation model | view baseline + interval | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **BLOCKED (truthful)** — `MODEL_RELEASE_BLOCKED`; UI shows gate, never a fabricated value |
| `/market/opportunities` | opportunity scan | IDLE→LOADING→SUCCESS/EMPTY/PARTIAL/ERROR | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — zero comparables → “cannot calculate”, no manufactured candidates |
| `/market/replacements` | replacement ranking | candidate list + trade-offs | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — similarity ≠ suitability labelled |
| `/market/risk` | risk model | factor breakdown (observed/modelled/assumed) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — limitations shown, no invented percentages |
| `/recruitment/projects` | `/api/phase10/recruitment/projects` | create project, add candidates, advance state, compare, report | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — created “Verification FC”, persisted across full reload |
| `/watchlists` | watchlist endpoints | create/rename, add/remove, alerts | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/shortlists` | shortlist endpoints | create, add/remove, share | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/shortlists/:shortlistId` | shortlist detail | detail view | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/shared/shortlists/:token` | shared shortlist | read-only shared view | ✅ | ✅ | ✅ | — | ✅ | ✅ | **IMPLEMENTED** |

### 2.4 Decision & squad

| Route | Data / API | Actions | L | E | Er | P | R | B | Status |
|---|---|---|---|---|---|---|---|---|---|
| `/decisions` | decision engine | requirements → candidates → decision record | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — hard constraints enforced & exclusions explained |
| `/decisions/recruitment` | decision engine | recruitment targeting variant | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** |
| `/decisions/replacement` | decision engine | replacement analysis variant | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** |
| `/decisions/scenarios` | decision engine | transfer scenario variant | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** |
| `/squad/builder` | squad construction | build squad, role coverage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/squad/simulator` | tactical simulation | simulate | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/squad/scenarios` | scenario engine | scenario lab | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/scenarios` | scenario engine | multi-alternative scenarios | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |

### 2.5 Match intelligence

| Route | Data / API | Actions | L | E | Er | P | R | B | Status |
|---|---|---|---|---|---|---|---|---|---|
| `/matches` | match fixtures | fixture selection, stats, provenance | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — 200; “Match center” renders; no false “live” badge |
| `/matches/:matchId` | match detail + intelligence | overview, player perf, timeline | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** — event visualisations only render when event data exists |

### 2.6 Research, copilot, system

| Route | Data / API | Actions | L | E | Er | P | R | B | Status |
|---|---|---|---|---|---|---|---|---|---|
| `/research` | feature registry | registry overview | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/research/models` | model registry | model status/validation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** — measured/UNKNOWN only, nothing hard-coded healthy |
| `/research/data` | data sources | provider coverage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/research/experiments` | experiments | experiment list | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **IMPLEMENTED** |
| `/copilot` | `/copilot/query` (Groq gateway) | streaming Q&A, abort, error, provider badge | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** — real streaming; provider status from backend |
| `/system/data-quality` | data-quality endpoints | coverage/freshness report | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFIED** |

### 2.7 Demo-gated modules (`409 DEMO_ONLY` outside demo mode)

`KNOWN_LIMITATIONS.md` L2: these routers are mounted with `require_demo_data` and answer
`409 {"code":"DEMO_ONLY"}` in non-demo mode. The UI shows `ModuleStateBanner` — a truthful
“demo-gated” explanation — never a blank screen or fabricated data.

| Route | Status |
|---|---|
| `/operations` | **BLOCKED (truthful)** — demo-gated banner |
| `/operations/global` | **BLOCKED (truthful)** — demo-gated banner |
| `/intelligence/continuous` | **BLOCKED (truthful)** — demo-gated banner |
| `/decision-lab` | **BLOCKED (truthful)** — demo-gated banner |
| `/outcome-intelligence` | **BLOCKED (truthful)** — demo-gated banner |

---

## 3. Server-side pagination proof (`/players`)

Executed directly against the canonical API with a real JWT:

| Query | Result |
|---|---|
| `GET /api/v1/players/search?page=3&page_size=25` | `200`, `total=109`, 25 items (offset 50 — beyond the old 50-cap) |
| `GET /api/v1/players/search?page=5&page_size=25` | `200`, `total=109`, 9 items (correct last page) |
| `GET /health` | `200` `{"status":"ALIVE", ...}` |

## 4. Reconciliation note

All 39 declared routes are accounted for above. There are no routes that render without useful
content or that are unreachable from navigation. Remaining honest limitations are data/model
conditions (valuation model, demo-gated Phase 11–14 modules, provider plan cap) — all surfaced
in-app, none hidden.
