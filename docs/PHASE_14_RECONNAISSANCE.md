# PHASE 14 — RECONNAISSANCE REPORT
## Outcome-Aware Decision Intelligence, Realized-Outcome Learning & Advanced Football Research OS

**Certified Baseline**: Phase 13 — `DECISION_SIMULATION_VALIDATED`  
**Active Test Suite**: **525 passed**, 0 failures, 0 skipped, 0 regressions in 23.87s  
**Database Migration Head**: `0013_valuation_ml_engine.py` (down: `0012`, alembic managed)  
**Frontend Status**: React 19 SPA, production bundle verified (`main.2359c500.js`, 261.61 kB gzip), 25 primary views  
**Core Epistemic Doctrine**: `OBSERVED`, `MODELLED`, `COUNTERFACTUAL`, `SCENARIO`, and `ASSUMPTION` remain strictly segregated. Counterfactuals are never observed facts. New outcomes create evidence; new evidence does NOT retroactively alter historical decisions.

---

### 1. Architectural & Repository State Analysis

A full static and runtime audit of the repository was performed across backend services, database schema migrations, analytical engines, frontend routes, and test suites.

| Subsystem | Existing Path | Phase Baseline | Current State & Reusability |
|---|---|---|---|
| **Decision Record Store** | `apps/api/app/phase13/decision_record_v2.py` | Phase 13 | High. `DecisionRecordV2` provides immutable record structure, cryptographic digests, candidate sets, and preliminary follow-up status. Phase 14 will evolve this to `DecisionRecordV3` adding append-only outcome links and retrospective learning signals. |
| **Evidence Graph** | `apps/api/app/phase13/scenario_graph.py` & `app/phase12/evidence_graph.py` | Phase 12/13 | High. `UnifiedScenarioGraphBuilder` links Club $\to$ Squad $\to$ Tactics $\to$ Scenarios $\to$ Evidence with SHA-256 digests. Phase 14 requires `EvidenceGraphV3` adding explicit `OUTCOME`, `EVALUATION`, and `LEARNING_SIGNAL` nodes and `REALIZED_AS`, `EVALUATED_BY`, `TRIGGERED` edges. |
| **Tactical Simulator** | `apps/api/app/phase13/tactical_simulator.py` | Phase 13 | High. Evaluates 8 supported formations (`4-3-3`, `4-2-3-1`, `3-5-2`, `3-4-3`, `4-4-2`, `5-3-2`, `4-1-4-1`, `3-4-2-1`) and diagnoses gaps. Reusable as the reference system to evaluate tactical realization. |
| **Scenario Engine** | `apps/api/app/phase13/multi_transfer_scenario.py` | Phase 13 | High. Evaluates multi-transfer movements with match-prediction bounds ($N \le 4$). Serves as ground truth for simulated scenario state when evaluating realized outcomes. |
| **Prediction Calibration**| `apps/api/app/prediction/calibration.py` | Phase 6/11 | High. Provides multi-class Log Loss, Brier Score, and Expected Calibration Error (ECE). Reusable for rolling outcome calibration windows (30, 50, 100, and competition-season windows). |
| **Model Registry & Governance** | `apps/api/app/phase12/challenger_framework.py` | Phase 12 | High. Champion/Challenger framework, shadow mode, and governed promotion reports. Reusable to link divergence signals to governed challenger evaluations. |
| **Decision Staleness** | `apps/api/app/phase12/decision_staleness.py` | Phase 12 | High. Monitors staleness. Phase 14 requires `DecisionFreshnessV2` integrating realized outcomes and assumption expiry. |
| **Post-Decision Feedback**| `apps/api/app/phase12/post_decision_feedback.py` | Phase 12 | Moderate. Preliminary single-transfer retrospective evaluator (`PostDecisionFeedbackRecord`). Needs expansion into multi-dimensional append-only Outcome Ledger and general Decision Realization Evaluator. |
| **Copilot System** | `apps/api/app/phase13/copilot_v3.py` | Phase 13 | High. 8 deterministic scenario query classes. Phase 14 upgrades this to `CopilotV4` supporting 10 outcome-aware research query classes with strictly registered tools. |
| **Frontend Workstation** | `Football_OS-frontend/frontend/src/pages/` | Phase 13 | High. `DecisionLabPage.js` (/decision-lab) provides 9 dense tabs. Phase 14 will build `/outcome-intelligence` workstation with 9 dedicated views. |

---

### 2. Identification of Gaps & Limitations

1. **Absence of Unified Outcome Ledger**:
   - Current feedback records are isolated to individual transfers. An append-only, immutable **Outcome Ledger** is required to record real-world observations across 13 distinct outcome types (`PLAYER_PERFORMANCE`, `TRANSFER_REALIZATION`, `TACTICAL_REALIZATION`, `SQUAD_DEPTH`, `AVAILABILITY`, `FINANCIAL`, `DEVELOPMENT`, `ACADEMY_PROGRESS`, `ROLE_REALIZATION`, `MATCH_OUTCOME`, `MODEL_PREDICTION_REALIZATION`, `DECISION_PROCESS`, `TEAM_PERFORMANCE`).
