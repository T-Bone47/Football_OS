# Sidebar module sweep — 2026-10-21

Live browser sweep of every route in `src/App.js` against the running local stack
(API 8002 · identity 8003 · gateway 8004 · UI 3005 · PostgreSQL `fios`).

For each route the DOM was inspected and **every** HTTP request (XHR *and* fetch) was
captured, so backend refusals (4xx/5xx) and transport failures are visible rather than assumed.

## Result summary

| Route | API calls | 4xx/5xx | Transport failures | Module state shown |
|---|---|---|---|---|
| `/dashboard` | 7 | 0 | 0 | 109 players / 480 clubs / 20 matches, Groq AVAILABLE |
| `/players` | 6 | 0 | 0 | `1–25 / 109`, page 1 of 5 |
| `/players/compare` | 4 | 0 | 0 | server-side picker, total 1 of 1 for "Akanji" |
| `/players/similarity` | 5 | 0 | 0 | renders |
| `/players/roles` | 85 | 0 | 0 | renders (N+1 fan-out, see limitations) |
| `/tactical/fit` | 7 | 0 | 0 | renders |
| `/recruitment/projects` | 6 | 0 | 0 | "No recruitment projects yet" |
| `/watchlists` | 6 | 0 | 0 | "You have no watchlists yet" |
| `/decisions` | 8 | 0 | 0 | candidate evaluation with exclusion reasons |
| `/market` | 8 | 0 | 0 | renders; market data is empty |
| `/market/valuation` | 8 | 0 | 0 | renders |
| `/market/opportunities` | 9 | 0 | 0 | empty (no transfer feed) |
| `/market/replacements` | 8 | 0 | 0 | empty (no transfer feed) |
| `/market/risk` | 9 | 0 | 0 | renders |
| `/matches` | 5 | 0 | 0 | renders |
| `/squad/builder` | 8 | 0 | 0 | **squad analysis renders (was HTTP 500)** |
| `/squad/simulator` | 6 | 0 | 0 | **200 (was HTTP 500)** |
| `/squad/scenarios` | 6 | 0 | 0 | **200 (was HTTP 500)** |
| `/scenarios` | 8 | 0 | 0 | "NO FORECAST IS PRODUCED" |
| `/decision-lab` | 26 | 9 × 409 | 0 | **banner: "Module disabled on real data"** (was: 3 failed requests, empty page) |
| `/outcome-intelligence` | 40 | 18 × 409 | 0 | **banner: "9 of 9 endpoints refused the request"** |
| `/operations` | 8 | 2 × 409 | 0 | shows the demo-gate reason |
| `/operations/global` | 28 | 12 × 409 | 0 | global demo banner |
| `/intelligence/continuous` | 32 | 7 × 409 | 0 | **banner: "7 of 7 module endpoints refused"** (was: 7 failed requests, empty page) |
| `/research` | 36 | 0 | 0 | renders |
| `/research/data` | 36 | 0 | 0 | renders |
| `/copilot` | 5 | 0 | 0 | `GROQ (OPENAI/GPT-OSS-120B) · AVAILABLE · STREAMING VERIFIED` |
| `/system/data-quality` | 8 | 0 | 0 | live probes |
| `/players/:playerId` | 30 | 0 | 0 | **all 13 sub-calls 200** (3 were 400/500) |

`409` responses are the deliberate `DEMO_ONLY` gate on the Phase 11–14 routers: those modules
compute from built-in demonstration figures and refuse to run on real data. The UI now states this
instead of presenting an empty module as "no data".

## Screenshots

| File | Content |
|---|---|
| `players_page_3_of_5_51-75.png` | `/players` page 3 of 5 — badge `51–75 / 109`, 25 rows from `J. Aguilar` to `M. Akanji` |
| `players_page_2_of_3_51-100.png` | `/players` with page size 50, page 2 of 3 — `51–100 / 109` |
| `player_M_Akanji_profile.png` | profile of record 75 (M. Akanji): 2514′ / 2G / 0A / 7.27931 |
| `squad_builder_after_500_fix.png` | squad builder after the fix: squad quality 59 %, role coverage 91 % (10 of 11 slots), tactical fit 53 %, depth risk 35 % HIGH, average age and estimated value shown as “—” because they are unknown |
