# Phase 17 — Freshness, Feature Refresh and Match State

Evidence: `live_pipeline.json` (`freshness`, `feature_refresh`, `match_state_examples`). Live endpoints: `GET /api/v1/ops/freshness/{competition_season_id}`, `GET /api/v1/ops/matches/{id}/state`, `POST /api/v1/ops/features/refresh/{competition_season_id}`.

## 1. Freshness chain (§11)

`readiness.freshness_chain()` reads a real timestamp for every layer of one competition-season:

| Layer | Source of the timestamp |
|---|---|
| SOURCE | the provider's own `last_updated` on the match records (inside the Bronze payload) |
| BRONZE | `data_snapshots.provider_retrieved_at`, plus `content_first_seen` for this SHA-256 |
| SILVER | `max(matches.updated_at)` |
| FEATURE | `max(ops_feature_refresh.refreshed_at)` for the scope |
| MODEL_READINESS | registry row of the match model |
| INTELLIGENCE | latest inference for these matches |
| DECISION | latest decision citing these matches |
| ALERT | latest alert |

A derived layer older than the content it depends on is **STALE**. The comparison uses when the content first arrived, not the latest retrieval: identical re-ingestion refreshes Bronze but correctly leaves Silver unchanged, and must not mark it stale. A layer with no record is `NOT_AVAILABLE`.

Measured for Premier League 2015/16 (evidence run):

| Layer | Timestamp | Age at measurement | State |
|---|---|---|---|
| SOURCE | 2025-12-17 14:38 (StatsBomb `last_updated`) | 6,913 h | CURRENT |
| BRONZE | 2026-10-01 15:56 | 0.0 h | CURRENT |
| SILVER | 2026-10-01 15:56 | 0.0 h | CURRENT |
| FEATURE | 2026-10-01 15:56 | 0.0 h | CURRENT |
| MODEL_READINESS | 2026-10-01 15:56 | 0.0 h | CURRENT |
| INTELLIGENCE | 2026-10-01 15:57 | 0.0 h | CURRENT |
| DECISION | – | – | NOT_AVAILABLE |
| ALERT | – | – | NOT_AVAILABLE |

`data_mode: HISTORICAL_ARCHIVE`, `is_live: false`. Retrieval minutes ago does not make data live. The source content is an archive last updated 288 days earlier, about matches from 2015/16.

## 2. Feature refresh (§12)

`app/phase17/feature_refresh.py`. Feature `team_form_v1` per club per competition-season depends on the club's FINISHED Silver matches; its version is the SHA-256 of that dependency set. States: `REFRESHED`, `UNCHANGED`, `STALE`, `FAILED`, `INSUFFICIENT_DATA`.

| Scope | First pass | Second pass | Recomputed on second pass |
|---|---|---|---|
| Premier League 2015/16 | 20 REFRESHED | 20 UNCHANGED | 0 |
| World Cup 2022 | 32 REFRESHED | 32 UNCHANGED | 0 |
| Bundesliga 2023/24 | 18 REFRESHED | 18 UNCHANGED | 0 |

Each record stores feature, source dependency, previous version, new version, timestamp and values. Inference checks `feature_staleness()`: if Silver moved after the last refresh, the stored version no longer matches and the request is refused with `STALE_DATA` (adversarial 9).

## 3. Match state (§14)

States: SCHEDULED, PRE_MATCH, LIVE, HALFTIME, POST_MATCH, FINAL, DATA_DELAYED, DATA_UNAVAILABLE. `LIVE`/`HALFTIME` require a provider whose live capability is **verified** and data younger than 120 s. Configured timing:

| Provider | Data mode | Live capable | Live verified here |
|---|---|---|---|
| StatsBomb | HISTORICAL_ARCHIVE | no | no |
| API-Football | NEAR_REAL_TIME_DOCUMENTED | yes (documented) | **no** (blocked) |
| football-data.org | DELAYED_DOCUMENTED | no | no |

No provider qualifies for LIVE in this environment. A match whose kickoff has passed without a result is DATA_DELAYED, then DATA_UNAVAILABLE; it is never shown as LIVE.

Example (2022 final): `FINAL`, `real_time: false`, `source_timestamp 2024-12-16T10:15:11` (StatsBomb), `retrieval_timestamp 2026-10-01T15:56:56Z`, `data_age_seconds 11.1`, snapshot `b9d7516d…`.

## 4. Prediction-type safety (§15)

- A `PRE_MATCH` prediction requires a cutoff strictly before kickoff; otherwise `TEMPORAL_VIOLATION`.
- `LIVE` requests cannot be backdated (tolerance 5 min): an explicit past cutoff must use `HISTORICAL_REPLAY` and is labelled as such.
- The history used is re-checked to be strictly before the cutoff.
- Every request is a new immutable `ops_inference_log` row. Earlier predictions cannot be updated or deleted (DB trigger, adversarial 12).
