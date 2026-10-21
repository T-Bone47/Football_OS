# Database Expansion Baseline

**Phase 0 audit — Football Intelligence OS, global player database expansion**
Audit date: 2026-10-21 · Auditor: expansion task (read-only audit, no data modified)

Every number below was produced by an actual query against the running system or a live
provider response. Nothing is estimated. Commands are given so each figure can be
reproduced.

---

## 1. Environment under audit

| Component | Value | How it was verified |
|---|---|---|
| Repo root | `Football_OS-main-remediated-v2/Football_OS-main` (not a git repo; all work uncommitted) | directory listing |
| PostgreSQL | `fios_pg` container, PostgreSQL 16.15, host port 55432, databases `fios` + `fios_test` | `docker ps`, `SELECT version()` |
| MongoDB | `fios_mongo` container, host port 28017 | `docker ps` |
| API service | `http://localhost:8002` (FastAPI, `apps/api/app/main.py`) | `GET /data-status` |
| Gateway / frontend | `http://localhost:8004` (gateway), `http://localhost:3005` (frontend) | running processes |
| Alembic head | `0016_seed_transfer_capability` (chain `0001→…→0015→32ee69fbf263→0016`) | `database/migrations/versions/` |
| API-Football plan | **Free** — `requests.limit_day = 100`, `x-ratelimit-limit = 10` req/min, `subscription.end = 2027-09-18` | live `GET /status` (response body captured in `docs/evidence/`) |
| StatsBomb | open-data GitHub, no key, no documented request quota | `apps/api/app/providers/statsbomb.py`, 2 prior SUCCESS runs |

Command used for the database figures (repeatable, read-only):

```powershell
docker exec -i fios_pg psql -U fios -d fios -X -q -f <sql-file>
```

---

## 2. Canonical row counts (PostgreSQL, `fios`)

```
players                          109      player_role_profiles            179
player_identities                109      player_tactical_fits              16
clubs                            545      player_contribution_snapshots      0
club_identities                  545      player_intelligence_snapshots     0
competitions                   1242      valuation_models                   0
seasons                           15      valuation_predictions              0
competition_seasons             1243      feature_snapshots                 74
player_season_stats               61      canonical_actions                  0
player_match_stats                 0      transfers                        220
matches                          235      operational_records                0
match_teams                      470      ledger_entries                     0
match_events                      42      ingestion_runs                   102
match_lineups                      0      data_snapshots                    86
match_statistics                   0      provider_capabilities             22
                                              data_sources                     2
```

**Read:** the football entity graph is wide but shallow. 1 242 competitions / 545 clubs /
15 seasons exist, but the *player* layer holds only **109 canonical players**, of which only
**61 player-season rows** exist — all for a single competition-season (Premier League 2023).
`player_match_stats`, `match_lineups` and `match_statistics` are **empty**: no match-level
player evidence has ever been persisted.

---

## 3. Player universe composition

### 3.1 Profile completeness (109 players)

| Field | Present | Absent |
|---|---|---|
| `date_of_birth` | 60 | 49 |
| `nationality` | 60 | 49 |
| `primary_position` | 60 | 49 |
| `club_id` | 60 | 49 |
| `height_cm` / `weight_kg` | 60 | 49 |
| `photo_url` | 60 | 49 |
| `first_name` / `last_name` | 60 | 49 |

**49 of 109 canonical players (45 %) are name-only shells.** They were created by the
transfer normaliser's name fallback (`apps/api/app/normalization/service.py:1355`,
`resolution_method = NAME_EXACT_MATCH`) — the provider payload that produced them carried
no profile fields.

### 3.2 By nationality (top 25 of 26 observed)

`(null) 49` · England 15 · France 8 · Brazil 7 · Netherlands 4 · Spain 3 · Germany 2 ·
Denmark 2 · Portugal 2 · Côte d'Ivoire 1 · Belgium 1 · Morocco 1 · USA 1 · Scotland 1 ·
Ghana 1 · Senegal 1 · Wales 1 · Colombia 1 · Korea Republic 1 · Nigeria 1 · Croatia 1 ·
Switzerland 1 · Zimbabwe 1 · Egypt 1 · Republic of Ireland 1 · Cameroon 1

