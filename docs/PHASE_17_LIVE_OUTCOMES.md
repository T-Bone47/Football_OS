# Phase 17 — Outcomes, Calibration and the Learning Loop

Evidence: `live_pipeline.json` (`calibration`, `model_validation`), `workflow_e2e.json` (steps 16–19). Live endpoints: `POST /api/v1/ops/inference/{id}/outcome`, `GET /api/v1/ops/models/calibration?mode=LIVE|HISTORICAL_REPLAY`.

## 1. Outcome ledger (§20)

`record_outcome()` links a served prediction to the real Silver result once the match is FINISHED. It stores the realized 1X2 result and score, the source (`silver.matches:<provider>:<fixture>`), the SHA-256 of the result's Bronze snapshot, the observation time and a per-prediction evaluation (log loss, Brier, correct).

- The prediction row is never modified. `ops_inference_log` rejects UPDATE/DELETE, and `ops_outcomes` references it with ON DELETE RESTRICT.
- The observation mode comes from timestamps, not labels: an outcome is **LIVE** only when the prediction was logged before kickoff. A prediction logged after the match (every backtest) is **HISTORICAL_REPLAY**.

## 2. What exists

| Kind | Count | Notes |
|---|---|---|
| Live outcomes | **0** | No reachable provider publishes upcoming fixtures, so no pre-kickoff prediction on a real future match was possible |
| Historical-replay outcomes | 335 | 330 Premier League 2015/16 + 4 World Cup 2022 validation predictions, plus the workflow's cited prediction |

## 3. Calibration (§51)

Minimums: 100 outcomes overall and 50 per subgroup. Below those, the report says so and computes nothing.

| Mode | Status | n | Log loss | Brier | ECE | MCE | Accuracy | Baseline log loss |
|---|---|---|---|---|---|---|---|---|
| **LIVE** | **NOT_ENOUGH_LIVE_OUTCOMES** | 0 | – | – | – | – | – | – |
| HISTORICAL_REPLAY | MEASURED | 334 | 1.1808 | 0.7008 | 0.2103 | 0.3674 | 0.4731 | 1.0787 |

Historical-replay subgroups: Premier League n = 330, measured; World Cup n = 4, `NOT_ENOUGH_OUTCOMES`. The calibration curve (10 confidence bins, mean confidence vs observed accuracy) is returned by the API and shown on `/model-ops`.

Reading: historical-replay calibration is poor (ECE 0.21) and worse than the base-rate baseline. That is the evidence that kept the model unpromoted. No live calibration exists, so no live claim is made.

## 4. Retrospective evaluation (workflow step 17)

The decision recorded in the end-to-end workflow cites a served validation prediction for the last Premier League 2015/16 fixture. That fixture finished 3–1 home win; the prediction's evaluation was log loss 0.133, Brier 0.023, correct. The decision's provenance shows: integrity verified (content hash recomputed), the outcome attached to its evidence node, and staleness `CURRENT` (no Silver dependency changed after the decision).

## 5. The loop (§53)

```
LIVE DATA ─► INTELLIGENCE ─► DECISION ─► OUTCOME ─► RESEARCH ─► VALIDATION ─► CHALLENGER ─► HUMAN PROMOTION ─► LIVE MODEL
```

| Link | Status in Phase 17 |
|---|---|
| Live data → intelligence | **UNVERIFIED**: no live provider reachable; archive data only |
| Intelligence → decision | VERIFIED (decision cites inference IDs; evidence graph built server-side) |
| Decision → outcome | VERIFIED for historical replay; live **UNVERIFIED** |
| Outcome → research | VERIFIED: `POST /research/dataset` returns a cutoff-bounded, versioned dataset with a future-data check |
| Research → validation | VERIFIED: walk-forward validation per competition |
| Validation → challenger | IMPLEMENTED (Phase 12/15 governed workflow); not exercised with a new candidate in Phase 17 |
| Challenger → human promotion | VERIFIED gate: promotion refused (409) without live evidence |
| Promotion → live model | **NOT_TESTED**: nothing qualified |
