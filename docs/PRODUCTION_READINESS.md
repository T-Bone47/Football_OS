# Production Readiness Assessment

**Assessment date:** 2026-10-21
**Supersedes:** `docs/archive/PRODUCTION_READINESS_PHASE8_SUPERSEDED.md` (the Phase 8 document, which
described a different, earlier baseline and is retained for history only).
**Scope of this assessment:** the state of the working tree in
`Football_OS-main-remediated-v2/Football_OS-main` (not a git repository; changes are uncommitted).

## Release classification

# `PRODUCTION_TRUTH_BLOCKED`

The player-retrieval and pagination pipeline is repaired and proven, and the Groq inference path is
live and verified. The classification is nevertheless **blocked**, because three mandatory gates
still fail:

1. **Provider coverage gate** — the API-Football plan caps pagination at page 3, so the canonical
   player index covers 60 of the 1,020 records the provider declares for league 39 / season 2023.
   The system reports this as `BLOCKED_BY_PLAN` rather than hiding it, but the universe is not
   complete.
2. **Module coverage gate** — four sidebar modules (Global operations, Continuous learning,
   Decision Lab 2.0, Outcome intelligence) have no canonical implementation: their routers are
   demo-gated and answer `409 DEMO_ONLY`. The market family (Market, Opportunities, Replacements)
   is `INSUFFICIENT_DATA` because the plan exposes no transfer feed.
3. **Automated test gate** — the full suite still has failing tests: `8 failed, 938 passed,
   10 skipped, 0 errors`. They are pre-existing and unrelated to this pass (one copilot mock
   contract, two copilot security/grounding expectations, five transfer-fixture tests), but a
   release claim requires them to pass, not to be explained.

---

## 1. Gate-by-gate status