25 distinct nationalities for 109 players, 49 of them unknown.

### 3.3 By position

`(null) 49` · Defender 20 · Midfielder 16 · Attacker 16 · Goalkeeper 6 · Forward 2

### 3.4 By club / competition-season

* `player_season_stats`: **61 rows, 100 % in one bucket** — competition-season
  `d38f0e36-2531-4789-9d7e-509eb24c23aa` = *Premier League / 2023* / England.
* 60 players carry a club association; 9 clubs are referenced (checked via
  `player_season_stats.club_id`).
* No other competition-season holds a single player-season row — despite 1 243
  competition-seasons existing.

### 3.5 Provider identity mappings

| Provider | identity rows | distinct provider ids | distinct players | duplicate ids |
|---|---|---|---|---|
| `api-football` | 109 | 109 | 109 | **0** |
| `statsbomb` | 0 | 0 | 0 | 0 |
| `football-data-org` | 0 | 0 | 0 | 0 |

`player_identities` has exactly one provider. The `statsbomb` and `football-data-org`
capability rows exist (`provider_capabilities`, 22 rows) but have produced **zero** canonical
player identities.

### 3.6 Transfers (220 rows)

| Provider | rows | with `fee_eur_normalized` | distinct players | with season |
|---|---|---|---|---|
| `api-football` | 220 | 109 | 37 | **0 (all NULL)** |

All 220 transfers carry `source_provider = api-football`; `season_id` is NULL on every row
and `competition_context` is NULL on every row, so transfer history cannot yet be placed on
a time axis. 38 of the 220 records are genuine transfers from the per-player
`/transfers?player=<id>` endpoint; the rest are duplicated/zero-fee entries with distinct
`source_record_id` values.

---

## 4. Provider-side reality (live API-Football probes, 2026-10-21)

All probes used the configured key, 6.6 s spacing, and are reproducible with
`python -m app.providers.diagnostics` / the ad-hoc probe recorded in the test report.

| Probe | Result |
|---|---|
| `GET /status` | plan **Free**, `requests.current = 0`, `limit_day = 100`, `x-ratelimit-limit: 10` |
| `GET /leagues?current=true` | **1 242 leagues**, 1 request, `paging.total = 1` |
| `GET /teams?league=39&season=2023` | 20 teams, 1 request |
| `GET /players?league=39&season=2023&page=1` | `paging.total = 51` → **1 020 player-records** declared for EPL 2023 |
| `GET /players?league=140&season=2023&page=1` | `paging.total = 45` → 900 (La Liga) |
| `GET /players?league=78&season=2023&page=1` | `paging.total = 39` → 780 (Bundesliga) |
| `GET /players?league=135&season=2023&page=1` | `paging.total = 54` → 1 080 (Serie A) |
| `GET /players?league=61&season=2023&page=1` | `paging.total = 43` → 860 (Ligue 1) |
| `GET /players?league=39&season=2023&page=4` | HTTP 200 + `{"errors": {"plan": "Free plans are limited to a maximum value of 3 for the Page parameter"}}` |
| `GET /players?team=<EPL team 0>&season=2023&page=1..3` | 20 rows per page, `paging.total = 4` for that team |
| `GET /players?team=<EPL team 0>&season=2023&page=4` | same plan error → **the page cap is global, not league-specific** |

**Two hard provider limits, both confirmed live:**

1. **Page cap** — any paginated endpoint is capped at `page ≤ 3` on the Free plan. A
   league-scoped player query can therefore never reach its declared 51 pages; only
   3 × 20 = 60 of 1 020 records are addressable through that query shape.
2. **Daily quota** — 100 requests/day. At 20 players per page this caps a full day at
   ~2 000 player-records.

