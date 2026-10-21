# Data Source Registry

**Phase 2 evaluation and licensing policy — database expansion**
Evaluated: 2026-10-21 · Registry owner: ingestion layer (`apps/api/app/ingestion/sources.py`)

Every source is registered with its licence, attribution requirement, redistribution
permission and enablement state. The registry is the single place that answers
"may we store and re-serve this data?" — it is consulted before a provider is used,
and it is seeded into `data_sources` (`license`, `license_url`, `attribution`,
`redistribution_allowed`, `enabled`, `terms_reviewed_at`, `notes`).

```powershell
# refresh the registry in the database
$env:PYTHONPATH="apps/api"; python -c "import asyncio; from app.ingestion.sources import seed_sources; ..."
```

---

## 1. Summary

| Source | State | What it actually provides | Licence | Redistribution |
|---|---|---|---|---|
| **API-Football** | enabled | Structured player/team/fixture/statistics/transfer records | Commercial API, Free plan (personal use) | Not permitted — internal analytics only |
| **StatsBomb Open Data** | enabled | Match events, lineups, 360 data for the published competitions | CC BY-NC-SA 4.0 | Not permitted (non-commercial, share-alike) — attribution required |
| **football-data.org** | **disabled** | Fixtures, standings, (limited) squad metadata | Free tier, token required | Not permitted |
| **OpenLigaDB** | **disabled** | German league fixtures, results, standings | Open data, no key | Permitted |
| **TheSportsDB** | **disabled** | Descriptive team/player metadata | Free API tier | Not permitted |
| **OpenFootball** | not implemented | Historical results/fixtures CSVs | Per-dataset (mostly CC0/Public Domain) | Depends on the dataset |
| **soccerdata** | not a source | A wrapper library around existing providers | n/a | n/a |

---

## 2. API-Football (principal structured source)

* Adapter: `apps/api/app/providers/api_football.py` · base URL from
  `API_FOOTBALL_BASE_URL` (default `https://v3.football.api-sports.io`).
* Auth: `x-apisports-key` header from `API_FOOTBALL_KEY` (never logged, never printed).
* **Measured plan limits (live, 2026-10-21, `GET /status`)**:
  * plan `Free`, subscription active until 2027-09-18;
  * `requests.limit_day = 100` — the hard daily budget;
  * `x-ratelimit-limit: 10` requests per minute (the runner paces at 6.5 s);
  * **`page` is capped at 3 on every paginated endpoint** — HTTP 200 with
    `{"errors": {"plan": "Free plans are limited to a maximum value of 3 for the Page parameter"}}`;
  * seasons 2022–2024 are the accessible window.
* **Measured coverage of the five priority leagues, season 2023** (`paging.total` from
  the live API):

  | Competition | Provider id | Pages | Player-records declared |
  |---|---|---|---|
  | Premier League | 39 | 51 | 1 020 |
  | La Liga | 140 | 45 | 900 |
  | Bundesliga | 78 | 39 | 780 |
  | Serie A | 135 | 54 | 1 080 |
  | Ligue 1 | 61 | 43 | 860 |
  | **Total** | | **232** | **4 640** |

* **Reachability consequence.** A league-scoped player query can address at most
  3 × 20 = 60 of its 51 declared pages. A per-**team** query returns the same 20
  records per request but *completes a club* instead of slicing a league, and a
  club's registered players fit in ≤ 3 pages for most clubs. The expansion runner
  therefore plans one scope per club (`players?team=<id>&season=<year>`), which is
  the query shape that maximises the reachable universe inside the plan limit.
* Records are ordered by provider player id ascending, so the page cap hides the
  **highest-id** (most recently created) players of each club. This is a plan
  limitation and is reported as `BLOCKED_BY_PLAN`, never smoothed over.
* **What it does not provide:** a complete player universe, historical transfers
  beyond the free tier, and match-level player statistics for arbitrary fixtures.

## 3. StatsBomb Open Data

* Adapter: `apps/api/app/providers/statsbomb.py` — base URL
  `https://raw.githubusercontent.com/statsbomb/open-data/master/data`
  (the `STATSBOMB_*` settings exist but the adapter does not read them; this is a
  known gap, recorded in the implementation document).
* No key, no documented request quota. Reachability confirmed by the two SUCCESS
  ingestion runs in the baseline (`competitions`, `matches`).
* Provides: competition/season catalogue, matches, lineups (player name, DOB,
  country, position, jersey number, starter flag), events, and 360 data for the
  competitions FIFA published.
* **Licence:** CC BY-NC-SA 4.0 — non-commercial, share-alike, attribution required.
  `redistribution_allowed = false` in the registry.
