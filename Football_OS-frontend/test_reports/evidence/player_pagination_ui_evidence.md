# Player pagination — live UI evidence (2026-10-21)

Environment: local stack, identity service + dev gateway + analytics API + React UI.
Database: `fios` (PostgreSQL container `fios_pg`). No secrets are included.

## Dashboard

| Signal | Value |
|---|---|
| Players in scope | **109** (`canonical index · server total`) |
| Clubs | 480 |
| Matches | 20 |
| Copilot model | **Groq** · `AVAILABLE` · streaming verified |

The dashboard previously counted `players.data.length` from `getPlayers({ limit: 50 })`,
so it displayed 50 regardless of the database. It now reads `total` from
`GET /api/v1/players/search`.

## Player discovery (`/players`)

Observed through the rendered DOM after the fix:

| Requested state | Badge | Indicator | Rows |
|---|---|---|---|
| Default | `1–25 / 109` | `Page 1 of 5 · 25 shown` | 25 |
| Click Next → page 2 | `26–50 / 109` | `Page 2 of 5 · 25 shown` | 25 |
| Click Next → page 3 | `51–75 / 109` | `Page 3 of 5 · 25 shown` | 25 |
| Search `Akanji` | `1–1 / 1` | `Page 1 of 1 · 1 shown` | 1 |
| Position `D` | `1–20 / 20` | `Page 1 of 1 · 20 shown` | 20 |
| Page size 50, page 2 | `51–100 / 109` | `Page 2 of 3 · 50 shown` | 50 |

Page 3 (25/page) began with `J. Aguilar` and ended with `M. Akanji`.
Page 2 (50/page) began with `J. Aguilar`, ended with `Thiago Silva`, and included
`M. Akanji`. A repeated API call returned the same ordered IDs (stable sort).

Full-page screenshot: `players_page_2_of_3_51-100.png`.
It visibly shows `51–100 / 109`, `Page 2 of 3 · 50 shown`, and rows including
M. Akanji, Mohamed Salah, Rodri, and Thiago Silva.

## Player profile beyond the first 50

Clicked `M. Akanji` from page 3 and opened
`/players/2ca6252c-128a-4da8-90da-a22194441fe8`.

Rendered profile:

- Name: **M. Akanji**
- Position: Defender
- Nationality: Switzerland
- Minutes: **2514**
- Goals: **2**
- Assists: **0**
- Rating: **7.27931**

Screenshot: `player_M_Akanji_profile.png`.

## Copilot and decision intelligence

`/copilot` rendered `GROQ (OPENAI/GPT-OSS-120B) · AVAILABLE · STREAMING VERIFIED`
and `Context passed to the model: 15 of 109 canonical players (server total; the
model receives a bounded sample, not the whole index)`.

A live prompt streamed a grounded response that included a recruitment decision
for `A. Danjuma` (Inside Forward, tactical fit 68.0%, estimated fee €13,200,000,
risk MEDIUM) and a summary of the 10 players visible to the model. This confirms
the Groq gateway and the existing decision-intelligence path still work after the
player-pagination changes.

## Backend contract evidence

`api_player_evidence.json` records the same run through the real ASGI app with a
signed admin token:

- `GET /api/v1/players/search?page=1&page_size=25` → `total=109`, `total_pages=5`, 25 items.
- `GET /api/v1/players/search?page=3&page_size=25` → 25 items, 51–75.
- `GET /api/v1/players/search?q=Akanji` → `total=1`, `M. Akanji`.
- `GET /api/v1/players/facets` → `total_players=109`.
- `GET /api/v1/players?limit=100` → legacy array shape, 100 items.
- Invalid `page=0`, `page_size=101`, unknown `sort_by` → HTTP 422.

## Automated regression tests

Frontend (`CI=true yarn test --watchAll=false --runInBand`):

- `src/pages/PlayerSearchPage.test.js` — 3 tests: backend total and rows beyond 50,
  no stale page label while the next page loads, and whole-index search from page 1.
- `src/lib/playerPagination.test.js` — 5 tests: server total, page 3 range,
  short final page, returned-page precedence, empty result.

Backend:

- `tests/integration/test_player_pagination_api.py` — paginated contract, later
  pages, totals, search outside page 1, filters, invalid params, duplicates.
- `tests/integration/test_ingestion_pagination.py` — page traversal, resume,
  record counts, provider plan limits, idempotent normalization.
- `tests/unit/test_provider_errors.py` — provider error classification.
- `tests/unit/test_llm_registry.py` — active provider status resolves the
  canonical provider name after verification.

## Provider limitation

`GET /api/v1/players/coverage` reports the league-39/2023 ingestion as
`BLOCKED_BY_PLAN`:

- declared total pages: **51**
- completed pages: **3** (60 records)
- plan maximum page: **3**
- provider error: `Free plans are limited to a maximum value of 3 for the Page parameter`

The ingestion does not claim completeness beyond page 3 and does not bypass the
subscription limit. The canonical database still holds 109 players from all
ingested scopes, all of which are now reachable and paginated in the UI.
