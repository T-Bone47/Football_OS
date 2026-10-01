# Phase 17 — Model Operations

Evidence: `live_pipeline.json` (`model_validation`, `model_registry`, `model_health`, `drift`, `live_inference_attempts`), `incident_drills.json` (MODEL_ARTIFACT_FAILURE), `rollback_drill.json` (model rollback). Live endpoints: `/api/v1/ops/models`, `/models/health`, `/models/calibration`, `/models/drift`, `/models/{id}/promote`, `/models/{id}/demote`, `/inference/match/{id}`, `/inference`.

## 1. What Phase 16 served

`ModelServingEngine` returned `base_metric × 1.05` from a model, `valuation_ml_v1:1.2.0`, that has no artifact, and it served out-of-distribution requests too (reconnaissance R8/R20). Phase 17 changes:
- The serving singleton registers nothing by default. A registered profile without an attached predictor answers `MODEL_UNAVAILABLE`.
- Out-of-distribution requests are never served.
- The demo profiles survive only as opt-in test fixtures.

## 2. Registry (`ops_model_registry`)

Only rows here can produce a prediction. The existing match model was registered as:

| Field | Value |
|---|---|
| model | `calibrated_multinomial_logit_v1` v1.2.0 (domain `match_outcome`) |
| feature version | `match_prediction_v1` |
| artifact SHA-256 | `3a073167…750a2` (digest of the model's parameter set; it has no file artifact) |
| declared metrics | **DECLARED_UNVERIFIED**: `prediction/registry.py` claims log loss 0.9418 on a dataset not in the repository (R18) |
| deployment state | **REGISTERED** (not servable) |
| supported competitions | none |

## 3. Inference gate (§13)

`app/phase17/model_ops.infer_match()` refuses, in this order, with:
1. `MODEL_UNAVAILABLE`: no ACTIVE or SHADOW model, artifact digest mismatch, or feature-version mismatch.
2. `TEMPORAL_VIOLATION`: a backdated LIVE request, a cutoff at or after kickoff, or history at or after the cutoff.
3. `OUT_OF_DISTRIBUTION`: competition not validated for this model (competitions never inherit), or the feature-level OOD gate (extreme Elo gap, invalid rates).
4. `STALE_DATA`: LIVE mode with a fixture snapshot older than 72 h, or team features out of sync with Silver.
5. `INSUFFICIENT_DATA`: fewer than 5 prior matches per side.

Every request, served or refused, is an immutable `ops_inference_log` row carrying model, feature and dataset versions, data cutoff, features used, missing features, reasons, latency and evidence (the history match IDs).

The Phase 6 `MatchPredictionService` falls back to league priors when data is insufficient. The Phase 17 path never does that.

## 4. Validation on real data (walk-forward)

Each match was predicted with a cutoff one second before kickoff, using only earlier Silver matches. These are historical-replay predictions, recorded as `VALIDATION_BACKTEST`.

| Competition | Matches | Served | INSUFFICIENT_DATA | Outcomes | Verdict |
|---|---|---|---|---|---|
| Premier League 2015/16 | 380 | 330 | 50 | 330 | **VALIDATION_FAILED** |
| FIFA World Cup 2022 | 64 | 4 | 60 | 4 | NOT_ENOUGH_OUTCOMES |
| Bundesliga 2023/24 (Leverkusen only) | 34 | 0 | 34 | 0 | NOT_ENOUGH_OUTCOMES |

Premier League 2015/16, n = 330:

| Metric | Model | Class-prior baseline |
|---|---|---|
| Log loss | **1.1832** | **1.0803** |
| Brier | 0.7023 | – |
| ECE | 0.2148 | – |
| MCE | 0.3674 | – |
| Accuracy | 0.4727 | – |

**The model is worse than predicting base rates**, so it does not qualify for any competition and stays `REGISTERED`. Caveat: 2015/16 was an unusual season (Leicester City won the league), but the model also uses fixed hand-set weights and has never been fitted to data. Re-fitting belongs to the governed challenger workflow (Phase 12/15); Phase 17 does not retrain.

## 5. Health snapshot (§19)

`LiveModelHealthSnapshot` (`/models/health`), computed only from the inference log. At the end of the evidence runs: 666 requests, 15 of them LIVE-mode.
- **By status**: SERVED 335, INSUFFICIENT_DATA 144, MODEL_UNAVAILABLE 187.
- **Latency** (inference only): p50 11.4 ms, p95 27.1 ms, p99 56.7 ms.
- **Live calibration**: `NOT_ENOUGH_LIVE_OUTCOMES` (0 live outcomes).

Because there are no live observations, live drift is `NOT_ENOUGH_OBSERVATIONS`.

## 6. Drift (§52)

PSI with thresholds 0.10 / 0.25 / 0.50 for MONITOR / DRIFT / CRITICAL_DRIFT; minimum 50 observations per window. Never retrains automatically. `DRIFT` sets `retrain_recommended`, which routes to the challenger workflow.

| Evidence mode | Result |
|---|---|
| LIVE | NOT_ENOUGH_OBSERVATIONS |
| VALIDATION_BACKTEST | **DRIFT** (reference 167 / current 167, split at the median kickoff): `elo_diff` PSI 0.418 (DRIFT), `home_goal_diff_l5` 0.157 and `away_goal_diff_l5` 0.152 (MONITOR), `points_diff_l5` 0.082 (STABLE), confidence PSI 0.203 (MONITOR) |

Interpretation, stated as association only: Elo differences start near zero each season and spread as results accumulate, so the first half of a season-long replay differs from the second. The later window also contains the 4 served World Cup matches. Either way, this is historical evidence, not production drift.

## 7. Promotion and rollback (§29, §48)

- **Promote** (`POST /models/{id}/promote`): ADMIN only. Any other role gets 403 plus an `UNAUTHORIZED_MODEL_PROMOTION_ATTEMPT` audit event. An ADMIN gets 409 `PROMOTION_BLOCKED` unless the model is SHADOW, has ≥100 live outcomes, beats the class-prior baseline on them, and shows no critical live drift. Observed: the scout got 403; the admin got 409 with blockers.
- **Demote** (`POST /models/{id}/demote`): ACTIVE → SHADOW → REGISTERED, audited. Rollback drill: SHADOW → REGISTERED succeeded; a second demote returned 409.
- **Artifact integrity**: a corrupted `artifact_sha256` gives `MODEL_UNAVAILABLE: ARTIFACT_INTEGRITY_FAILED` and an operational alert. Restoring the digest restores service (incident drill, passed).

## 8. Other models

- **Valuation**: the real artifact `val_lightgbm_20260920` has validation R² of −0.011 and was trained on the open-transfers dataset, whose provenance is unverified (R21). It is not registered for serving. Its inputs require transfer data that no reachable provider supplies.
- **Roles, similarity, tactical fit, player intelligence**: these endpoints answer HTTP 200 on the StatsBomb-loaded database (measured in the load test). Whether they produce evidence-backed output on this data was **NOT_TESTED** in Phase 17. They depend on player feature snapshots that the StatsBomb Silver path does not populate.