**Reachability analysis (derived from the two limits, not assumed):** a per-**team** query
returns that club's registered players, so `players?team=<id>&season=<year>&page=1..3`
yields up to 60 players per club with the *same* request cost as three league pages, and it
completes the club instead of a slice of the league. This is the only query shape that can
approach club-complete coverage under the cap. It is also *ordered by provider player id
ascending* (verified: page 1 of `league=39&season=2023` returned ids 5, 14, 18 … 130, 133),
so the cap systematically hides the **highest-id** (most recently created) players of each
club. This is a plan limitation and is reported as such, not papered over.

---

## 5. Ingestion state, checkpoints and failures

`ingestion_runs` (102 rows) by provider/endpoint/status:

| Provider | Endpoint | SUCCESS | FAILED | Notes |
|---|---|---|---|---|
| api-football | `players` | 10 (40 records) | 1 | the FAILED run is `page=4, league=39, season=2023` → the plan cap |
| api-football | `teams` | 8 | 0 | produced the 545 clubs |
| api-football | `leagues` | 13 | 0 | produced the 1 242 competitions |
| api-football | `fixtures` | 1 | 5 | produced the 235 matches |
| api-football | `fixtures/events` | 3 | 2 | produced the 42 match events |
| api-football | `fixtures/lineups` | 3 | 2 | produced **0** `match_lineups` rows |
| api-football | `fixtures/players` | 2 | 3 | produced **0** `player_match_stats` rows |
| api-football | `fixtures/statistics` | 2 | 3 | produced **0** `match_statistics` rows |
| api-football | `transfers` | 38 | 0 | produced the 220 transfers |
| api-football | `standings` / `injuries` / `predictions` | 1 each | 0 | not normalised into canonical tables |
| statsbomb | `competitions` | 2 | 0 | catalogue only |
| statsbomb | `matches` | 1 | 0 | no lineups/events ingested for those matches |

* Latest successful ingestion: **2026-10-20 22:27:51 UTC** (`api-football`, `transfers`),
  i.e. ~9.95 h before the audit (`GET /data-status`).
* `data_snapshots`: 86 Bronze artefacts under `data/bronze/<provider>/<resource>/<sha256>.json`.
* `data_sources`: 2 rows (`api-football`, `statsbomb`) — **no licence, attribution,
  redistribution or terms-review columns exist**.
* **There is no checkpoint table, no retry queue and no dead-letter table.** Resume state is
  reconstructed from `ingestion_runs` + `data_snapshots`
  (`apps/api/app/ingestion/service.py:368-418`).
* There is **no scheduler, no worker and no job queue**; Redis is configured but unused, and
  `background_jobs` is an in-memory dict.
* **No provider is health-probed by the running service** — `GET /api/v1/operations/health`
  reports `provider_gateway: UNKNOWN`.

---

## 6. Counts as seen by consumers (backend endpoints)

| Endpoint | Value | Notes |
|---|---|---|
| `GET /data-status` | `canonical_players_count 109`, `canonical_matches_count 235`, `canonical_transfers_count 220`, `schema_version 0016` | matches the DB exactly |
| `GET /api/v1/players/search` | `total 109`, `total_pages 109` at `page_size=1` | server-side total |
| `GET /api/v1/players` (legacy) | array, `limit` default **100**, max 500 | legacy contract, no total |
| `GET /api/v1/players/facets` | 25 nationalities, 5 positions, `total_players 109` | 49 players have no nationality, so 49 players are unfilterable by country |
| `GET /api/v1/players/coverage` | `status BLOCKED_BY_PLAN`, `declared_total_pages 51`, `completed_pages 3`, `accessible_pages 3`, `provider_plan_limit.page_max 3`, `players_with_season_stats 60`, `players_missing_position 49`, `duplicate_provider_ids 0` | the plan cap is surfaced honestly |
| `GET /api/v1/players/roles` | `coverage.qualified_profiles 33`, `insufficient_profiles 76`, `total_players 109` | role model has 179 profile rows in the DB but 33 qualified |
| `GET /api/v1/matches/search` | `total 235` | |
| `GET /api/v1/clubs` | 545 rows, **unpaginated array** | |
| `GET /api/v1/competitions` | 1 242 rows, **unpaginated array** | |

