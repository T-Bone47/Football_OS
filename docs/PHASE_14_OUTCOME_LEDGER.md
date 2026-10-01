# Phase 14 — Governed Append-Only Outcome Ledger Architecture

**Certified Baseline**: Phase 13 — `DECISION_SIMULATION_VALIDATED`  
**Current Phase**: Phase 14 — `OUTCOME_AWARE_DECISION_INTELLIGENCE`  
**Core Epistemic Doctrine**: The Outcome Ledger records **ONLY empirical real-world observations** under the strict epistemic modality **`OBSERVED`**. Counterfactual simulations, model estimates, hypotheses, and analyst assumptions are strictly barred from entering the Outcome Ledger.

---

### 1. Architectural Principles & Non-Negotiable Guarantees

1. **Append-Only Semantics**:
   - Once written, an outcome record can never be updated, overwritten, or deleted.
   - Any attempt to append an existing `outcome_id` raises a deterministic error.
2. **Cryptographic Lineage**:
   - Every entry generates a deterministic SHA-256 hash over its full analytical payload.
   - The ledger engine provides a `verify_ledger_integrity()` auditing method to detect any unauthorized data tampering or bit rot.
3. **Strict Data Sufficiency (Zero-Fabrication Policy)**:
   - Missing observations are recorded with `DataSufficiencyStatus.INSUFFICIENT_DATA` or `UNAVAILABLE`.
   - Missing match minutes or metrics are **NEVER converted to 0.0**.
   - Undisclosed transfer fees are **NEVER treated as free (€0.00)**.
4. **Temporal Isolation**:
   - Every observation records the empirical timestamp `observed_at` and the snapshot ID `source_snapshot_id` of the bronze data feed.

---

### 2. Outcome Record Schema & Data Contracts

Each `OutcomeRecord` preserves:

| Field | Type | Description |
|---|---|---|
| `outcome_id` | `str` | Unique immutable primary identifier (e.g. `outc_timber_min_2324`). |
| `decision_id` | `str` | Reference to the associated historical Decision Record. |
| `scenario_id` | `str` | Reference to the specific simulated scenario being evaluated. |
| `player_id` | `str \| None` | Target player entity identifier where applicable. |
| `club_id` | `str` | Club entity identifier (e.g. `arsenal_fc`). |
| `competition_id` | `str` | Competition identifier (e.g. `premier_league`). |
| `season_id` | `str` | Season identifier (e.g. `2023_2024`). |
| `observation_window` | `str` | Observation scope (e.g. `FULL_SEASON`, `MATCH_DAY_1_TO_19`, `WINDOW_CLOSE`). |
| `outcome_type` | `OutcomeType` | One of the 13 canonical outcome categories. |
| `metric` | `str` | Specific measured parameter (e.g. `minutes_played`, `transfer_fee_paid_eur`). |
| `value` | `float` | Measured numerical observation. |
| `unit` | `str` | Parameter unit (e.g. `minutes`, `EUR`, `score_0_100`, `per_90`). |
| `observed_at` | `str` | Verified ISO-8601 observation timestamp. |
| `source` | `str` | Authoritative data provider (e.g. `premier_league_official_telemetry`). |
| `source_snapshot_id` | `str` | Bronze data source immutable snapshot identifier. |
| `provenance` | `dict` | Ingestion pipeline metadata and auditing signatures. |
| `confidence` | `float` | Source measurement confidence (0.0 to 1.0). |
| `data_status` | `DataSufficiencyStatus` | Data sufficiency classification (`DATA_AVAILABLE`, `LOW_SAMPLE`, etc.). |
| `calculation_version`| `str` | Analytical ingestion calculator version (e.g. `outcome_calc_v1.0`). |
| `modality` | `EpistemicModality` | Fixed invariant: **`OBSERVED`**. |
| `record_digest` | `str` | Cryptographic SHA-256 payload digest. |

---

### 3. The 13 Canonical Outcome Types

1. `PLAYER_PERFORMANCE`: Realized individual match actions, progressive numbers, defensive actions.
2. `TRANSFER_REALIZATION`: Confirmed transfer fee, signing bonuses, realized weekly wage.
3. `TEAM_PERFORMANCE`: League points, goal difference, xG concession, possession share.
4. `TACTICAL_REALIZATION`: Observed formation deployment, pitch position, heatmaps.
5. `SQUAD_DEPTH`: Realized minutes distribution, backup coverage under injury.
6. `AVAILABILITY`: Match availability percentage, injury absence duration.
7. `FINANCIAL`: Net transfer spend, wage bill utilization, financial fair play headroom.
8. `DEVELOPMENT`: Career development curve progression, skill acquisition.
9. `ACADEMY_PROGRESS`: First-team appearances, academy promotion minutes.
10. `ROLE_REALIZATION`: Observed tactical role vs simulated archetype.
11. `MATCH_OUTCOME`: Realized match class (Home Win, Draw, Away Win) and full-time scores.
12. `MODEL_PREDICTION_REALIZATION`: Match prediction outcome pairing for calibration tracking.
13. `DECISION_PROCESS`: Audited procedural milestones and governance approvals.
