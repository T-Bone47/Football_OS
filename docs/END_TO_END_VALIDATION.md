# End-to-End Validation

**Date:** 2026-10-21 · **Stack:** analytics API `8002`, identity `8003`, gateway `8004`, UI `3005`, PostgreSQL `fios` / `fios_test`, MongoDB `fios_mongo`.

This document records what was executed, with exact commands and exact results. Anything not
executed is listed as unverified; nothing is inferred from a green unit test alone.

## 1. How the end-to-end pass was executed

1. **Route sweep.** Every route in `src/App.js` was opened in a real browser. For each route the
   DOM was captured *and* every HTTP request was recorded (both XHR and `fetch` — the first
   sweep missed the axios calls and had to be repeated), so 4xx/5xx responses and transport
   failures are visible rather than inferred.
2. **Live API probes.** Individual endpoints were called directly against `127.0.0.1:8002` with a
   JWT minted from `settings.auth_jwt_secret` (issuer `football-os-identity`, audience
   `football-os-api`). No secret was printed.
3. **Live provider calls.** API-Football (page 1 + page 4 of league 39 / season 2023) and Groq
   (completion + streaming) were called for real.
4. **Automated suites.** Backend `pytest` and frontend `yarn test` were executed; the production
   frontend build was executed.

## 2. Player pipeline — the original defect

### Root cause (three layers, all verified, none assumed)

| Layer | Defect | Evidence |
|---|---|---|
| Ingestion | Only page 1 of the provider's declared 51 pages was ever fetched | `ingestion_runs` for `endpoint='players'` before the fix: a single page; the provider metadata says `paging.total=51` |
| Backend API | The legacy list endpoint was capped and carried no total | `GET /api/v1/players` returned an array with no `total`; the dashboard could not learn the real size |
| Frontend | The dashboard counted the rows it received: `getPlayers({ limit: 50 })` | Dashboard rendered "50" while the database held 69 and the provider declared 1,020 |

### Repair

- Ingestion: provider-metadata-driven pagination with resume, measured record counts, raw Bronze
  snapshot per page, idempotent upserts, and an explicit plan-limit classification
  (`apps/api/app/ingestion/service.py`, `apps/api/app/providers/{api_football,errors}.py`).
- API: canonical paginated contract `GET /api/v1/players/search` returning
  `items, total, page, page_size, total_pages, has_next`; filters applied **before** pagination;
  LIKE escaping; validated bounds; stable sort with an id tiebreaker; plus
  `GET /api/v1/players/facets` and `GET /api/v1/players/coverage`
  (`apps/api/app/api/routes_canonical.py`).
- Frontend: the dashboard uses the backend total, and the players page is a real server-paginated
  table with search, position/nationality filters, page-size selection and distinct
  loading/error/empty states (`src/pages/PlayerSearchPage.js`, `src/pages/DashboardPage.js`).

### Before / after (measured on the same database)

| Metric | Before | After |
|---|---|---|
| Canonical players | 69 | **109** |
| Provider identities | 69 | **109** (0 duplicate provider ids) |
| Player-season statistics | 21 | **61** |
| Players with a club association | 0 | **60** |
| Players with a primary position | 0 | **60** |
| Dashboard player count | 50 | **109** (server total) |
| Rows visible on page 3 of the players page | not reachable | **25** (records 51–75) |

### Browser evidence

| Action | Observed |
|---|---|
| Open `/players` | badge `1–25 / 109`, `Page 1 of 5 · 25 shown`, 25 rows |
| Click Next | `26–50 / 109` |
| Click Next | `51–75 / 109`, first `J. Aguilar`, last `M. Akanji` |
| Search `Akanji` (a record 75 player, from page 1) | `1–1 / 1`, one row `M. Akanji` |
| Filter position `D` | `1–20 / 20` — the filter is applied before pagination |
| Page size 50 → page 2 | `51–100 / 109`, `Page 2 of 3 · 50 shown`, contains `M. Akanji` |
| Open `M. Akanji` | Defender, Switzerland, 2514 minutes, 2 goals, 0 assists, rating 7.27931 |
| Repeat the page-3 API call | identical ordered ids (stable sort) |

### API contract evidence (`Football_OS-frontend/test_reports/evidence/api_player_evidence.json`)

```
GET /api/v1/players/search?page=1&page_size=25 -> total=109 total_pages=5 page=1 has_next=true  (25 items, A. Areola..C. Nkunku)
GET /api/v1/players/search?page=3&page_size=25 -> 25 items, J. Aguilar..M. Akanji
GET /api/v1/players/search?page=2&page_size=50 -> 50 items, J. Aguilar..Thiago Silva, contains M. Akanji
GET /api/v1/players/search?q=Akanji              -> total=1
GET /api/v1/players/facets                       -> total_players=109
GET /api/v1/players?limit=100                    -> legacy array shape, 100 items
GET /api/v1/players/search?page=0                -> 422
GET /api/v1/players/search?page_size=101         -> 422
GET /api/v1/players/search?sort_by=not_a_column  -> 422
```

### A UI defect found by this verification

The page indicator advanced to the requested page while the previous rows were still on screen
(`placeholderData: previous`), so the UI briefly claimed "51–75" for page-2 rows. The display
range and indicator are now derived from the **returned** page, and stale rows are not rendered.
Regression test: `frontend/src/pages/PlayerSearchPage.test.js` (3 tests) plus
`frontend/src/lib/playerPagination.test.js` (5 tests).

## 3. Cross-module defects found and repaired in this pass

