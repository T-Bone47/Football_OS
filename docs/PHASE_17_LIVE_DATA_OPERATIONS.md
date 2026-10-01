# Phase 17 — Live Data Operations

Evidence: `docs/evidence/phase17/live_pipeline.json`, `scheduler_run.json`, `quality_final.json`, `ops_snapshot.json`.
Run date: 2026-10-01, Claude Code cloud sandbox, PostgreSQL 16.14, local Bronze store.

## 1. Environments (§2)

| Environment | Template | Database | Redis | Bronze | Model artifacts |
|---|---|---|---|---|---|
| development | `.env.example`, `deploy/env/development.env.example` | `fios` | db 0 | `./data/bronze` (local) | `./data/models` |
| test | `deploy/env/test.env.example` | `fios_test` | db 1 | `./data/bronze-test` (local) | `./data/models-test` |
| staging | `deploy/env/staging.env.example` | `fios_staging` @ staging host | staging host | `s3://football-os-bronze-staging` | `s3://football-os-models-staging` |
| production | `deploy/env/production.env.example` | `fios_production` @ prod host | prod host | `s3://football-os-bronze-production` | `s3://football-os-models-production` |

`app/phase17/environments.py` enforces these rules:
- `ENVIRONMENT` must be one of the four values. A missing value means **development**, never production.
- `audit_isolation()` rejects any database, Redis DB, object store, artifact location or secret shared between environments. It is tested against the four templates.
- In **staging/production** the app refuses to start (`enforce_startup_policy`, called from `main.py`) if the database password is a development default or empty, CORS contains `*` or a localhost origin, Bronze storage is not S3, or the S3 secret is a default. With no secrets injected, the production template is rejected; that is tested.
- Secrets in templates are `${...}` placeholders resolved from the environment at deploy time. `.env` is gitignored, and `.dockerignore` excludes it from build contexts.

## 2. Pipeline

```
probe ─► rate budget ─► IngestionService (fetch ► Bronze ► validate)
      ─► SHA-256 re-verify ─► contract check ─► payload DataQualityReport
      ─► NormalizationService (Silver) ─► Silver DataQualityReport ─► feature refresh
```

Implemented in `app/phase17/live_ingestion.py`. Every execution is an `ops_job_runs` row. Its `RUNNING` status is committed **before** the network call, so a lost worker leaves a visible, reapable row. Possible outcomes:

| Status | Meaning |
|---|---|
| `SUCCESS` | Bronze captured, contract OK/WARN, quality not FAIL, Silver written |
| `INGESTION_BLOCKED` | Contract drift. Bronze is kept, Silver is untouched, and an audit event plus an operational alert are raised |
| `QUALITY_BLOCKED` | Payload quality FAIL or non-JSON body. Silver is untouched |
| `RATE_LIMIT_DEFERRED` | Budget exhausted or provider cooldown. **No request is sent** |
| `FAILED` | Provider, network, storage, Bronze integrity or Silver failure. A Silver failure rolls back only the Silver writes |

No path returns `SUCCESS` without a provider response.

### StatsBomb → Silver (new)
Before Phase 17 the Silver layer only understood API-Football payloads (reconnaissance R13). `normalization/statsbomb_transformers.py` maps StatsBomb matches, lineups and events to the existing `Normalized*` schemas, and `NormalizationService` dispatches on provider. Provider facts handled, all observed in real payloads:
- Penalty-shootout kicks (period 5) are not match goals. The 2022 final reconciles at 6 goals = 3–3.
- Starters are identified by a first position beginning at `00:00` in period 1, not only by `start_reason == "Starting XI"`. In Premier League 2015/16 match 3754047, all 11 Swansea starters are labelled `"Tactical Shift"`. The first evidence pass quality-blocked that file before the rule was fixed.
- `formation_position` stores StatsBomb's numeric `position_id`. The position name overflowed `VARCHAR(16)` on the first live run.
- `kick_off` has no timezone and is interpreted as UTC. This is recorded as an assumption.

