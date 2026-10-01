# Phase 18 — Database Integrity

Evidence: `tests/integration/test_phase18_database_integrity.py` (8 tests), the CI step "Schema parity", and the commands below. Every command was run against an empty PostgreSQL 16.14 database.

## 1. Clean install

```
CREATE DATABASE fios_p18_recon;
DATABASE_URL=postgresql+asyncpg://…/fios_p18_recon alembic upgrade head   # 0001 → 0016, no manual steps
DATABASE_URL=…                                    alembic check            # "No new upgrade operations detected."
alembic downgrade 0014 && alembic upgrade head && alembic check            # round trip, still zero drift
```

`database/migrations/env.py` uses the psycopg2 driver for migrations (R3) and now compares column **types** as well as tables, columns, nullability and indexes.

## 2. Drift found and resolved (R19)

At Phase 18 start, `alembic check` on a 0014 database reported **32 operations**.

| Kind | Count | Resolution (migration `0015_schema_parity`) |
|---|---|---|
| Timestamp columns NOT NULL in the ORM, nullable in the database | 16 | `ALTER … SET NOT NULL`. The migration **refuses to run if any NULL exists**: it will not invent a timestamp |
| Indexes declared in the ORM, never created | 10 | created |
| Indexes that duplicated a unique constraint on the same columns | 2 | dropped (`ix_club_identities_provider_lookup`, `ix_player_identities_provider_lookup`) |
| Composite indexes present only in the database | 4 | kept, and now declared in the ORM (`match_events`, `player_match_stats` ×2, `ingestion_runs`) |
| ORM single-column index on `match_events.minute`, superseded by the composite | 1 | removed from the ORM |

Historical migrations 0001–0014 were not edited.

## 3. Defaults that asserted facts (migration `0016_truthful_defaults`)

Comparing server defaults (which `alembic check` ignores by default) found 57 database defaults the ORM did not declare. Some of them **made facts up whenever a writer left a column out**. The ORM had matching Python-side defaults that did the same.

| Column | Default that was removed | Why it was a fabrication |
|---|---|---|
| `transfers.data_quality_status` | `'HIGH'` | quality was never assessed |
| `transfers.source_provider`, `canonical_actions.provider`, `player_match_stats.provider` | `'api-football'` | provenance claimed for rows from any source, including StatsBomb |
| `valuation_models.status` | `'MODEL_VALIDATED'` | validation claimed by default |
| `valuation_predictions.coverage_level` / `data_status` | `0.8` / `'VALUATION_AVAILABLE'` | interval coverage and availability claimed |
| `match_lineups.is_starter` | `true` | every lineup row became a starter |
| `matches.status` | `'SCHEDULED'` | |
| `transfers.transfer_type`, `is_permanent`, `is_loan`, `option_type` | `'PERMANENT'`, `true`, `false`, `'NONE'` | contract structure assumed |
| `player_role_profiles.role_status` | `'QUALIFIED'` | |
| `player_season_stats.appearances/lineups/minutes/goals/assists/conceded` | `0`, NOT NULL | an unreported figure became an observed zero |
| sample sizes, `action_quantity`, `is_captain`, `competitions.type` | `0` / `1` / `false` / `'LEAGUE'` | |

After 0016, a writer must state these values or the insert fails. `player_season_stats` counts are nullable: **NULL means "not reported", 0 means an observed zero.**

Code changes that follow from this:
- The API-Football player transformer no longer turns a missing figure into 0 (`or 0` removed); `NormalizedPlayerStats` fields are optional.
- The transfer-risk availability dimension counts only seasons whose provider reported appearances. With none reported it returns `INSUFFICIENT_DATA`.
- The action normalizer takes the provider from the record's own lineage (`player_match_stats.provider`, or the event's snapshot → ingestion run → data source). It returns `UNKNOWN_SOURCE` when there is no snapshot. Before, it wrote `'api-football'` on every action.
- The valuation dataset builder's record path gave every training row 1,500 minutes, a 7.2 rating, fixed contribution scores and an intelligence score of 75. Those fields are now `None` (see `PHASE_18_MODEL_SERVING.md` for the effect on the valuation model).
- Six test fixtures that relied on the default provider now declare `provider="test-fixture"`.

### Structural defaults kept (explained)

`'{}'` / `'[]'` JSON containers; `PENDING` / `QUEUED` / `UNKNOWN` states (they assert nothing); attempt and notification counters starting at 0 or 1; `is_active` on ops users; `available = false` on provider capabilities (conservative); code version labels such as `calculation_version`; identity `confidence = 1` with `resolution_method = 'DIRECT_PROVIDER_ID'`, which is how every current identity is created (from the provider's own id).

## 4. Tests that enforce this

| Test | Fails when |
|---|---|
| `test_orm_and_migrations_have_zero_drift` | any table, column, nullability, index or type differs between the ORM and a database built only by migrations |
| `test_no_fact_asserting_defaults` | any of 15 fact columns regains a default in the database **or** the ORM |
| `test_season_counts_can_be_unreported` (×6) | a season count can no longer hold NULL |
| `test_adv_19_fake_operational_status` | the reported migration head differs from the head of the migration scripts (no longer a hardcoded literal) |
| CI "Schema parity" | `alembic check` reports anything after the migration round trip |

## 5. Not covered

- The data-bearing database `fios_p17_live` was upgraded to 0016 without error; no NULL timestamps existed.
- Server-default parity for the structural defaults listed above is explained, not enforced by a test.
- A production database restore followed by `upgrade head` is NOT_TESTED: no production database exists.
