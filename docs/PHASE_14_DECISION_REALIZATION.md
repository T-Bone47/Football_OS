# Phase 14 — Decision vs Realization Evaluation Methodology

**Certified Baseline**: Phase 13 — `DECISION_SIMULATION_VALIDATED`  
**Current Phase**: Phase 14 — `OUTCOME_AWARE_DECISION_INTELLIGENCE`  
**Core Non-Causal Epistemic Rule**: Divergence between simulated expectations and realized outcomes is evaluated using **purely associative and descriptive language**. Under no circumstances may an evaluation claim that a transfer, formation, or decision *caused* a specific outcome without formal causal identification.

---

### 1. Evaluation Architecture & Pipeline

The `DecisionRealizationEvaluator` acts as the bridge connecting simulated projections from Phase 13 to verified observations recorded in the Phase 14 Outcome Ledger:

```
DECISION RECORD (Frozen Snapshot)
  • Projected Minutes
  • Assumed Transfer Fee
  • Modelled Tactical Fit
  • Expected Contribution
          │
          ▼
   [ EVALUATOR ] ◄──── OUTCOME LEDGER (Verified OBSERVED)
          │             • Confirmed Minutes
          │             • Audited Transfer Fee
          │             • Observed Tactical Fit
          ▼
REALIZATION REPORT
  • Multi-Dimensional Delta Matrix (No Single-Score Collapse)
  • Tolerance Band Checks (±5% to ±15%)
  • Classification: ALIGNED | PARTIALLY_ALIGNED | DIVERGED | INSUFFICIENT_EVIDENCE
  • Associative Qualitative Findings
  • Error Taxonomy Root Diagnosis
```

---

### 2. Multi-Metric Preservation (No Single-Score Collapse)

A core requirement of Football Decision Intelligence 2.0 and 3.0 is that multi-dimensional decisions must **never be collapsed into an opaque single score**.

For every tracked metric, the evaluation computes:
1. `expected_value` ($E$) [MODELLED / SCENARIO]
2. `realized_value` ($R$) [OBSERVED]
3. `absolute_delta` ($R - E$)
4. `relative_delta_pct` ($\frac{R - E}{E} \times 100\%$)
5. `tolerance_band_pct` ($\pm T\%$)
6. `is_within_tolerance` ($E(1 - T) \le R \le E(1 + T)$)
7. `directional_alignment` (`WITHIN_TOLERANCE`, `HIGHER_THAN_EXPECTED`, `LOWER_THAN_EXPECTED`)
8. `evidence_status` (`DATA_AVAILABLE`, `LOW_SAMPLE`, `INSUFFICIENT_DATA`)

---

### 3. Alignment Classification Standard

- **`ALIGNED`**: $\ge 80\%$ of tracked metrics fall within their calibrated tolerance bands. No primary metric shows extreme divergence.
- **`PARTIALLY_ALIGNED`**: $50\% \le \text{rate} < 80\%$ of metrics are within tolerance bands, indicating that the directional transfer thesis was validated despite secondary variance.
- **`DIVERGED`**: $< 50\%$ of metrics within tolerance, indicating significant operational or contextual disparity.
- **`INSUFFICIENT_EVIDENCE`**: Telemetry is missing or below minimum sample threshold, preventing conclusive classification.

---

### 4. Canonical Phrasing Guide (Non-Causal Compliance)

| Prohibited Phrasing (Causal Claim) | Mandated Analytical Phrasing (Associative Grounding) |
|---|---|
| *"Signing Player X caused the team to concede more goals."* | *"Observed goal concession rate diverged by +0.32/90 relative to the scenario baseline."* |
| *"The 4-3-3 formation failed because the fullback was bad."* | *"Tactical role execution diverged from the simulated inverted fullback receiving pattern."* |
| *"This was a bad recruitment decision."* | *"Realized minutes (1,280 mins) tracked below the 1,400 min baseline, associated with acute match-day trauma."* |
| *"The player will definitely succeed next year."* | *"Under current trajectory progression, the player's 12-month rolling vector is consistent with upward development."* |
