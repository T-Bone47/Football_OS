# Feature Inventory — Football Intelligence OS

**Date:** 2026-10-21
**Repository:** `Football_OS-main-remediated-v2/Football_OS-main` (not a git repository; all changes are uncommitted working-tree edits)
**Verification environment:** local stack — analytics API `127.0.0.1:8002`, identity service `127.0.0.1:8003`, dev gateway `127.0.0.1:8004`, React UI `127.0.0.1:3005`, PostgreSQL container `fios_pg` (database `fios`), MongoDB container `fios_mongo`.

## How this inventory was produced

1. The React route table (`Football_OS-frontend/frontend/src/App.js`) and the sidebar
   (`src/components/Sidebar.js`) were read in full; every route is listed below, including
   routes that have no sidebar entry.
2. Every FastAPI router was enumerated mechanically from `apps/api/app/api/routes_*.py`
   and `apps/api/app/main.py` (156 endpoints across 11 routers).
3. Every route was opened in a real browser against the running stack. For each route the
   DOM was inspected and **every** HTTP request (XHR *and* fetch, not just `fetch`) was
   captured, so failing backend calls (4xx/5xx) and transport failures are visible.
4. Backend behaviour was re-probed directly against the live API with a signed admin JWT
   (`/api/v1/...`, `/api/phase10/...`, `/api/phase12/...`).
5. Automated suites were executed (see `docs/END_TO_END_VALIDATION.md`).

## Status vocabulary

| Status | Meaning |
|---|---|
| `VERIFIED` | The full acceptance path was exercised against real persisted data with reproducible evidence in this session. |
| `PARTIALLY_VERIFIED` | The module loads and calls its real backend, but one or more acceptance requirements (write path, pagination, persistence, deeper calculation) were not exercised end to end. |
| `FAILING` | A reproducible functional defect exists. |
| `BLOCKED_BY_PROVIDER` | A required external dependency (provider plan/quota) prevents verification. |
| `INSUFFICIENT_DATA` | The capability exists and behaves correctly, but the canonical dataset is too small/thin to exercise it (it reports uncertainty instead of fabricating). |
| `NOT_IMPLEMENTED` | The intended capability does not exist in the current build. |
| `NOT_APPLICABLE` | The requirement does not apply to that module. |

---

## 1. Module inventory (sidebar order)

