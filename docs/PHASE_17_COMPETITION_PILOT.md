# Phase 17 — Live Competition Pilot

Evidence: `live_pipeline.json` (`pilots`, `competition_readiness`, `model_validation`), `quality_final.json`. Live endpoint: `GET /api/v1/ops/competitions/readiness`.

## 1. Pilot selection

The only reachable provider is StatsBomb Open Data, a historical archive, so the pilot is an **operational pilot on real historical data**, not a live-season pilot. Three scopes were chosen to exercise different shapes of evidence:

| Pilot | Why | Coverage |
|---|---|---|
| Premier League 2015/16 | a complete league season: every team plays 38 times, enough history for walk-forward validation | 380/380 matches, 380 lineups, 8 event files |
| FIFA World Cup 2022 | a short tournament with sparse team histories; tests that thin data is refused, not inherited | 64/64 matches, 64 lineups, 8 event files (including the final) |
| 1. Bundesliga 2023/24 | StatsBomb publishes only Leverkusen's 34 matches; tests partial league coverage | 34 matches (one team's), 34 lineups, 8 event files |

## 2. Measurements (§49)

| Measure | Premier League 2015/16 | World Cup 2022 | Bundesliga 2023/24 |
|---|---|---|---|
| Ingestion success | 389/389 jobs | 73/73 | 43/43 |
| Data freshness | retrieved 2026-10-01; source `last_updated` 2025-12-17; mode HISTORICAL_ARCHIVE | same mode | same mode |
| Silver quality | PASS | PASS | PASS |
| Feature availability | 20/20 clubs REFRESHED | 32/32 | 18/18 |
| Prediction volume (validation) | 380 requests: 330 served, 50 INSUFFICIENT_DATA | 64: 4 served, 60 INSUFFICIENT_DATA | 34: 0 served, 34 INSUFFICIENT_DATA |
| Outcome coverage | 330 historical-replay; **0 live** | 4; 0 live | 0 |
| Model validation | **VALIDATION_FAILED** (log loss 1.183 vs baseline 1.080) | NOT_ENOUGH_OUTCOMES (4 < 50) | NOT_ENOUGH_OUTCOMES (0) |
| OOD refusals | 0 (refused earlier as MODEL_UNAVAILABLE / INSUFFICIENT_DATA) | 0 | 0 |
| Errors | 0 failed jobs | 0 | 0 |
| Alerts | 1 watchlist alert (genuine) in the workflow | – | – |
| Latency | ingestion 4.5 s (matches), 390 s for 380 lineups at the 60/min budget | 1.2 s / 65 s | 0.9 s / 33 s |

## 3. Readiness matrix (§18)

| Competition | Match | Player | Event | Transfer | Model support | Calibration (live) | Freshness | Final state |
|---|---|---|---|---|---|---|---|---|
| Premier League (England) | 380 | 644 players, 13,678 lineup rows | 97 events (8 matches) | NOT_AVAILABLE | validation FAILED | NOT_ENOUGH_LIVE_OUTCOMES | archive | **DATA_AVAILABLE** |
| FIFA World Cup (International) | 64 | 829 players, 3,244 lineup rows | 133 events (8 matches) | NOT_AVAILABLE | NOT_ENOUGH_OUTCOMES | NOT_ENOUGH_LIVE_OUTCOMES | archive | **DATA_AVAILABLE** |
| 1. Bundesliga (Germany) | 34 (one club) | 460 players, 1,353 lineup rows | 130 events (8 matches) | NOT_AVAILABLE | NOT_ENOUGH_OUTCOMES | NOT_ENOUGH_LIVE_OUTCOMES | archive | **DATA_AVAILABLE** |

State rules (`app/phase17/readiness.py`): no matches → NOT_AVAILABLE; fewer than 30 finished → INSUFFICIENT_DATA; data without validated model support → DATA_AVAILABLE; validated support with a SHADOW model → SHADOW. PRODUCTION_READY additionally needs an ACTIVE model and ≥100 live outcomes. A failing latest quality report → BLOCKED; a probe-observed provider failure → DEGRADED. Every figure is filtered to its own competition. **No competition inherits another's status.**

No pilot reached MODEL_VALIDATED, SHADOW or PRODUCTION_READY. The data pipeline is ready for all three; the prediction model is not.

## 4. Expansion policy (§50)

```
PILOT ─► OBSERVE ─► VALIDATE ─► STABILIZE ─► EXPAND
```

- The scheduler's scope table (`tools/phase17/scheduler.py: JOB_PARAMS`) is the only place a competition-season enters scheduled ingestion. Adding one is a reviewed code change, never automatic.
- A competition is served only after its **own** walk-forward validation passes (`validate_competition_support`). Its `supported_competitions` entry is per competition.
- Expansion is blocked until a live-capable provider is reachable (for live operation), and until a model that beats the baseline exists (for prediction).

## 5. Not demonstrated
- Live season operation (no live fixtures reachable).
- Transfer-market monitoring (§17): no reachable source publishes transfers. The open-transfers dataset in the repo has unverified provenance (R21). The fee taxonomy (UNKNOWN_FEE never 0, UNDISCLOSED never FREE) is unchanged from Phase 4 and was not re-exercised on live data. **NOT_TESTED.**