2. **Missing Decision Realization Evaluator**:
   - Projections made at decision time (expected minutes, contribution, tactical fit, financial net spend) lack automated, multi-metric divergence calculations with explicit tolerance bands and non-causal reasoning.
3. **Discrete Calibration Feedback Loops**:
   - Rolling calibration metrics (Log Loss, Brier, ECE, MCE) are computed statically for training/validation sets, but not continuously updated as new match outcomes are realized across versioned evaluation windows (30, 50, 100 predictions).
4. **Deterministic Error Taxonomy**:
   - When realized outcomes diverge from simulated expectations, the system lacks an explicit multi-label error classifier to identify whether divergence stems from `DATA_ERROR`, `DATA_SPARSE`, `TEMPORAL_MISMATCH`, `MODEL_ERROR`, `CALIBRATION_ERROR`, `OOD_ERROR`, `ASSUMPTION_ERROR`, `SCENARIO_ERROR`, `EXECUTION_DIVERGENCE`, `UNOBSERVED_EXTERNAL_FACTOR`, or `INSUFFICIENT_EVIDENCE`.
5. **Decision Process Quality Auditing**:
   - No standardized metric assesses whether the *decision process* itself was well-supported (e.g. data sufficiency, calibration status, explicit assumptions, OOD checks, sensitivity/robustness) separate from the eventual football outcome.
6. **Benchmark Versioning**:
   - Benchmark percentiles must distinguish `CURRENT_BENCHMARK`, `HISTORICAL_BENCHMARK`, and `DECISION_TIME_BENCHMARK` so that new data cannot retroactively shift historical evaluations.
7. **Temporal Leakage Protection**:
   - Need strict automated leakage test harnesses verifying that injecting future outcomes never mutates historical decision digests or decision-time feature sets.

---

### 3. Compatibility Constraints & Non-Negotiable Rules

- **Zero Rewrite Policy**: Do not modify existing Phase 1–13 endpoints, registries, or databases.
- **Append-Only Outcomes**: Never overwrite an existing outcome record; each entry receives an `outcome_id`, cryptographic provenance, and timestamp.
- **Epistemic Modality Separation**:
  - `OBSERVED`: Raw measured real-world data (e.g., actual minutes played, confirmed transfer fee).
  - `MODELLED`: Algorithmically generated estimates (e.g., tactical fit, valuation model prediction).
  - `COUNTERFACTUAL`: What-if simulation outputs (e.g., predicted squad contribution under replacement).
  - `SCENARIO`: Analyst-defined hypothetical framing (e.g., assumed fee, proposed wage ceiling).
  - `ASSUMPTION`: Stated parameter priors (e.g., assumed availability rate).
- **Non-Causal Language**: Divergence must be characterized using associative language ("aligned with", "diverged from", "associated with", "not explained by available evidence", "insufficient evidence").
- **Historical Immutability**: Historical `DecisionRecord` objects and their SHA-256 digests cannot be altered by retrospective evaluations.

---

### 4. Implementation Blueprint (Phase 14)

1. **`apps/api/app/phase14/` Core Package**:
   - `outcome_ledger.py`: Governed append-only Outcome Ledger (§3).
   - `decision_realization.py`: Decision Realization Evaluator comparing expectation vs realization across multi-metrics (§4, §6).
   - `prediction_calibration_feedback.py`: Rolling calibration feedback engine (Log Loss, Brier, ECE, MCE, evaluation windows 30/50/100) (§5).
   - `tactical_realization.py`: Tactical and scenario realization evaluator (§7, §8).
   - `process_quality.py`: Decision process quality evaluator and error taxonomy classifier (§9, §11).
   - `learning_loop.py`: Governed learning loop, pattern mining, and challenger feedback (§10, §12, §17).
   - `subgroup_monitoring.py`: Subgroup model performance evaluation by context (§13).
   - `decision_freshness_v2.py`: Extended decision freshness and benchmark versioning (§15, §16).
   - `evidence_graph_v3.py`: Cryptographically traceable Evidence Graph V3 with outcome/learning nodes (§18).
   - `decision_record_v3.py`: Immutable Decision Record V3 with append-only evaluation links (§19).
   - `research_mode.py`: Governed research workspace distinguishing hypothesis vs observation (§21).
   - `copilot_v4.py`: Deterministic Outcome-Aware Copilot dispatcher (§20).
2. **REST API**:
   - `apps/api/app/api/routes_phase14.py`: Router mounted under `/api/v1/outcomes` (§23).
3. **Frontend Workstation**:
   - `Football_OS-frontend/frontend/src/pages/OutcomeIntelligencePage.js`: Dense 9-tab analytical workstation at `/outcome-intelligence` (§22).
4. **Verification & Tests**:
   - Comprehensive test suite `tests/unit/test_phase14_outcome_intelligence.py` covering all gates, adversarial injections, temporal safety, and deterministic replay.
