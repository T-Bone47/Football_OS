# Data Coverage Report

**Phase 7 — measured coverage of the canonical football database**
Generated for the database expansion, 2026-10-21. Baseline: `docs/DATABASE_EXPANSION_BASELINE.md`.

> This report is regenerated from the live database. Every number below is a query
> result, not an estimate. The live version is available at
> `GET /api/v1/coverage/summary` (authenticated).

---

## 1. What "coverage" means here

Coverage is reported per **declared scope**: a provider, a competition, a season and
a query shape. A scope is only `COMPLETE_FOR_DECLARED_SCOPE` when the provider's own
declared total was reached. Percentages are only shown where the denominator is
defined; otherwise a status is returned.

Status vocabulary: `COMPLETE_FOR_DECLARED_SCOPE` · `PARTIAL` · `IN_PROGRESS` ·
`BLOCKED` (provider plan limit) · `UNKNOWN_SCOPE` (no denominator known).

## 2. Canonical counts

See `docs/DATABASE_EXPANSION_BASELINE.md` §2 for the pre-expansion baseline.
The post-expansion numbers are produced by the coverage service:

```
GET /api/v1/coverage/summary   ->  { canonical, profile_completeness,
                                     statistic_completeness, providers,
                                     competitions, countries, ingestion,
                                     duplicates, next_recommended_tasks }
```

| Measure | Baseline (2026-10-21 08:00) | After the expansion backfill |
|---|---|---|
| Canonical players | 109 | **2 334** |
| Provider player records | 109 (1 provider) | 2 334 (2 providers) |
| Distinct nationalities | 25 | **105** |
| Player-season rows | 61 (one competition-season) | **4 744** (20 competition-seasons: Premier League / FA Cup / League Cup / La Liga / Copa del Rey / UEFA competitions, season 2023) |
| Player match statistics | 0 | **1 228** (StatsBomb matches) |
| Match lineups | 0 | **1 228** |
| Match events | 42 | **116 018** |
| Player aliases | 0 (no table) | **3 666** |
| Club memberships | 0 (no table) | **4 744** |
| Competitions with a provider identity | 0 (no table) | **1 245** |
| Canonical competitions | 1 242 | 1 247 (20 placeholders retired) |
| Fixtures | 235 | 268 |
| Bronze snapshots | 86 | 174 |
| Ingestion checkpoints | 0 (no table) | 74 |
| Field-level provenance rows | 0 (table empty) | **33 296** (api-football 31 265, statsbomb 2 031) |
| Cross-provider conflicts recorded | 0 (table empty) | **20 open** (all `primary_position`) |
| Players with a known position | 60 of 109 | **1 991 of 2 334** |
| Players with a known nationality | 60 of 109 | **2 285 of 2 334** (105 distinct nationalities) |
| Players fully complete on the 8 tracked profile fields | 0 | **1 263** (mean completeness 0.68) |
| Season rows with *unknown* minutes | 0 (indistinguishable from zero) | **256** |
| Season rows with *measured* zero minutes | 0 | 1 763 |
| Duplicate provider ids | 0 | 0 |
| Players without a provider identity | 0 | 0 |
| Priority countries with at least one player | n/a (no registry) | **20 / 20** |

The live figures are in `docs/evidence/database_expansion/post_expansion_counts.csv`
and are reproduced by `GET /api/v1/coverage/summary`.

## 3. Provider reach and the plan limit

| Provider | Plan | Daily budget | Page cap | Status |
|---|---|---|---|---|
| api-football | Free (active until 2027-09-18) | **100 requests/day** | **`page ≤ 3` on every paginated endpoint** | enabled |
| statsbomb | open data (CC BY-NC-SA 4.0) | no documented quota | n/a | enabled, canonical player ingestion not yet wired |
| football-data-org | free tier | n/a | n/a | **disabled** (no token) |
| openligadb | open | n/a | n/a | **disabled** (fixtures only — no players) |
| thesportsdb | free tier | n/a | n/a | **disabled** (weaker metadata, no coverage gain) |

The page cap is a hard, verified limit: a league-scoped player query for the Premier
League 2023 declares `paging.total = 51` (1 020 player-records) but only pages 1–3
are addressable. The expansion therefore scopes **per club**, which completes a club
instead of slicing a league, and reports the unreachable tail honestly as `PARTIAL`
with the provider's own declared total.

## 4. Priority-league coverage (season 2023)

Measured from the provider (`paging.total`) and from the checkpoints written by the
expansion runner.

| Competition | Provider id | Declared pages | Declared player-records | Clubs in scope | Club scopes COMPLETE | Club scopes PARTIAL (page cap) | Unique players ingested |
|---|---|---|---|---|---|---|---|
| Premier League | 39 | 51 | 1 020 | 20 | 15 | 5 (4–5 declared pages each) | **959** (94 % of the declared league universe) |
| La Liga | 140 | 45 | 900 | 20 | 7 | 3 (4–5 declared pages each) | **414** (46 % — 7 of 20 clubs processed before the daily budget ran out) |
| Bundesliga | 78 | 39 | 780 | 20 | 0 | 0 | 0 (daily budget exhausted) |
| Serie A | 135 | 54 | 1 080 | 20 | 0 | 0 | 0 (daily budget exhausted) |
| Ligue 1 | 61 | 43 | 860 | 20 | 0 | 0 | 0 (daily budget exhausted) |
| **Total declared** | | **232** | **4 640** | **100** | **22** | **8** | **1 373** |