| # | Gate | Requirement | Result | Evidence |
|---|---|---|---|---|
| G1 | Provider authentication and access scope | Verified | **PASS** | Groq live completion + streaming; API-Football key authenticates and its plan ceiling is captured verbatim |
| G2 | Pagination and ingestion coverage measured | Measured and reported | **PASS (truthful, incomplete)** | `declared_total_pages=51`, `completed_pages=3`, `accessible_pages=3`, `status=BLOCKED_BY_PLAN` |
| G3 | Repeated ingestion is idempotent | No duplicate rows | **PASS** | 109 identities for 109 players, 0 duplicate provider ids, 0 players missing an identity; re-normalisation produced no new rows |
| G4 | Canonical records and relationships valid | Constraints and FKs hold | **PASS** | Migration 0015 + `32ee69fbf263` applied cleanly on a fresh database; `player.club_id` FK present |
| G5 | Data provenance and failure reporting | Raw payload + counts + failures | **PASS** | 48 Bronze snapshots, `ingestion_runs` with status/error/parameters, measured `record_count` |
| G6 | Player counts consistent DB ↔ API ↔ UI | 109 everywhere | **PASS** | DB 109; `/api/v1/players/search` total 109; dashboard badge 109; players page `1–25 / 109` |
| G7 | Analytics calculations have reproducible tests | — | **PARTIAL** | Targeted suites green; the similarity/role/valuation surfaces are thin on data (`feature_snapshots`=7) and their ranking logic is not fully re-derived here |
| G8 | Squad and transfer workflows validate constraints | — | **PARTIAL** | Squad analysis now works end to end (was a 500) and reports coverage gaps; transfer simulation runs on a canonical index with no transfer universe |
| G9 | Financial unknowns and model uncertainty preserved | Unknown ≠ 0 | **PASS** | `estimated_value_eur=null`, `contribution_scores.duels=null`, `comparables_count=0`, `VALUATION_UNAVAILABLE` / `INSUFFICIENT_DATA` |
| G10 | Unsupported predictions blocked or marked uncalibrated | — | **PASS (by design)** | The Scenarios page states "NO FORECAST IS PRODUCED"; demo-only modules answer 409 instead of serving figures |
| G11 | LLM configuration valid | — | **PASS** | `GET /llm-status` → `AVAILABLE`, `streaming_verified=true`, no secret in the payload |
| G12 | Real Groq inference verified | Live call, not a mock | **PASS** | `FIO_GROQ_OK` in 478–706 ms (non-streaming) and 6 chunks / 379 ms TTFT (streaming) |
| G13 | All AI workflows use the shared gateway | — | **PASS** | `/api/copilot/query` → `app.decisions.copilot` → `LLMRegistry` → Groq; no direct SDK calls from pages |
| G14 | Data-backed tool calls work | — | **PASS** | The copilot answered with canonical players and the sample size (`15 of 109`) |
| G15 | Grounding, streaming, error handling, cancellation tested | — | **PARTIAL** | Streaming verified live; cancellation exercised manually; the automated LLM error matrix is not built (see `KNOWN_LIMITATIONS.md`, L10) |
| G16 | Provider status truthful | — | **PASS** | Two defects fixed this pass (wrong status URL, registry key mismatch); the dashboard and copilot now show `AVAILABLE` |
| G17 | Failed fallback providers clearly identified | — | **PASS** | `fallback_enabled=false`; HF (402) and Gemini (404) are not presented as healthy |
| G18 | Secrets never reach the frontend or logs | — | **PASS** | `/llm-status` exposes no key/header/trace; probes in this session printed no secret |
| G19 | Existing pages call real backend capabilities | — | **PASS (all 28 sidebar modules issue real API calls)** | Two modules were calling the wrong port and were fixed |
| G20 | Search, filters, pagination work | — | **PASS for players; PARTIAL elsewhere** | Players proven end to end; matches still has no total/pagination |
| G21 | Loading, empty and error states correct | — | **PARTIAL** | Player/Squad/Demo-gated modules now distinguish them; several older pages still swallow errors |
| G22 | Core workflows survive refresh | — | **PARTIAL** | Read paths are server-derived; write paths were not exercised (L7) |
| G23 | API and frontend contracts agree | — | **PASS** | 0 failing API calls on all 28 routes after the fixes |
| G24 | Relevant migrations pass | — | **PASS** | Fresh-database install: 0004 → 0015 → `32ee69fbf263`, 30 tables |
| G25 | Relevant automated tests pass | — | **PARTIAL** | 57-test targeted set green; full suite: 938 passed / 8 failed / 0 errors |
| G26 | Frontend build and backend validation pass | — | **PASS** | `yarn build` compiled successfully; `compileall` clean |
| G27 | Critical regressions fixed | — | **PASS** | 10 defects fixed this pass (see `SIDEBAR_MODULE_ACCEPTANCE_MATRIX.md`) |
| G28 | Security and configuration checks completed | — | **PARTIAL** | Router-level bearer auth verified (401 without a token); two Phase 8 copilot security tests still fail |
| G29 | Remaining failures documented | — | **PASS** | `docs/KNOWN_LIMITATIONS.md` |

**Gates that fail or are partial: G2 (scope), G7, G8, G15, G20 (partly), G21 (partly), G22, G25,
G28 (partly), and the four demo-gated modules.** Any one of them is sufficient to block the
release.

---

## 2. What was broken and what is now repaired

| Defect | Symptom | Root cause | Status |
|---|---|---|---|
| Dashboard counted a client-side slice | "50 players" | `getPlayers({limit:50})` length used as a total | **FIXED** — backend total (109) |
| Backend list had no total and a 100-row cap | No true count, no paging | Legacy list endpoint | **FIXED** — canonical `/players/search` contract |
| Ingestion fetched one page | 69 players instead of the provider's scope | No provider-metadata pagination | **FIXED** — resumable pagination, plan-limit aware |
| UI labelled stale rows as the new page | "51–75" over page-2 rows | `placeholderData: previous` | **FIXED** — range derived from the returned page |
| Squad builder 500 | Squad/Transfer simulator/Scenario lab dead | `PlayerRoleProfile.primary_role` does not exist | **FIXED** |
| Player profile market 400/500 | Market tab broken on every player | `dimension_scores` JSONB vs `dict[str, float]` | **FIXED** — unknown stays `null` |
| Valuation training set `AttributeError` | Dataset build broken | second call site of the same wrong column | **FIXED** |
| Decision Lab + Continuous learning dead | No data, silent | `REACT_APP_API_URL` undefined → wrong port | **FIXED** |
| Outcome intelligence looked empty | 409 swallowed | `.catch(() => ({data: []}))` | **FIXED** — truthful banner |
| LLM status never verified | Dashboard showed no provider | wrong status URL + registry key mismatch | **FIXED** |
| Test isolation destroyed the shared test DB | 18 cascading errors | `create_all`/`drop_all` teardown | **FIXED** (guard + rollback fixture) |
| `NormalizationService.upsert_player_season_stats` missing | 6 integration tests errored | method lost from the restored service | **FIXED** |

