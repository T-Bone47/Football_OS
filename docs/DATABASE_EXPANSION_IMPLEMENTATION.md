# Database Expansion — Implementation

**Phase 1 implementation record** · repo: `Football_OS-main-remediated-v2/Football_OS-main`

This document describes what was implemented for the database expansion, where it
lives, and which guarantees it makes. The baseline it starts from is
`docs/DATABASE_EXPANSION_BASELINE.md`; the source decisions are in
`docs/DATA_SOURCE_REGISTRY.md`; the data-quality rules are in
`docs/DATA_QUALITY_AND_ENTITY_RESOLUTION.md`.

---

## 1. Schema changes

Two migrations, both additive (no destructive step, no truncation):

### `0017_database_expansion`

| Object | Purpose |
|---|---|
| `players.display_name`, `secondary_position`, `country_of_birth`, `preferred_foot`, `active_status`, `name_normalized`, `identity_confidence`, `data_completeness`, `last_synced_at` | The profile fields a multi-source world needs, plus a measured completeness score |
| `player_identities.source_url`, `source_record_hash`, `review_status`, `first_seen_at`, `last_seen_at` | Provenance and lifecycle on the provider mapping |
| `player_season_stats` metric columns → **NULLABLE** | A statistic the provider never reported is unknown, not zero |
| `player_aliases` | Every observed spelling of a player, per provider |
| `player_club_memberships` | Time-bounded club registrations (history is never overwritten) |
| `ingestion_checkpoints` | Durable, resumable ingestion state per provider scope |
| `ingestion_failures` | Retry queue + dead-letter records |
| `field_provenance` | Per-field provider provenance (value, transformation, source hash) |
| `source_conflicts` | Unresolved provider disagreements |
| `identity_review_queue` | Ambiguous cross-provider identity candidates |
| `country_priorities` | Dated, configurable country-priority registry |
| `data_sources` + licence columns | `license_url`, `attribution`, `redistribution_allowed`, `enabled`, `terms_reviewed_at`, `notes` |
| 13 new indexes | `players(name/nationality/primary_position/club_id)`, a **pg_trgm GIN index on `players.name`** for the substring search, `player_identities(player_id)`, `player_season_stats(club_id/competition_season_id/player_id)`, `clubs(name/country)`, `matches(competition_season_id, date)` |

**The zero/unknown backfill.** The migration nulls a season statistic only when the
source-native block in `raw_stats` has no corresponding key *and* the stored value is
0. A measured zero (the provider explicitly sent `0`) is preserved. On the baseline
data this turned 5 rows from "0 minutes" into "minutes not reported" and left 10 rows
as measured zeros.

### `0018_competition_identities`

`competitions` is provider-neutral, so the provider's own competition id had no
mapping table: competition-seasons could not be linked to the canonical league, and
the player normaliser had to fall back to a hardcoded league-39 special case
("Premier League"/"England"/"EPL") for exactly one league. `competition_identities
(provider, provider_competition_id) → competition_id` removes that special case; the
normaliser now resolves any provider league id through the mapping.

**Parity gate:** `python tools/check_orm_migration_parity.py` → *0 drift, 3 warnings*
(the warnings are pre-existing `op.execute` DDL in `0015` plus the `CREATE EXTENSION`
in `0017`). `alembic check` → *No new upgrade operations detected*.

---

## 2. Ingestion engine

| Component | File | What it does |
|---|---|---|
| Scope planner | `apps/api/app/ingestion/scope.py` | Builds the ordered list of provider scopes from configuration (`data/registry/priority_leagues.json`) and the dated country snapshot. Discovers the club list of a scope from the most recent successful `teams` snapshot. |
| Checkpoint store | `apps/api/app/ingestion/checkpoints.py` | Durable per-scope state; the scope key is the provider parameters **minus** the page, so a checkpoint can never be reused for a different league, season or club. |
| Country registry | `apps/api/app/ingestion/country_priorities.py` | Loads a dated ranking snapshot into `country_priorities`; administrators change the selection by pointing the loader at another file. |
| Source policy | `apps/api/app/ingestion/sources.py` | Licence, attribution, redistribution permission and enablement per source. |
| Runner | `tools/ingest_expansion.py` | Plan / dry-run / execute, quota-aware, checkpoint-aware, machine-readable summary. |
| StatsBomb runner | `tools/ingest_statsbomb.py` | Ingest a competition-season of the open data: matches, lineups, events. No key, no request quota. |
| StatsBomb normaliser | `apps/api/app/normalization/statsbomb.py` | StatsBomb → canonical matches, lineups, player match statistics and match events. |
| Identity services | `apps/api/app/identity/names.py`, `resolution.py` | Name normalisation (accent- and order-insensitive) and conservative cross-provider resolution. |
| Coverage service | `apps/api/app/coverage/service.py` | The measured coverage view and the next recommended tasks. |