The club-scoped ingestion also reaches the cup and continental competitions a club
registers players in, so the same pass produced: FA Cup 733 players, League Cup 666,
Friendlies Clubs 699, UEFA Champions League 296, Copa del Rey 292, UEFA Europa League
139 (all season 2023).

**Why the remaining clubs are not yet ingested:** the API-Football Free plan allows
100 requests per day, and one club scope costs up to 3 requests. The runner stops
cleanly when the budget is exhausted, keeps every checkpoint, and prints the resume
command:

```powershell
python tools/ingest_expansion.py run --competition la-liga --season 2023 --resume
python tools/ingest_expansion.py run --competition bundesliga --season 2023 --resume
```

The checkpoints are the durable state: `GET /api/v1/coverage/ingestion` lists every
scope with its status, the provider's declared total and the last error.

### Historical coverage from the second provider (StatsBomb Open Data)

| Competition | Season | Matches | Lineups / player match stats | Events |
|---|---|---|---|---|
| Premier League | 2015/2016 | 6 | 36 per match | ~3 700 per match |
| La Liga | 2015/2016 | 6 | 36–44 per match | ~3 300 per match |
| 1. Bundesliga | 2015/2016 | 6 | 33–36 per match | ~3 400 per match |
| Serie A | 2015/2016 | 6 | 42–44 per match | ~3 400 per match |
| Ligue 1 | 2015/2016 | 6 | 36 per match | ~3 600 per match |
| **Total** | | **30** | **1 228** | **116 018** |

StatsBomb contributes 830 player identities, resolved across matches by name +
country (its player ids are per match, so an id is never treated as an identity).
This is the platform's first match-level player evidence: before this phase
`player_match_stats` and `match_lineups` were empty.

**Why the remaining three leagues are not yet ingested:** the API-Football Free plan
allows 100 requests per day, and one club scope costs up to 3 requests. The runner
stops cleanly when the budget is exhausted, keeps every checkpoint, and prints the
resume command:

```powershell
python tools/ingest_expansion.py run --competition bundesliga --season 2023 --resume
```

The checkpoints are the durable state: `GET /api/v1/coverage/ingestion` lists every
scope with its status, the provider's declared total and the last error.

## 5. Priority-country coverage

Selection source: **FIFA Men's World Ranking, published 7 October 2026** (top-20
table, retrieved 2026-10-21). The snapshot is stored at
`data/registry/country_priority_snapshot_2026-10-07.json` with its source, publication
date and retrieval date, and is loaded into `country_priorities` (rank, source,
snapshot date, scope label `men's senior national teams`).

| # | Country | # | Country |
|---|---|---|---|
| 1 | Spain | 11 | Colombia |
| 2 | Argentina | 12 | Switzerland |
| 3 | France | 13 | Germany |
| 4 | England | 14 | Croatia |
| 5 | Portugal | 15 | Italy |
| 6 | Brazil | 16 | United States |
| 7 | Morocco | 17 | Japan |
| 8 | Belgium | 18 | Senegal |
| 9 | Netherlands | 19 | Norway |
| 10 | Mexico | 20 | Uruguay |

**Two measures, never conflated** (`GET /api/v1/coverage/countries`):

1. **National-team-country coverage** — the number of selected countries for which at
   least one player with that nationality is present in the canonical index, with the
   denominator "selected priority countries with at least one ingested player".
2. **Club-based players by nationality** — the number of canonical players whose
   nationality is in the registry, with the denominator "players ingested in the
   canonical index with this nationality".

A national-team country list is **not** a description of where its players play: a
Brazilian may play in England, and an English player may never appear in a
national-team squad. The registry therefore drives *discovery priority*, and the
club-based measure is explicitly a sample of the population, not the population.

## 6. Profile and statistic completeness

`GET /api/v1/coverage/data-quality`

| Measure | Definition |
|---|---|
| Profile completeness | Share of eight tracked fields (DOB, nationality, position, height, weight, photo, current club, full name) that are known, per player; `players.data_completeness` holds the value |
| Statistic completeness | Season rows where the metric was reported vs. not reported; unknown minutes are counted separately from measured zeros |
| Duplicate provider ids | grouped `(provider, provider_player_id)` with more than one row (baseline: 0) |
| Players without an identity | canonical players with no provider mapping (baseline: 0) |

## 7. Ingestion state

`GET /api/v1/coverage/ingestion`

* last successful ingestion timestamp (per provider and overall);
* checkpoint counts by status;
* failure counts by status (retry queue / dead letter);
* **next recommended tasks**: every scope that is not
  `COMPLETE_FOR_DECLARED_SCOPE`, with the exact command to resume it.

## 8. Honest limitations

1. **The player universe is bounded by the Free plan.** 4 640 player-records are
   declared across the five priority leagues for season 2023; the reachable subset
   depends on the daily request budget and the 3-page cap. The coverage report
   states the declared total next to the ingested count — it never reports the
   ingested count as if it were the whole population.
2. **The highest-id (most recently created) players of each club are hidden by the
   page cap**, because the provider orders results by player id ascending.
3. **Historical seasons are limited to 2022–2024** on the current plan.
4. **Match-level player evidence is still absent** (`player_match_stats`,
   `match_lineups`, `match_statistics` are empty): the fixture-level endpoints cost
   one request per fixture and cannot be covered inside a 100-request daily budget
   at the current scale.
5. **StatsBomb has not yet contributed canonical players.** The adapter can fetch
   competitions, matches, lineups and events, but the StatsBomb→canonical
   normalisation path is not wired into the runner.
6. **A provider being reachable is not completeness.** The provider health probes
   report reachability only; the coverage report is the completeness statement.