## 3. Real ingestion results (§5)

Provider: StatsBomb Open Data, the only provider reachable from this environment (see `PHASE_17_PROVIDER_MATRIX.md`).

| Scope | Matches file | Lineups | Events (sample) | Silver |
|---|---|---|---|---|
| Premier League 2015/16 (2/27) | SUCCESS, 380 records | 380/380 SUCCESS | 8/8 SUCCESS | 380 matches |
| FIFA World Cup 2022 (43/106) | SUCCESS, 64 records | 64/64 SUCCESS | 8/8 SUCCESS (includes the final) | 64 matches |
| 1. Bundesliga 2023/24 (9/281) | SUCCESS, 34 records (Leverkusen only) | 34/34 SUCCESS | 8/8 SUCCESS | 34 matches |
| Competitions index | SUCCESS, 80 competition-seasons | – | – | – |

Totals: **511 jobs, 511 SUCCESS**. Silver holds 478 matches, 70 clubs, 1,802 players, 18,275 lineup rows and 360 discrete events. Bronze holds 506 distinct snapshot files (88.3 MB of distinct content).

## 4. Bronze snapshots (§6)

Each snapshot records: provider (`data_sources`, with licence `CC BY-NC-SA 4.0` and base URL), endpoint and parameters (`ingestion_runs`), the provider retrieval timestamp, HTTP status, content type and source URL (new columns in migration 0014), the raw payload (content-addressed file `bronze/<provider>/<resource>/<sha256>.json`), its SHA-256, a schema version (the contract fingerprint) and `ingestion_run_id`.

- **Same bytes → same SHA → same file**: verified on all 5 idempotency re-runs.
- **Integrity**: bytes are re-hashed before Silver promotion and before replay; a mismatch gives `BRONZE_INTEGRITY_FAILED`. The local store now also re-verifies an existing file before skipping a write, so a re-fetch heals a corrupted copy (incident drill BAD_DATA_SNAPSHOT).

## 5. Idempotency (§6, adversarial 1)

| Re-run | SHA-256 identical | Silver delta |
|---|---|---|
| Premier League 2015/16 matches | yes | 0 on every table |
| World Cup 2022 matches | yes | 0 |
| Bundesliga 2023/24 matches | yes | 0 |
| Final lineups (3869685) | yes | 0 |
| Final events (3869685) | yes | 0 |

## 6. Scheduling (§7)

`tools/phase17/scheduler.py --once` runs whatever is due and exits; a deployment calls it from cron or systemd. There is no long-running worker (reconnaissance; `apps/worker` does not exist). Schedule classes and their rationale are in `live_ingestion.SCHEDULES`:

| Job | Class | Why |
|---|---|---|
| statsbomb_competitions_index | WEEKLY | The archive updates irregularly; `match_updated` reveals additions |
| statsbomb_season_matches | SEASONAL | Archived seasons are complete |
| statsbomb_match_lineups / events | ON_DEMAND | Per-match files; events are 3–4 MB each, so they are never bulk-polled |
| api_football_fixtures | LIVE | Only runs when the last probe was AVAILABLE |
| api_football_transfers | DAILY | Transfers change at most daily |

Evidence run: StatsBomb jobs were skipped as not yet due. `api_football_fixtures` was withheld (no AVAILABLE probe). `api_football_transfers` ran with the configured key and was recorded `FAILED: ProviderNetworkError: ProxyError: 403`, in 2.4 s across 3 bounded attempts.

## 7. Rate-limit governance (§8)

`app/phase17/rate_governor.py` counts every HTTP attempt, including adapter retries, through `httpx` event hooks. Budgets carry their source:
- StatsBomb: 60/min, 2,000/h, `SELF_IMPOSED`. The host (raw.githubusercontent.com) publishes no API quota.
- API-Football and football-data.org: 10/min, `CONSERVATIVE_DEFAULT_UNVERIFIED`. Their quotas could not be read: the hosts are blocked here.