| # | Sidebar module | Route | Frontend entry | Backend endpoints | Persistence / data source | Tests | Status |
|---|---|---|---|---|---|---|---|
| 1 | Dashboard | `/dashboard` | `pages/DashboardPage.js` | `GET /api/v1/players/search?page=1&page_size=6`, `/api/v1/clubs`, `/api/v1/matches?limit=20`, `/llm-status` | `players`, `clubs`, `matches` (PostgreSQL) | `tests/integration/test_player_pagination_api.py` | `VERIFIED` |
| 2 | Players | `/players` | `pages/PlayerSearchPage.js` | `GET /api/v1/players/search`, `/api/v1/players/facets`, `/api/v1/players/coverage` | `players` + `player_identities` | `tests/integration/test_player_pagination_api.py`, `frontend/src/pages/PlayerSearchPage.test.js` | `VERIFIED` |
| 3 | Comparison | `/players/compare` | `pages/PlayerComparePage.js` | `GET /api/v1/players/search?q=`, `GET /api/v1/players/{id}` | `players`, `player_season_stats` | `tests/integration/test_canonical_api.py` | `VERIFIED` |
| 4 | Similarity | `/players/similarity` | `pages/SimilarityPage.js` | `GET /api/v1/players/{id}/similar`, `/api/v1/players/{id}/similarity/{other}` | `feature_snapshots` (7 rows) | `tests/unit/test_similarity_v2_evaluation.py` | `PARTIALLY_VERIFIED` |
| 5 | Roles | `/players/roles` | `pages/RolesPage.js` | `GET /api/v1/players/{id}/role` (one per sampled player) | `player_role_profiles` (111) | `tests/unit/test_role_v2_evaluation.py` | `PARTIALLY_VERIFIED` |
| 6 | Tactical fit | `/tactical/fit` | `pages/TacticalFitPage.js` | `GET /api/v1/tactical/contexts`, `/api/v1/players/{id}/tactical-fit` | `player_role_profiles`, `feature_snapshots` | `tests/unit/test_tactical_fit_v2_evaluation.py` | `PARTIALLY_VERIFIED` |
| 7 | Recruitment projects | `/recruitment/projects` | `pages/RecruitmentProjectsPage.js` | `GET/POST /api/phase10/recruitment/projects`, `.../candidates`, `.../compare`, `.../report` | `operational_records` (MongoDB-free, PostgreSQL phase10 store) | `tests/unit/test_phase10_recruitment_truth.py` | `PARTIALLY_VERIFIED` |
| 8 | Watchlists & alerts | `/watchlists` | `pages/WatchlistsPage.js` | `GET/POST /api/phase10/watchlists`, `/alerts`, `.../evaluate` | phase10 operational store | `tests/unit/test_phase10_operations.py` | `PARTIALLY_VERIFIED` |
| 9 | Decision engine | `/decisions` | `pages/DecisionPage.js` | `POST /api/v1/decisions/recruitment/analyze`, `/replacement`, `/transfer-scenario`, `/compare` | `player_season_stats`, `player_role_profiles` | `tests/unit/test_decision_intelligence.py` (6 passed) | `PARTIALLY_VERIFIED` |
| 10 | Market | `/market` | `pages/MarketPage.js` (variant `overview`) | `GET /api/v1/market/coverage`, `/benchmarks`, `/transfers`, `/readiness` | `transfers` (**0 rows**) | `tests/unit/test_market_feature_registry.py` | `INSUFFICIENT_DATA` |
| 11 | Shortlists | `/shortlists` | `pages/ShortlistsPage.js` | `GET/POST /api/shortlists` (identity service) | MongoDB `fios_mongo` | `tests/unit/test_persistence_contract.py` | `PARTIALLY_VERIFIED` |
| 12 | Opportunities | `/market/opportunities` | `pages/MarketPage.js` (variant `opportunities`) | `GET /api/v1/market/opportunities` | `transfers` (0 rows) | `tests/unit/test_market_feature_registry.py` | `INSUFFICIENT_DATA` |
| 13 | Replacements | `/market/replacements` | `pages/MarketPage.js` (variant `replacements`) | `POST /api/v1/market/replacements`, `GET /api/v1/market/replacements/{id}` | `transfers` (0 rows) | `tests/unit/test_market_feature_registry.py` | `INSUFFICIENT_DATA` |
| 14 | Transfer risk | `/market/risk` | `pages/MarketPage.js` (variant `risk`) | `GET /api/v1/market/risk`, `/api/v1/players/{id}/transfer-risk` | `transfers` (0 rows), `player_season_stats` | `tests/unit/test_market_feature_registry.py` | `PARTIALLY_VERIFIED` |
| 15 | Matches | `/matches` | `pages/MatchesPage.js` | `GET /api/v1/matches`, `/api/v1/matches/{id}`(+events/lineups/statistics) | `matches` (235), `match_statistics` | `tests/integration/test_canonical_match_api.py` | `PARTIALLY_VERIFIED` |
| 16 | Decision Lab 2.0 | `/decision-lab` | `pages/DecisionLabPage.js` | `/api/v1/decision-lab/*` (phase13) | demo fixtures only | `tests/unit/test_phase13_decision_simulation.py` | `BLOCKED_BY_PROVIDER` (demo-gated) |
| 17 | Squad builder | `/squad/builder` | `pages/SquadPage.js` (variant `builder`) | `GET /api/v1/squads/build?formation=` | `players`, `player_role_profiles` | `tests/integration/test_squad_market_regression.py` (new) | `VERIFIED` (was `FAILING`) |
| 18 | Scenarios (Multi-Alt) | `/scenarios` | `pages/ScenariosPage.js` | `GET/POST /api/phase10/scenarios` | phase10 store | `tests/unit/test_phase10_operations.py` | `PARTIALLY_VERIFIED` |
| 19 | Transfer simulator | `/squad/simulator` | `pages/SquadPage.js` (variant `simulator`) | `POST /api/v1/squads/simulate-transfer` | `players`, `player_season_stats` | `tests/integration/test_squad_market_regression.py` | `PARTIALLY_VERIFIED` |
| 20 | Scenario lab | `/squad/scenarios` | `pages/SquadPage.js` (variant `scenarios`) | `POST /api/v1/scenarios/transfer` | `players`, `player_season_stats` | `tests/unit/test_phase13_scenario_engine.py` | `PARTIALLY_VERIFIED` |
| 21 | Outcome intelligence | `/outcome-intelligence` | `pages/OutcomeIntelligencePage.js` | `/api/v1/outcomes/*` (phase14) | demo fixtures only | `tests/unit/test_phase14_outcome_ledger.py` | `BLOCKED_BY_PROVIDER` (demo-gated) |
| 22 | Research lab | `/research` | `pages/ResearchPage.js` (variant `overview`) | `/api/v1/research/*` (phase15) | phase15 operational store | `tests/unit/test_phase15_*` | `PARTIALLY_VERIFIED` |
| 23 | Data sources | `/research/data` | `pages/ResearchPage.js` (variant `data`) | `/api/v1/research/*`, `/api/data-coverage/*` | phase15 store + ingestion runs | `tests/unit/test_phase16_data_quality.py` | `PARTIALLY_VERIFIED` |
| 24 | Scout copilot | `/copilot` | `pages/CopilotPage.js` | `POST /api/copilot/query` (streaming), `GET /api/v1/players/search` | Groq (live) + canonical index | `tests/unit/test_decision_intelligence.py`, live probe | `VERIFIED` |
| 25 | Live operations | `/operations` | `pages/OperationsPage.js` | `GET /api/phase10/operations/competition-readiness`, `/ingestion/runs`, `/api/phase10/models/lifecycle` | ingestion runs, model registry | `tests/unit/test_phase10_operations.py` | `PARTIALLY_VERIFIED` |
| 26 | Global operations | `/operations/global` | `pages/GlobalOperationsPage.js` | `/api/phase11/*` | demo fixtures only | `tests/unit/test_phase11_*` | `BLOCKED_BY_PROVIDER` (demo-gated) |
| 27 | Continuous learning | `/intelligence/continuous` | `pages/ContinuousIntelligencePage.js` | `/api/phase12/*` | demo fixtures only | `tests/unit/test_phase12_*` | `BLOCKED_BY_PROVIDER` (demo-gated) |
| 28 | Data quality | `/system/data-quality` | `pages/DataQualityPage.js` | `GET /api/v1/players?limit=5`, `/clubs`, `/matches?limit=5`, `/features/registry` | canonical tables | `tests/unit/test_phase16_data_quality.py` | `PARTIALLY_VERIFIED` |