* **Honest scope claim:** this is *historical research data for the competitions
  FIFA released*. It is not live coverage, it is not the whole StatsBomb corpus, and
  it is not a substitute for a current club-league universe. Every ingested match is
  tracked so the processed subset is always explicit.
* Player identities in StatsBomb are per-match ids; the same human appears under
  different ids in different matches. Cross-match resolution therefore goes through
  the conservative identity resolver (name + DOB + country), never through an
  id-equality assumption.

## 4. football-data.org — evaluated, disabled

* Adapter exists (`apps/api/app/providers/football_data_org.py`) but is **not** in the
  default registry; `FOOTBALL_DATA_TOKEN` is not configured, so the capability rows
  have `last_verified = NULL`.
* Free plan covers a small set of Western European leagues: fixtures, results,
  standings and limited squad metadata — **no detailed player statistics**.
* **Decision:** disabled. It cannot close the player-universe gap on its own, and
  the adapter lacks the envelope/plan-limit error handling API-Football has. It is
  registered with its licence so the decision is auditable, and it can be enabled by
  adding a token.
* Also missing: HTTP-200-with-errors envelope detection (the adapter treats any 200
  as success), pagination handling and a plan-limit check.

## 5. OpenLigaDB — evaluated, disabled

* `https://api.openligadb.de/` needs no key and is reachable.
* It exposes **German league fixtures, results and standings only** — no player
  profiles, no player statistics, no squads.
* **Decision:** disabled for this phase. It cannot add a single player to the
  canonical universe, and the expansion target is the player universe. It remains a
  candidate for a *fixture-completeness* phase, where it would improve the German
  competition's fixture coverage without a token.

## 6. TheSportsDB — evaluated, disabled

* Free tier is available with a public test key; team/player descriptive metadata
  is broad but shallow: missing DOB, ambiguous nationalities, and often stale club
  associations.
* **Decision:** disabled, for two reasons that are not about convenience:
  1. its metadata is weaker than the canonical sources and would have to be
     prevented from overwriting stronger facts (the field-authority rules do allow
     that, but the value is not there yet);
  2. it adds no coverage the priority leagues do not already provide.
* No adapter is implemented while it cannot measurably close a coverage gap —
  implementing one would add surface area without adding coverage.

## 7. OpenFootball — not implemented as a provider

* `github.com/openfootball/awesome-football` aggregates per-competition CSV
  repositories (results, fixtures, squads) with mostly permissive licences.
* It is a *dataset collection*, not an API: each dataset has its own licence,
  season coverage and update cadence, and several of them are community-maintained
  with irregular history.
* **Decision:** not implemented in this phase. The canonical priority (the live
  player universe for the five leagues) is served by API-Football; OpenFootball is
  the natural source for a *historical results* phase, where its per-dataset
  licences can be reviewed one by one. Importing it now would import fixtures for
  seasons the platform has no players for — a scope that adds rows without adding
  evidence.

## 8. soccerdata — not a data source

* `soccerdata` is a wrapper library that scrapes or calls existing providers
  (WhoScored, Understat, FBref, ESPN, FotMob, …) behind a common interface.
* Importing it would mean importing **someone else's** provider without their
  permission and without their licence — the exact failure mode the licensing rules
  exist to prevent.
* **Decision:** excluded. Where a dataset is used, the *original* provider is
  named as the source and its licence is recorded.

---

## 9. Licensing and exclusion rules enforced in code

| Rule | Where |
|---|---|
| A disabled source is never ingested from | `data_sources.enabled` (registry) |
| Redistribution permission is recorded per source | `data_sources.redistribution_allowed` |
| Attribution text is stored per source | `data_sources.attribution` |
| Terms review date is stored per source | `data_sources.terms_reviewed_at` |
| Source-native payloads are always kept (Bronze) | `data_snapshots`, `data/bronze/<provider>/<resource>/<sha256>.json` |
| Derived values keep their source reference | `field_provenance` (provider, provider id, transformation, source hash) |
| Provider disagreements are preserved, not overwritten | `source_conflicts` |

## 10. Provider id discipline

A provider id is **never** assumed to equal a canonical id or another provider's id:

* `player_identities (provider, provider_player_id)` — unique per provider.
* `club_identities (provider, provider_club_id)` — unique per provider.
* `competition_identities (provider, provider_competition_id)` — added by migration
  `0018`; before that, competition-seasons could not be linked to the canonical
  league at all and the player normaliser had to invent a placeholder name.

Cross-provider matching of the same human goes through
`apps/api/app/identity/resolution.py`, which requires supporting evidence and
queues anything ambiguous for review.
