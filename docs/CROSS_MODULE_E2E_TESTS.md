# Cross-Module End-to-End Tests

**Date:** 2026-10-21 · **Stack:** API 8002 / identity 8003 / gateway 8004 / UI 3005 / PostgreSQL `fios`.

The eight workflows below are the cross-module integrations required for a release. Each row
states what was actually executed in this session, in a real browser against the running
stack, and what remains unproven. Nothing here is inferred from a passing unit test alone.

| # | Workflow | Executed? | Evidence | Blocking factor |
|---|---|---|---|---|
| 1 | Player discovery → comparison → similarity → roles | **Partially** | `/players` page 3 loaded (`51–75 / 109`, first `J. Aguilar`, last `M. Akanji`); M. Akanji profile opened (Defender, Switzerland, 2514′, 2G, 0A, rating 7.27931); M. Akanji added to the comparison slot (`2514′ · 2G · 0A`); `/players/similarity` and `/players/roles` load and call their real endpoints | Similarity/roles computation not asserted; `feature_snapshots` holds only 7 rows |
| 2 | Recruitment project → candidates → tactical fit → similarity → shortlist → decision | **Partially** | `POST /api/v1/decisions/recruitment/analyze` returns ranked candidates with explicit exclusions (e.g. *“Position mismatch: candidate plays Attacker (ATT), which does not fulfill required CM slot”*, *“Sample insufficiency: 595 minutes played is below required minimum threshold (600 mins)”*); project list endpoint returns 200 (empty) | No recruitment project exists, so project→candidate→shortlist persistence was not exercised |
| 3 | Replacement planning → compare → risk → market → decision | **Partially** | `GET /api/v1/players/{id}/market-context` → 200 with honest unknowns (`contribution_scores.duels = null`, `total_career_transfers = 0`); `GET /api/v1/players/{id}/transfer-risk` reachable; replacements page loads | `transfers` table is empty → no comparable universe; replacements/opportunities render empty |
| 4 | Opportunity assessment | **Not executable** | `/market/opportunities` loads, returns no rows | `transfers` empty (provider plan) |
| 5 | Watchlist monitoring | **Not executable** | `/watchlists` → 200, empty list; `GET /api/phase10/watchlists/alerts` reachable | No watchlists exist; the add/evaluate path was not exercised to avoid writing production rows |
| 6 | Match intelligence | **Partially** | `/matches` → 200 from 235 canonical matches | Match detail, events, lineups and prediction were not exercised; `player_match_stats` empty |
| 7 | Decision explanation through Groq | **Yes** | Live prompt on `/copilot` returned a grounded recruitment decision for **A. Danjuma** (Inside Forward, tactical fit 68.0 %, estimated fee €13,200,000, risk MEDIUM, evidence status `DECISION_AVAILABLE`) plus a summary of the ten players visible to the model; the model was told the context is *“15 of 109 canonical players”* | Model sees a bounded sample, not the whole index (disclosed in the UI) |
| 8 | Persistence across refresh | **Partially** | Player/pagination state is server-derived; watchlists/shortlists/projects are read from their stores and survive navigation | Write paths were not exercised in this session (see `KNOWN_LIMITATIONS.md`, L7) |

## Regression suites that back these workflows

| Suite | Command | Result |
|---|---|---|
| Player pagination API | `pytest tests/integration/test_player_pagination_api.py` | included in the 57-test regression run — all passed |
| Ingestion pagination + plan limits | `pytest tests/integration/test_ingestion_pagination.py` | passed |
| Squad/market regression (new) | `pytest tests/integration/test_squad_market_regression.py` | 7 passed |
| Provider error classification | `pytest tests/unit/test_provider_errors.py` | passed |
| LLM registry status | `pytest tests/unit/test_llm_registry.py` | passed |
| Decision intelligence | `pytest tests/unit/test_decision_intelligence.py` | passed |
| Canonical API | `pytest tests/integration/test_canonical_api.py` | passed |
| Frontend pagination | `CI=true yarn test --watchAll=false --runInBand` | 2 suites / 8 tests passed |

## Browser evidence artefacts

Stored under `Football_OS-frontend/test_reports/evidence/`:

| File | Content |
|---|---|
| `players_page_2_of_3_51-100.png` | Full-page screenshot of `/players` with page size 50, page 2 of 3, `51–100 / 109`, rows including M. Akanji, Mohamed Salah, Rodri, Thiago Silva |
| `player_M_Akanji_profile.png` | M. Akanji profile (record 75 of 109) with minutes/goals/assists/rating |
| `api_player_evidence.json` | Machine-readable API capture: totals, later pages, stable ordering, facets, legacy list, invalid-parameter status codes, coverage block |
| `player_pagination_ui_evidence.md` | The same evidence in prose, with the automated test list |
