# Sidebar Module Acceptance Matrix

**Date:** 2026-10-21 · **Stack:** API `8002`, identity `8003`, gateway `8004`, UI `3005`, DB `fios` (container `fios_pg`).

Each sidebar module was exercised through the complete contract path:
`Navigation → Frontend component → API request → Auth → Backend route → Domain service → Database/provider/model → Validated response → Frontend rendering → Persistence where applicable`.

Evidence codes used in the table:

- **[B]** browser evidence (route opened, DOM inspected, every XHR/fetch captured)
- **[A]** direct live API probe with a signed admin JWT
- **[T]** automated test (file named)
- **[L]** live provider/LLM call

| Sidebar module | Navigation | API call | Auth | Domain service → DB | Response validated | Rendered truthfully | Persisted | Evidence | Status |
|---|---|---|---|---|---|---|---|---|---|
| Dashboard | ✔ | ✔ 4 calls, 200 | ✔ bearer | ✔ `players`/`clubs`/`matches` | ✔ `total=109` | ✔ 109 / 480 / 20 | read-only | [B][A][T] | `VERIFIED` |
| Players | ✔ | ✔ search/facets | ✔ | ✔ `players`+`player_identities` | ✔ `items,total,page,page_size,total_pages,has_next` | ✔ badge `1–25 / 109`, page 3 `51–75 / 109` | read-only | [B][A][T] | `VERIFIED` |
| Comparison | ✔ | ✔ picker search | ✔ | ✔ `players`,`player_season_stats` | ✔ M. Akanji selected | ✔ slot shows 2514′ 2G 0A | read-only | [B][A] | `VERIFIED` |
| Similarity | ✔ | ✔ | ✔ | ✔ `feature_snapshots` | ✖ not exercised end-to-end | ✔ renders | read-only | [B] | `PARTIALLY_VERIFIED` |
| Roles | ✔ | ✔ 85 calls | ✔ | ✔ `player_role_profiles` (111) | ✖ per-player role not asserted | ✔ sample disclosure | read-only | [B] | `PARTIALLY_VERIFIED` |
| Tactical fit | ✔ | ✔ | ✔ | ✔ roles+features | ✖ not asserted | ✔ renders | read-only | [B] | `PARTIALLY_VERIFIED` |
| Recruitment projects | ✔ | ✔ GET 200 | ✔ | ✔ phase10 store | ✔ empty list | ✔ "No recruitment projects yet" | ✔ create not exercised | [B][A] | `PARTIALLY_VERIFIED` |
| Watchlists & alerts | ✔ | ✔ GET 200 | ✔ | ✔ phase10 store | ✔ empty list | ✔ "You have no watchlists yet" | ✔ create not exercised | [B][A] | `PARTIALLY_VERIFIED` |
| Decision engine | ✔ | ✔ `decisions/recruitment/analyze` 200 | ✔ | ✔ canonical index + engine | ✔ per-candidate evidence text | ✔ shows position/sample exclusions | decision records not exercised | [B] | `PARTIALLY_VERIFIED` |
| Market | ✔ | ✔ 8 calls 200 | ✔ | ✔ `transfers` (0) | ✔ coverage/readiness | ✔ states absence | – | [B][A] | `INSUFFICIENT_DATA` |
| Shortlists | ✔ | ✔ | ✔ | ✔ MongoDB | ✔ empty list | ✔ empty state | create not exercised | [B] | `PARTIALLY_VERIFIED` |
| Opportunities | ✔ | ✔ | ✔ | ✔ `transfers` (0) | ✔ | ✔ empty | – | [B] | `INSUFFICIENT_DATA` |
| Replacements | ✔ | ✔ | ✔ | ✔ `transfers` (0) | ✔ | ✔ empty | – | [B] | `INSUFFICIENT_DATA` |
| Transfer risk | ✔ | ✔ | ✔ | ✔ canonical index | ✔ | ✔ renders factors | – | [B] | `PARTIALLY_VERIFIED` |
| Matches | ✔ | ✔ | ✔ | ✔ `matches` (235) | ✔ | ✔ list | read-only | [B] | `PARTIALLY_VERIFIED` |
| Decision Lab 2.0 | ✔ | ✔ **now reaches the API** | ✔ | ✔ demo-gated phase13 | ✔ 409 DEMO_ONLY | ✔ banner: "Module disabled on real data" | – | [B] | `BLOCKED_BY_PROVIDER` |
| Squad builder | ✔ | ✔ **200 (was 500)** | ✔ | ✔ `players`+role profiles | ✔ 30 players, coverage/depth scores | ✔ starting XI + depth gaps | read-only | [B][A][T] | `VERIFIED` |
| Scenarios (Multi-Alt) | ✔ | ✔ | ✔ | ✔ phase10 store | ✔ | ✔ states "no forecast produced" | – | [B] | `PARTIALLY_VERIFIED` |
| Transfer simulator | ✔ | ✔ **200 (was 500)** | ✔ | ✔ canonical index | ✔ | ✔ renders | read-only | [B][A] | `PARTIALLY_VERIFIED` |
| Scenario lab | ✔ | ✔ **200 (was 500)** | ✔ | ✔ canonical index | ✔ | ✔ renders | read-only | [B][A] | `PARTIALLY_VERIFIED` |
| Outcome intelligence | ✔ | ✔ 9 endpoints, all 409 | ✔ | ✔ demo-gated phase14 | ✔ | ✔ banner + global demo banner | – | [B][A] | `BLOCKED_BY_PROVIDER` |
| Research lab | ✔ | ✔ 36 calls 200 | ✔ | ✔ phase15 store | ✔ | ✔ renders | read-only | [B] | `PARTIALLY_VERIFIED` |
| Data sources | ✔ | ✔ | ✔ | ✔ phase15 + coverage | ✔ | ✔ renders | read-only | [B] | `PARTIALLY_VERIFIED` |
| Scout copilot | ✔ | ✔ streaming | ✔ | ✔ canonical index (15 of 109) | ✔ answer cites A. Danjuma + evidence | ✔ model badge AVAILABLE | – | [B][L] | `VERIFIED` |
| Live operations | ✔ | ✔ 409 on model lifecycle | ✔ | ✔ ingestion runs | ✔ | ✔ shows the demo-gate reason | – | [B][A] | `PARTIALLY_VERIFIED` |
| Global operations | ✔ | ✔ 409 (demo gate) | ✔ | ✔ demo fixtures | ✔ | ✔ global demo banner | – | [B][A] | `BLOCKED_BY_PROVIDER` |
| Continuous learning | ✔ | ✔ **now reaches the API** | ✔ | ✔ demo-gated phase12 | ✔ 7/7 refused | ✔ banner "7 of 7 module endpoints refused the request" | – | [B] | `BLOCKED_BY_PROVIDER` |
| Data quality | ✔ | ✔ | ✔ | ✔ canonical tables | ✔ | ✔ live probes | read-only | [B] | `PARTIALLY_VERIFIED` |