The frontend consumes the same canonical endpoints
(`Football_OS-frontend/frontend/src/lib/footballApi.js`), so frontend and backend totals
agree at 109 players / 235 matches / 220 transfers. No separate, stale player universe is
present in the frontend.

---

## 7. Hardcoded limits, scopes and provider restrictions (audit inventory)

### 7.1 Backend

| Location | Limit |
|---|---|
| `app/api/routes_canonical.py:585` | `/players/search` `page_size` ≤ 1000 declared, clamped to `settings.players_max_page_size` (100) |
| `app/api/routes_canonical.py:598` | `/players/search` default `page_size` 25 |
| `app/api/routes_canonical.py:675` | **`/players/roles` `page_size` default 50, max 100** (a sample, not the universe) |
| `app/api/routes_canonical.py:695` | `/players/roles` accepts at most 100 ids per request |
| `app/api/routes_canonical.py:1057` | legacy `/players` `limit` default 100, max 500 |
| `app/api/routes_canonical.py:895` | `/players/coverage` scans only the **500 most recent** ingestion runs |
| `app/api/routes_canonical.py:1173` | `/matches/search` `page_size` 25, max 100 |
| `app/api/routes_canonical.py:1237` | `/matches` `limit` default 50, max 100 |
| `app/api/routes_canonical.py:1798` | `/players/{id}/similar` `limit` max 50 |
| `app/api/routes_canonical.py:2063`, `:2101` | `/players/{id}/actions` `limit` max 200, internal 500 |
| `app/api/routes_canonical.py:2276`, `:2328` | `/market/transfers` `limit` max 200, internal 10 000 |
| `app/api/routes_canonical.py:2486` | `/market/replacements` `limit` max 50 |
| `app/api/routes_canonical.py:2669` | `/decisions/recruitment` `limit` max 50 |
| `app/config.py:45-46` | `PLAYERS_DEFAULT_PAGE_SIZE=25`, `PLAYERS_MAX_PAGE_SIZE=100` |
| `app/config.py:35`, `:38` | API-Football page delay 6.1 s, `API_FOOTBALL_MAX_PAGES_PER_RUN=200` |
| `app/ingestion/service.py:256-261` | non-API-Football providers fall back to `max_pages = 200` and `request_interval = 0` |
| `app/normalization/service.py:392-394` | **hardcoded league-39 special case** ("Premier League" / "England" / "EPL") in the player normaliser |
| `app/providers/verify_live_endpoints.py:45-50` | probe pinned to season 2023, league 39, date `2026-09-20` |
| `app/providers/statsbomb.py:16` | StatsBomb base URL hardcoded, the `STATSBOMB_*` settings are never read |
| `app/phase11/competition_coverage.py` | hardcoded per-competition coverage profiles (demo-gated) |
| `app/phase16/provider_orchestrator.py:64-117` | hardcoded provider capability seeds; the orchestrator is in-memory and not wired to the real adapters |

### 7.2 Frontend

`footballApi.js:131` `/players` `limit 100` · `:134` `/players/search` `page_size 25` ·
`:157` `/players/roles` `page_size 50` · `:193` `/similar` `limit 10` ·
`CopilotPage.js:53` `page_size 50` · `DecisionPage.js:56` `page_size 100` ·
`SimilarityPage.js:26` `page_size 100` · `SquadPage.js:115` `page_size 100` ·
`TacticalFitPage.js:33` `page_size 100` · `PlayerComparePage.js:83` `page_size 40`.

### 7.3 Provider-side restrictions (live, verified)

* API-Football Free plan: `page ≤ 3` on every paginated endpoint; 100 requests/day;
  10 requests/minute.
* API-Football Free plan season window: 2022–2024 only (documented in
  `docs/DEVELOPMENT_STATUS.md:166-169`).