After a provider 429 the governor enters a cooldown, and later jobs are `RATE_LIMIT_DEFERRED` without sending anything (adversarial 5).

Evidence run: 511 requests, at most 50 in any minute against a budget of 60. 0 retries, 0 × 429, 0 × 5xx, budget never exceeded.

**Limitation**: the governor is process-local. A multi-worker deployment needs a shared store. Per-user API rate limiting already uses Redis, with a local fallback.

## 8. Failure handling (§9)

Tested by integration and adversarial tests and by incident drills: timeout or transport error, DNS/egress block (real), HTTP 500/503, 429, invalid credentials, malformed or truncated JSON, schema change, partial response (one team), object-storage failure, database outage, and worker loss. In every case: **no fabrication, no partial Silver write, no silent success**.

## 9. Data quality (§10)

`app/phase17/data_quality.py` produces a `DataQualityReport` (PASS/WARN/FAIL with affected record counts) per Bronze payload and per Silver competition-season. Checks: schema/contract, nulls, duplicates, referential integrity (Silver row → snapshot), temporal validity, identity consistency, impossible values, pitch bounds, competition/season consistency, cross-resource score/event reconciliation, and lineup completeness. A check that cannot run is `WARN` with `evaluated: false`, never `PASS`. Cross-provider conflict detection is always `WARN / evaluated: false`, because only one provider is reachable.

Final Silver reports (`quality_final.json`), run after all lineups and events were loaded:

| Scope | Overall | Notes |
|---|---|---|
| Premier League 2015/16 | PASS | 8 matches with events reconcile with final scores; 380/380 matches have ≥22 lineup players |
| FIFA World Cup 2022 | PASS | 8 reconciled (including the 3–3 final with its shootout excluded); 64/64 complete |
| Bundesliga 2023/24 | PASS | 8 reconciled; 34/34 complete |

## 10. Contract drift (§39)

`app/phase17/contract_drift.py` checks each payload against code-reviewed key fields and enum domains, plus the field types registered from the first good snapshot.
- **Blocks Silver**: a missing key field, a type change, an unexpected null, an enum value outside its domain, or an envelope change. A likely rename is reported.
- **Warns only**: a new field, or a non-key field that is absent (StatsBomb event streams are heterogeneous).
- All live payloads in the evidence run were `CONTRACT_OK`.

## 11. Replay (§40)

`replay_snapshot()` re-verifies a Bronze snapshot's SHA-256 and runs the same normalizer, with no network. Tested: Silver digest identical after replaying every snapshot, and inference output, features and input digest identical before and after replay (adversarial 21).

## 12. Provenance (§41)

`live_pipeline.json → provenance_audit`: 100 sampled Silver records (40 matches, 40 lineup rows, 20 events). All traced Silver → `data_snapshots` → `ingestion_runs` → `data_sources`. Every Bronze file's recomputed SHA-256 matched. Orphans: 0 matches, 0 lineups, 0 events without a snapshot.

## 13. Retention (§45) and usage (§44)

`GET /api/v1/ops/retention` reports the policy plus the live trigger check. UPDATE/DELETE triggers are present on `ops_audit_events`, `ops_decisions` and `ops_inference_log`. No automatic deletion job exists. Bronze is content-addressed and never overwritten except to heal a corrupt copy with bytes of the same hash.

`GET /api/v1/ops/usage` (`ops_snapshot.json`): Bronze 93.9 MB referenced, 88.3 MB distinct; database 25.6 MB; job runtime 391 s total; 666 inference requests; notifications IN_APP 9, WEBHOOK 2. **Monetary cost: UNAVAILABLE**, because no provider billing API is configured.

## 14. Known limitations
- Silver promotion reads Bronze from the local store only; reading from S3 Bronze is not implemented.
- Events are ingested for a sample (8 per competition), not every match.
- StatsBomb is a historical archive. Nothing here is live data.