### Runner guarantees

* **Plan before work.** `python tools/ingest_expansion.py plan --competition X --season Y --dry-run`
  prints the scopes, the estimated request count and the current state of each scope
  **without a single provider call or database write**.
* **Quota awareness.** The runner reads the provider's own `/status` (plan,
  `requests.current`, `requests.limit_day`) before the run and tracks the requests it
  makes. When the daily budget is exhausted it stops cleanly, marks the remaining
  scopes `SKIPPED_DAILY_BUDGET_EXHAUSTED` and prints the resume command.
* **Resumability.** Every scope writes a checkpoint after each page. A re-run with
  `--resume` continues from the stored page; scopes already
  `COMPLETE_FOR_DECLARED_SCOPE` are skipped unless `--force` is given.
* **Honest completeness.** A scope is only `COMPLETE_FOR_DECLARED_SCOPE` when the
  provider's own declared page total was reached. A scope stopped by the page cap is
  `PARTIAL`; a scope stopped by the plan limit is `BLOCKED_BY_PLAN`; a scope that
  failed is `FAILED`. A successful first page is never "complete".
* **Machine-readable output.** The runner prints one JSON document with per-scope
  status, request counts, records fetched, records normalised, the provider budget
  before and after, and the resume command.

### Query shape under the Free plan

The API-Football Free plan caps `page` at 3 on every paginated endpoint, so a
league-scoped player query can address at most 60 of its 51 declared pages. The
planner therefore issues **one scope per club** (`players?team=<id>&season=<year>`),
which yields the same 20 records per request but *completes a club* instead of
slicing a league. Where a club declares more than three pages the scope is reported
as `PARTIAL` with the provider's own declared total — the missing tail is never
presented as covered.

---

## 3. Normalisation changes

* `transform_api_football_players` now emits **nullable** season statistics
  (`appearances`, `lineups`, `minutes`, `goals`, `assists`, `conceded`) and preserves
  the provider's two spellings of "appearances". It also collects every observed
  spelling of the player (short name, full name, "Last, First") as alias candidates.
* `upsert_player_with_status` fills missing profile fields, keeps
  `name_normalized`, `display_name`, `data_completeness` and `last_synced_at` current,
  and stores the observed spellings in `player_aliases`.
* `normalize_players_payload` writes one `player_club_memberships` row per
  (player, club, competition-season) registration, with the season recorded in the
  row's provenance, and marks the newest observed season as the current registration.
  A later club never erases an earlier one.
* `resolve_competition` replaces the hardcoded league-39 branch with a lookup in
  `competition_identities`; an unmapped provider competition id gets a clearly
  labelled placeholder competition **and** a mapping row, so the id is never lost.

---

## 4. Consumer changes (truthfulness)

| Consumer | Before | After |
|---|---|---|
| `decisions/recruitment.py` | `select(Player).limit(100)` with no order — an arbitrary slice of the table | evidence-scoped query (players that actually have season statistics) ordered by observed minutes, then name, then id |
| `decisions/recruitment.py` | missing statistics became **900 minutes / 10 appearances** | observed minutes/appearances, `0` when nothing was observed, and `evidence_status = INSUFFICIENT_DATA` + `evidence_notes` on the assessment |
| `decisions/recruitment.py` | market value from a hardcoded cohort table (8/14/18/22 M€) | the canonical `valuation_predictions` record, or `null` with `affordability_status = UNAVAILABLE` |
| `decisions/replacement.py` | `.limit(80)`, 1 000 / 12 fabricated | same treatment as recruitment |
| `decisions/hard_constraints.py` | unknown value compared against a budget | a constraint that cannot be evaluated is reported in `unevaluated_checks`, never silently passed or failed |
| `decisions/schemas.py` | `DimensionMarket.estimated_value_eur` required | optional; `affordability_status` defaults to `UNAVAILABLE`; `financial_risk` optional |
| `squad/service.py` | an empty club squad was replaced by arbitrary players from other clubs | an empty squad stays empty |
| `market/dataset.py`, `market/risk.py` | `sum(s.minutes …)` broke on a null minute | sums over observed values only |
| `normalization/transformers.py` | `… or 0` turned "not reported" into zero | nullable statistics |