* `football-data.org`: no token configured (`FOOTBALL_DATA_TOKEN` absent from `.env`),
  capability rows exist but `last_verified` is NULL.
* StatsBomb open data: reachable (2 SUCCESS runs), but only the catalogue and one match
  list have been fetched.
* OpenLigaDB, TheSportsDB, OpenFootball: **no adapter, no client, no code** anywhere in the
  repository — they exist only as hand-typed strings in demo-gated phase modules.

---

## 8. Duplicate candidates and unresolved mappings

* Duplicate `(provider, provider_player_id)` groups: **0**.
* Players with no provider identity: **0**.
* Players without a position: **49**; without nationality: **49**; without club: **49**.
* Name-based identity fallback in use: `NAME_EXACT_MATCH` (transfers) — it matches on
  `Player.name` string equality, which is **not** safe for common names and currently has
  no review queue, no confidence floor and no merge audit trail.
* No alias table, no name-history table, no `normalized_name` column exists anywhere.

---

## 9. Index and constraint audit (Phase 9 input)

| Table | Indexes present | Missing for the target workload |
|---|---|---|
| `players` | **none** (PK only) | `name`, `nationality`, `primary_position`, `club_id`; no index supports `ILIKE '%q%'` or the stable `ORDER BY name, id` |
| `player_identities` | `uq_player_identity_provider_id`, `ix_player_identities_provider_lookup` | `player_id` (reverse lookup is a seq scan) |
| `player_season_stats` | `uq_player_club_comp_season` only | `club_id`, `competition_season_id`, `player_id` |
| `clubs` | **none** | `name`, `country` |
| `matches` | 6 single-column + 2 unique | composite `(competition_season_id, date DESC)` for the match search |

`pg_trgm` 1.6 and `unaccent` 1.1 are **available but not installed** in the container, so a
trigram index on `players.name` is possible without any new infrastructure.

---

## 10. Baseline gaps this task must close

1. **Player universe**: 109 canonical players (60 with full profiles) versus a
   provider-declared 4 640 player-records across the five priority leagues for season 2023
   alone (51+45+39+54+43 pages × 20).
2. **Competition breadth**: exactly one competition-season holds player-season statistics.
3. **Statistics depth**: zero match-level player statistics, zero lineups, zero team match
   statistics. `player_season_stats` metric columns are `NOT NULL DEFAULT 0`, so an
   unmeasured statistic is currently indistinguishable from a measured zero.
4. **Time awareness**: `players.club_id` is a single mutable pointer; no membership or
   transfer time axis exists; all 220 transfers have `season_id = NULL`.
5. **Identity**: no aliases, no normalised names, no review queue, no merge audit trail,
   no cross-provider mapping discipline beyond one provider.
6. **Provenance**: byte-level provenance exists (`data_snapshots`), but there is no
   field-level provenance, no source authority policy and no conflict register.
7. **Ingestion operations**: no checkpoint table, no dead-letter queue, no dry-run, no
   quota-aware stop, no per-competition coverage ledger.
8. **Provider breadth**: only one live provider. `statsbomb` never produced a canonical
   player; `football-data.org` is unconfigured; OpenLigaDB / TheSportsDB / OpenFootball do
   not exist in code.
9. **Country priorities**: no ranking snapshot, no configurable registry. Nationality
   coverage is 25 countries with 49 unknown — there is no "top-20 countries" concept at all.
10. **Coverage reporting**: `/players/coverage` describes one league-season scope only; there
    is no provider×competition×season coverage ledger.

---

## 11. Evidence index

| Artefact | Location |
|---|---|
| Live provider probe (plan, quotas, paging caps) | `docs/evidence/database_expansion/` (this task) |
| Baseline database dumps | `docs/evidence/database_expansion/baseline_*.json` |
| Existing prior evidence | `Football_OS-frontend/test_reports/evidence/`, `docs/verification/` |
| Prior coverage narrative | `docs/DATA_COVERAGE_REPORT.md`, `docs/KNOWN_LIMITATIONS.md` |