| Module | Symptom | Root cause | Fix | Regression test |
|---|---|---|---|---|
| Squad builder / Transfer simulator / Scenario lab | `GET /api/v1/squads/build` → **HTTP 500** | `SquadService.build_player_profile` read `PlayerRoleProfile.primary_role`; the column is `primary_archetype` | read the real column (`apps/api/app/squad/service.py`) | `tests/integration/test_squad_market_regression.py` |
| Player profile → Market | `market-context` 500, `valuation-baseline` 400, `transfer-comparables` 400 | the raw `dimension_scores` JSONB (`{"duels": {"score": null, ...}}`) was validated against `dict[str, float]` | shared helper `app/market/dimension_scores.py`; contract `dict[str, float \| None]` — an unknown score stays `null` | same file (4 tests) |
| Valuation training set | would raise `AttributeError` | second call site of the same wrong column name | shared helper | same file |
| Decision Lab 2.0 | every request failed (`net::ERR_FAILED`, CORS) | the page used `REACT_APP_API_URL` (undefined) → `http://localhost:8000` instead of the configured gateway | use the shared `BACKEND_URL` | browser evidence (26 API calls now reach the backend) |
| Continuous learning | every request failed, errors swallowed | same wrong base URL + `r.ok ? json : []` | shared `BACKEND_URL` + recorded failures | browser evidence (7/7 refusals reported) |
| Outcome intelligence | `409 DEMO_ONLY` swallowed into empty tables | `.catch(() => ({ data: [] }))` on every request | failures are recorded and rendered | browser evidence (banner) |
| Dashboard / Copilot | LLM provider always "NOT_CONFIGURED" | `getLLMStatus()` used `/api/v1/llm-status`; the route is at the app root | fixed URL | live `/llm-status` + `test_llm_registry.py` |
| `/llm-status` | `active.status` never became `AVAILABLE` | registry keyed the status by the settings name, looked it up by the provider name | explicit primary/fallback keys | `tests/unit/test_llm_registry.py` |
| Test isolation | 18 tests errored with `UndefinedTableError` | `tests/integration/test_ingestion_lifecycle.py` ran `create_all` + `drop_all` on the **shared** test database | the file now uses the shared transaction-rollback fixture | full-suite rerun |

## 4. Test results

### Backend (targeted regression set)

```
$env:PYTHONPATH="apps/api"; $env:TEST_DATABASE_URL="postgresql+asyncpg://fios:fios@localhost:55432/fios_test"
python -m pytest tests/unit/test_provider_errors.py tests/unit/test_llm_registry.py \
  tests/unit/test_decision_intelligence.py tests/integration/test_player_pagination_api.py \
  tests/integration/test_ingestion_pagination.py tests/integration/test_canonical_api.py \
  tests/integration/test_squad_market_regression.py tests/unit/test_validation.py -q
=> 57 passed
```

### Backend (full suite)

```
python -m pytest tests -q
=> 8 failed, 938 passed, 10 skipped, 39 warnings in 137.78s   (0 errors)
```

Before this pass the same command reported `9 failed, 902 passed, 27 skipped, 18 errors`. The
18 errors were caused by the destructive fixture, and the isolation fix removed all of them; the
ledger-trigger failure disappeared as a side effect (the migrated schema carries the trigger that
`create_all` never created). The 8 remaining failures are the pre-existing ones listed in
`docs/KNOWN_LIMITATIONS.md` (L8): one copilot mock contract, two copilot security/grounding
expectations, and five transfer-fixture tests.

### Frontend

```
$env:CI="true"; yarn test --watchAll=false --runInBand
=> Test Suites: 2 passed, Tests: 8 passed
```

### Frontend production build

```
$env:NODE_OPTIONS="--max-old-space-size=4096"; yarn build
=> Compiled successfully.  278.46 kB gzip js / 17 kB css
```

### Migrations

```
$env:DATABASE_URL="postgresql+asyncpg://fios:fios@localhost:55432/fios_test"; python -m alembic upgrade head
=> 0004 -> 0005 ... 0015 -> 32ee69fbf263 (add_player_club_id)   # fresh-database install, 30 tables
```

### Live provider calls

| Provider | Call | Result |
|---|---|---|
| API-Football | `GET /players?league=39&season=2023&page=1` | `paging.total=51`, 20 records |
| API-Football | `GET /players?league=39&season=2023&page=4` | plan error: `Free plans are limited to a maximum value of 3 for the Page parameter` |
| Groq | completion, prompt `Reply with exactly: FIO_GROQ_OK` | `FIO_GROQ_OK` in 478–706 ms, 133 tokens |
| Groq | streaming, same prompt | 6 chunks, TTFT 379 ms, assembled `FIO_GROQ_OK` |
| StatsBomb | `competitions` catalogue | ingested (Bronze snapshot kept) |

## 5. Workflow validation summary

| Workflow | Result |
|---|---|
| Dashboard → real totals | `VERIFIED` (109 / 480 / 20, provider status AVAILABLE) |
| Players → browse beyond 50 → search → filter | `VERIFIED` |
| Player profile → statistics | `VERIFIED` (M. Akanji, record 75) |
| Comparison → select a player beyond 50 | `VERIFIED` |
| Squad build → formation, coverage, depth | `VERIFIED` after the 500 fix |
| Copilot → grounded answer over the canonical index | `VERIFIED` (live Groq) |
| Decision engine → candidate ranking with exclusions | `VERIFIED` (read path) |
| Market / opportunities / replacements | `INSUFFICIENT_DATA` (no transfer feed) |
| Watchlists / shortlists / projects write paths | not exercised (see `KNOWN_LIMITATIONS.md`, L7) |
| Phase 11–14 modules | `BLOCKED_BY_PROVIDER` (demo-gated, now stated in the UI) |