### Routes without a sidebar entry (discovered, not invented)

| Route | Page | Status |
|---|---|---|
| `/market/valuation` | `MarketPage.js` (variant `valuation`) | `PARTIALLY_VERIFIED` |
| `/research/models` | `ResearchPage.js` (variant `models`) | `PARTIALLY_VERIFIED` |
| `/research/experiments` | `ResearchPage.js` (variant `experiments`) | `PARTIALLY_VERIFIED` |
| `/decisions/recruitment`, `/decisions/replacement`, `/decisions/scenarios` | `DecisionPage.js` (same page, tab presets) | `PARTIALLY_VERIFIED` |
| `/players/:playerId` | `PlayerProfilePage.js` | `VERIFIED` (after the market-context fix) |
| `/matches/:matchId` | `MatchesPage.js` (detail) | `PARTIALLY_VERIFIED` |
| `/shortlists/:shortlistId` | `ShortlistsPage.js` (detail) | `PARTIALLY_VERIFIED` |
| `/shared/shortlists/:token` | `SharedShortlistPage.js` | `PARTIALLY_VERIFIED` (not exercised — no share token exists) |
| `/login`, `/auth-callback` | `App.js` | `VERIFIED` (session flow used for every browser run) |

---

## 2. Provider and ingestion inventory

| Provider | Endpoint | Runs (SUCCESS/FAILED) | Records | Notes |
|---|---|---|---|---|
| api-football | `players` | 10 / 1 | 40 measured (pages 2–3) | Page 4 rejected by the free plan (`page` ≤ 3). |
| api-football | `leagues` | 13 / 0 | – | Competition catalogue. |
| api-football | `teams` | 8 / 0 | – | 480 clubs canonical. |
| api-football | `fixtures`, `fixtures/events`, `fixtures/lineups`, `fixtures/players`, `fixtures/statistics` | 11 / 15 | – | Historical attempts; 235 matches canonical. |
| api-football | `injuries`, `predictions`, `standings` | 3 / 0 | – | Single runs. |
| statsbomb | `competitions`, `matches` | 3 / 0 | – | Open-data catalogue; **not** a player feed. |

## 3. Canonical data inventory (database `fios`, measured 2026-10-21)

| Table | Rows |
|---|---|
| `players` | 109 |
| `player_identities` | 109 (provider `api-football`, 0 duplicate provider ids) |
| `player_season_stats` | 61 |
| `players.club_id` populated | 60 |
| `players.primary_position` populated | 60 |
| `player_match_stats` | 0 (no match-level ingestion in scope) |
| `clubs` | 480 |
| `matches` | 235 |
| `competitions` / `seasons` / `competition_seasons` | 1242 / 15 / 1243 |
| `feature_snapshots` | 7 |
| `player_role_profiles` | 111 |
| `player_contribution_snapshots` | 21 |
| `player_intelligence_snapshots` | 7 |
| `transfers` | 0 |
| `valuation_predictions` | 0 |
| `data_snapshots` (Bronze) | 48 |

## 4. Not implemented / deliberately disabled

| Capability | State | Reason |
|---|---|---|
| Phase 11 (global operations), Phase 12 (continuous learning), Phase 13 (Decision Lab), Phase 14 (outcome intelligence) | `NOT_IMPLEMENTED` on canonical data | Routers are mounted with `Depends(require_demo_data)`; outside demo mode they answer `409 {"code":"DEMO_ONLY"}`. The UI now states this instead of showing an empty module. |
| Live transfer-fee data | `NOT_APPLICABLE` | The API-Football free plan exposes no transfer endpoints; `transfers` is empty, so valuation returns `VALUATION_UNAVAILABLE` / `INSUFFICIENT_DATA` rather than a fabricated fee. |
| Match-level player statistics | `INSUFFICIENT_DATA` | `player_match_stats` is empty for the ingested scope. |
| Full league-season player universe | `BLOCKED_BY_PROVIDER` | The provider declares 51 pages for league 39 / season 2023 but the plan caps `page` at 3. |