**Documented contract change.** `MultiDimensionalCandidateAssessment` gains
`evidence_status` and `evidence_notes`; `HardConstraintResult` gains
`unevaluated_checks`; `DimensionMarket`'s monetary fields and `DimensionRisk.
financial_risk` become optional. Existing consumers that ignore unknown fields keep
working (all response models use `extra="ignore"`), but a client that assumed a
non-null valuation must now handle `null` and `affordability_status = UNAVAILABLE`.

---

## 5. New API surface

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/coverage/summary` | The full measured coverage view |
| `GET /api/v1/coverage/providers` | Per-provider identity counts, last success, checkpoint status |
| `GET /api/v1/coverage/competitions` | Per competition-season player coverage |
| `GET /api/v1/coverage/countries` | Priority-country coverage with the ranking snapshot and the denominator |
| `GET /api/v1/coverage/ingestion` | Runs, checkpoints, failures and the next recommended tasks |
| `GET /api/v1/coverage/data-quality` | Profile/statistic completeness and the duplicate state |

All routes require an authenticated principal, like the rest of the API.

---

## 6. Configuration

| File | Purpose |
|---|---|
| `data/registry/priority_leagues.json` | The five mandatory competitions with their provider ids and default seasons |
| `data/registry/country_priority_snapshot_2026-10-07.json` | The dated FIFA Men's World Ranking snapshot (20 countries) with source, publication date and retrieval date |
| `apps/api/app/ingestion/sources.py` | Licence/attribution/enablement policy per source |

`.env.example` gained no new secret-bearing keys: the expansion reuses the existing
`API_FOOTBALL_KEY` and adds no new provider credentials. The optional providers stay
disabled until a key is supplied.

---

## 7. Commands

```powershell
# 0. schema
$env:DATABASE_URL="postgresql+asyncpg://fios:fios@localhost:55432/fios"
$env:PYTHONPATH="apps/api"
python -m alembic upgrade head
python tools/check_orm_migration_parity.py

# 1. plan (no provider calls, no writes)
python tools/ingest_expansion.py plan --competition premier-league --season 2023 --dry-run

# 2. backfill (quota-aware, resumable)
python tools/ingest_expansion.py run --competition premier-league --season 2023 --resume

# 3. resume after the daily quota resets
python tools/ingest_expansion.py run --competition premier-league --season 2023 --resume

# 4. coverage
python -c "import os;os.environ['DATABASE_URL']='...'; ..."
curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/api/v1/coverage/summary
```

## 8. Known gaps in this implementation

* The StatsBomb adapter still hardcodes its base URL and does not read the
  `STATSBOMB_*` settings. Its ingestion path is now implemented
  (`tools/ingest_statsbomb.py` + `app/normalization/statsbomb.py`) and has been run
  against five competition-seasons, but the runner is a separate command from the
  API-Football expansion runner: they do not share one plan file.
* StatsBomb's own catalogue (`competitions.json`) is fetched per run; it is not
  cached in the canonical database, so "which competition-seasons exist" is answered
  by the provider, not by our registry.
* The `football-data.org` adapter still lacks envelope/plan-limit detection.
* `player_match_stats`, `match_lineups` and `match_statistics` are now populated
  **for the ingested StatsBomb matches only**; the API-Football fixture-level
  endpoints (lineups / statistics / player statistics) are still empty because they
  cost one request per fixture and cannot be covered inside a 100-request daily
  budget at the current scale.
* The country registry drives *nationality* coverage only. Club-based discovery for
  the selected countries is expressed through the priority-league registry; a
  dedicated "players of these nationalities" scope planner is not implemented.
* `ingestion_failures` (retry queue / dead-letter) is modelled and tested but the
  runner does not yet re-drive dead letters automatically.
* The identity review queue has no administrative merge command yet (the queue, the
  scoring and the audit fields are implemented and tested).
* `field_provenance` and `source_conflicts` are **populated**: the API-Football and
  StatsBomb normalisers record the provider behind every canonical field, and a
  disagreement between providers is written to `source_conflicts` (status `OPEN`)
  while the canonical value is kept. Measured: 33 296 provenance rows and 20 open
  conflicts. Backfilled from the stored Bronze snapshots with
  `tools/backfill_field_provenance.py` (no provider quota consumed).