---

## 3. Test evidence (exact results)

### Targeted regression set (this pass)

```
python -m pytest tests/unit/test_provider_errors.py tests/unit/test_llm_registry.py \
  tests/unit/test_decision_intelligence.py tests/integration/test_player_pagination_api.py \
  tests/integration/test_ingestion_pagination.py tests/integration/test_canonical_api.py \
  tests/integration/test_squad_market_regression.py tests/unit/test_validation.py -q
=> 57 passed
```

### Frontend

```
CI=true yarn test --watchAll=false --runInBand
=> Test Suites: 2 passed, Tests: 8 passed
   (PlayerSearchPage.test.js: 3, playerPagination.test.js: 5)
```

### Frontend production build

```
yarn build => Compiled successfully. 278.46 kB (gzip) js, 17 kB css
```

### Migrations (fresh disposable database)

```
DATABASE_URL=postgresql+asyncpg://fios:fios@localhost:55432/fios_test python -m alembic upgrade head
=> 0004 → 0005 → … → 0015 → 32ee69fbf263 (add_player_club_id); 30 tables
```

### Full suite

```
python -m pytest tests -q
=> 8 failed, 938 passed, 10 skipped, 39 warnings in 137.78s   (0 errors)
```

Before this pass: `9 failed, 902 passed, 27 skipped, 18 errors`. The 18 errors were the
cascading `UndefinedTableError` failures caused by the destructive test fixture; the isolation fix
removed all of them and also closed the ledger-trigger failure (the migrated schema carries the
trigger that `create_all` never created). The 8 remaining failures are listed in
`docs/KNOWN_LIMITATIONS.md` (L8).

---

## 4. Release decision and rationale

**`PRODUCTION_TRUTH_BLOCKED`.**

The player pipeline — the defect that started this work — is fixed and proven end to end:
109 canonical players, a truthful backend total, server-side pagination, search and filters that
work beyond the first 50, and a stable, repeatable record order across the database, the API and
the UI. The squad and market defects found while auditing the rest of the sidebar are also fixed
and regression-tested, and the two modules that were calling the wrong port now reach the
backend and say, truthfully, that they are disabled on real data.

The release is still blocked, for reasons that are not code defects and cannot be closed by
writing more code:

- the provider plan makes the full player universe unreachable (1,020 declared → 60 ingested);
- four modules have no canonical implementation and the market family has no transfer feed;
- eight tests still fail (one copilot mock contract, two copilot security/grounding
  expectations, five transfer-fixture tests).

Downgrading any of these to an "accepted limitation" to obtain a green status would be exactly
the failure mode the release taxonomy exists to prevent.

---

## 5. Most important next action

**Purchase or request an API-Football plan that allows `page > 3`, then run**

```powershell
python tools/ingest_api_football.py players --league 39 --season 2023 --resume
```

and re-run the coverage endpoint. The ingestion resumes from page 4, the coverage status moves
from `BLOCKED_BY_PLAN` to `COMPLETE` when the declared 51 pages are reached, and the player
universe, the API totals and every UI count move together.

In parallel, the missing transfer fixtures (`data/bronze/open-transfers/`) unblock the five
transfer tests and give the market family something to rank.

---

## 6. Related documents

- `docs/FEATURE_INVENTORY.md` — every feature, its data source, its tests and its status
- `docs/SIDEBAR_MODULE_ACCEPTANCE_MATRIX.md` — per-module acceptance contract and defect log
- `docs/ROUTE_API_COVERAGE.md` — route → API → service → persistence → test
- `docs/CROSS_MODULE_E2E_TESTS.md` — the eight cross-module workflows
- `docs/END_TO_END_VALIDATION.md` — commands and raw results
- `docs/DATA_COVERAGE_REPORT.md` — provider/competition/season/player coverage
- `docs/LLM_PROVIDER_VALIDATION.md` — live Groq inference, status endpoint, fallbacks
- `docs/KNOWN_LIMITATIONS.md` — every open limitation with its blocker
