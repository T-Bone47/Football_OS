# PHASE 13 — SCENARIO ENGINE SPECIFICATION & ARCHITECTURE
## Multi-Transfer Scenarios, Unified Scenario Graph & Epistemic Boundaries

### 1. Architectural Mission
The Phase 13 Scenario Engine evolves the Football Intelligence OS from **Continuous Intelligence** to **Decision Simulation Intelligence**. Analysts, Sporting Directors, and Chief Scouts can simulate complex, multi-alternative squad permutations without conflating simulated counterfactuals with observed historical reality.

---

### 2. Core Epistemic Doctrine (§7, §36)
The Scenario Engine enforces a strict ontological separation between data states:
- **`OBSERVED`**: Real-world recorded events, empirical match minutes, official wages, signed transfer fees, and physical medical records.
- **`MODELLED`**: Calibrated statistical representations, player role fits, similarity rankings, and valuation distributions derived from validated models.
- **`COUNTERFACTUAL`**: Simulated hypothetical state adjustments (e.g., replacing Player A with Player B alters the squad's progressive passing vector by +0.07).
- **`SCENARIO`**: User-defined or algorithmically constructed hypothetical movements and parameters (e.g., "Assume Player Y is acquired for €38M on a 5-year contract").
- **`ASSUMPTION`**: Explicit boundary conditions (e.g., "Player adapts within 90 days; 2,200 season minutes expected").

> **Absolute Epistemic Rule**: The system never asserts "Signing Player Y will improve the squad." It reports: *"Under the specified scenario assumptions, the model estimates a +2.4 tactical fit delta and +0.035 win probability shift."*

---

### 3. Unified 12-Stage Scenario Graph (§3)
Every simulation creates a cryptographically traceable, directed acyclic graph (DAG) capturing all 12 analytical stages:

```
[1. CLUB CONTEXT]
       ↓ (SPECIFIES)
[2. CURRENT SQUAD]
       ↓ (EVALUATES)
[3. TACTICAL SYSTEM]
       ↓ (CONSTRAINS)
[4. SQUAD CONSTRAINTS]
       ↓ (CONSTRAINS)
[5. PROPOSED CHANGES]
   ├───┴────────────────────────┐
   ↓ (PERTURBS)                 ↓ (DERIVES)
[6. FEATURE IMPACT]     [8. FINANCIAL IMPACT]
   ↓ (DERIVES)                  ↓
[7. TACTICAL IMPACT]    [9. SQUAD DEPTH]
   ├───┬────────────────────────┘
   ↓ (EVALUATES)
[10. MATCH MODEL ELIGIBILITY]
       ↓ (DERIVES)
[11. COUNTERFACTUAL OUTPUTS]
       ↓ (SUPPORTS)
[12. DECISION EVIDENCE LINEAGE]
```

Every node retains:
- `node_id`, `stage`, `label`, `epistemic_status`
- `source_component`, `model_version`, `dataset_version`
- `assumptions`, `attributes`, and deterministic SHA-256 cryptographic lineage digest.

---

### 4. Canonical Scenario Topologies (§6)
The engine natively supports five fundamental scenario archetypes:
1. **Scenario A (Sell X / Buy Y)**: Like-for-like or positional upgrade (e.g., Sell Partey, acquire Inácio).
2. **Scenario B (Sell X / Buy Y + Z)**: Squad reinvestment & depth expansion (e.g., Sell starter, acquire starter + high-ceiling developmental backup).
3. **Scenario C (Retain X / Promote Academy)**: Zero net spend internal succession pathway.
4. **Scenario D (Sell X + Y / Buy Z)**: Capital consolidation for elite prime talent.
5. **Scenario E (Status Quo / No Transfers)**: Baseline control scenario tracking contract expiration and aging risks.

---

### 5. Match Prediction Parameter Boundary Contract (§15)
To safeguard statistical validity, the existing calibrated match prediction model (`calibrated_multinomial_logit_v1`) is bounded by strict operational contracts:
- **Starter Churn Threshold**: If roster alterations exceed 4 starter changes, the simulation engine returns:
  `SCENARIO_UNSUPPORTED` with contract message: *"Roster churn exceeds match model calibration contract (max 4). Silent extrapolation rejected."*
- **Calibrated Formations**: Only validated tactical systems (`4-3-3`, `4-2-3-1`, `3-5-2`, `3-4-3`, `4-4-2`, `5-3-2`, `4-1-4-1`, `3-4-2-1`) receive match impact modeling.
- **Probability Sum Rule**: All supported counterfactual probabilities (`scenario_win_prob + scenario_draw_prob + scenario_loss_prob`) strictly sum to 1.000.