## Defects found and fixed during this acceptance pass

| # | Module | Defect | Root cause | Fix | Files |
|---|---|---|---|---|---|
| D1 | Squad builder / Transfer simulator / Scenario lab | `GET /api/v1/squads/build` returned **HTTP 500** | `SquadService.build_player_profile` read `PlayerRoleProfile.primary_role`; the column is `primary_archetype` → `AttributeError` | Read the real column | `apps/api/app/squad/service.py` |
| D2 | Player profile (Market tab) | `market-context` **500**, `valuation-baseline` **400**, `transfer-comparables` **400** | `build_player_market_context` passed the raw `dimension_scores` JSONB (`{"duels": {"score": null, ...}}`) into a `dict[str, float]` contract → pydantic `ValidationError` | Added `app/market/dimension_scores.py`; contract is now `dict[str, float \| None]` so an unknown score stays `null` instead of `0.0` | `apps/api/app/market/{dimension_scores,context,schemas,comparables}.py` |
| D3 | Valuation training-set build | would raise `AttributeError` (`contribution_scores` is not a column) | Same class of defect as D2, second call site | Reused the shared helper | `apps/api/app/market/dataset.py` |
| D4 | Decision Lab 2.0 | **Every** data request failed (`net::ERR_FAILED`, CORS) | Page used `process.env.REACT_APP_API_URL` (undefined) → fell back to `http://localhost:8000` instead of the configured gateway `http://localhost:8004` | Use the shared `BACKEND_URL` from `src/lib/footballApi.js` | `src/pages/DecisionLabPage.js` |
| D5 | Continuous learning | **Every** data request failed (same cause as D4) and errors were swallowed (`r.ok ? json : []`) | Wrong base URL + silent error handling | Shared `BACKEND_URL` + recorded failures | `src/pages/ContinuousIntelligencePage.js` |
| D6 | Outcome intelligence | Backend `409 DEMO_ONLY` was swallowed into empty arrays → the page looked like "no data" | `.catch(() => ({ data: [] }))` on every request | Failures are recorded and rendered | `src/pages/OutcomeIntelligencePage.js` |
| D7 | Dashboard + Copilot | LLM status always `CONFIGURED_UNVERIFIED`, dashboard showed no provider | `getLLMStatus()` called `/api/v1/llm-status`; the route is mounted at the app root (`/llm-status`) | Fixed URL | `src/lib/footballApi.js` |
| D8 | LLM status API | `active.status` never reflected verification | `LLMRegistry.get_active_status()` looked the status up by `provider.provider_name` ("Groq") while `verify_all()` wrote it under the settings key ("groq") | Track the primary/fallback keys explicitly | `apps/api/app/llm/registry.py` |
| D9 | Players | Page indicator labelled stale rows as the requested page | `placeholderData: previous` kept the old rows on screen while the page state advanced | Range/indicator derive from the returned page; stale rows are not shown | `src/pages/PlayerSearchPage.js` |
| D10 | Players | 50-player illusion in the UI and a 100-row backend cap without a total | `getPlayers({limit:50})` counted client-side; legacy list had no total | Canonical paginated contract + backend totals | `src/pages/DashboardPage.js`, `apps/api/app/api/routes_canonical.py` |

## Defects still open (not fixed in this pass)

| # | Module | Defect | Impact |
|---|---|---|---|
| O1 | Roles | 85 sequential HTTP calls for one page (one `/players/{id}/role` per sampled player) | N+1 fan-out; slow page, heavy API load |
| O2 | Data quality | Probes report "5 records" (a `limit=5` sample) next to a `HEALTHY` badge | Can be read as the true row count |
| O3 | Phase 11–14 | Entire router families are demo-gated and answer `409` on real data | Four sidebar modules have no canonical implementation |
| O4 | Market family | `transfers` is empty, so valuations/comparables/opportunities have nothing to rank | `INSUFFICIENT_DATA` rather than a defect, but the modules cannot be verified end to end |
| O5 | Decision Lab | The club selector offers demo club ids (`arsenal_fc`) | Demo vocabulary in a production surface |
