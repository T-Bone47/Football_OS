# Phase 14 — Scout Copilot V4 Outcome-Aware Research Assistant

**Certified Baseline**: Phase 13 — `DECISION_SIMULATION_VALIDATED`  
**Current Phase**: Phase 14 — `OUTCOME_AWARE_DECISION_INTELLIGENCE`  
**Core Tool Policy**: Scout Copilot V4 is a **strictly deterministic analytical assistant**. It does not perform ungrounded generative inference or hallucinate statistics. Every quantitative statement resolves to verified records in the Outcome Ledger, Decision Realization Evaluator, or Calibration Engine.

---

### 1. The 10 Canonical Query Classes

| Query Class | Typical Analyst Prompts | Deterministic Backend Tool |
|---|---|---|
| **`EXPECTATION`** | *"What did we expect?", "Original projections for X"* | `decision_realization_evaluator.get_evaluation()` |
| **`REALIZATION`** | *"What actually happened?", "Observed minutes/fee"* | `outcome_ledger.list_outcomes()` |
| **`DIVERGENCE`** | *"Where did the scenario diverge?", "Root causes of delta"* | `process_quality_engine.diagnose_divergence()` |
| **`SENSITIVITY`** | *"Which assumptions were most sensitive?", "Fragile bounds"* | `ScenarioSensitivityAnalyzer` |
| **`TRAJECTORY`** | *"How has player trajectory changed?", "Development vector"* | `player_trajectory_engine` |
| **`CALIBRATION`** | *"How accurate has this model been?", "Brier/Log Loss in EPL"* | `prediction_calibration_feedback_engine` |
| **`FRESHNESS_REVIEW`**| *"Which recruitment decisions require review?", "Stale targets"*| `decision_freshness_v2_engine.list_assessments()` |
| **`EVIDENCE_LINEAGE`** | *"What evidence supports this?", "Show lineage graph"* | `evidence_graph_v3_builder.get_graph()` |
| **`DATA_SUFFICIENCY`** | *"What data is still missing?", "Sample size sufficiency"* | `data_sufficiency_gate` |
| **`CONTEXTUAL_SHIFT`** | *"What changed since the decision?", "Material changes"* | `decision_freshness_v2_engine.get_assessment()` |

---

### 2. Zero-Hallucination Non-Causal Grounding

When responding to user inquiries:
1. Copilot matches the query class against registered patterns.
2. It invokes the deterministic Python engine directly.
3. It extracts verified metrics, units, and source snapshot IDs.
4. It formats the response using associative, non-causal phrasing ("aligned with", "diverged from", "associated with", "not explained by available evidence").
5. It attaches the cryptographic evidence digest to the response payload.
