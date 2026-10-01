# PHASE 13 — COUNTERFACTUAL POLICY & EPISTEMIC GOVERNANCE
## Strict Modality Separation, Causal Claims Prohibition & Model Boundary Safeguards

### 1. Fundamental Principle
The Football Intelligence OS is governed by an absolute epistemic rule:
> **COUNTERFACTUAL SIMULATIONS MUST NEVER BE PRESENTED OR INTERPRETED AS OBSERVED FACTS OR CERTAIN OUTCOMES.**

---

### 2. Modality Taxonomy (§7, §36)
Every data element, analytical vector, and user-facing output must carry an unambiguous `epistemic_modality` tag:

| Modality | Definition | Permitted Examples | Strictly Prohibited Phrasing |
|:---|:---|:---|:---|
| **`OBSERVED`** | Empirically verified historical and contract data. | *"Player X recorded 7.2 progressive actions per 90 in the 2024/25 EPL season."* | Conjectural or extrapolated historical statistics. |
| **`MODELLED`** | Statistically estimated representations from validated models. | *"Player Y exhibits an 88.4 tactical fit score for the Ball Playing CB archetype."* | *"Player Y has an innate true quality of 88.4."* |
| **`COUNTERFACTUAL`** | Simulated mathematical shifts under hypothetical assumptions. | *"Under the scenario, the model projects a +0.035 shift in win probability."* | *"Signing Player Y will guarantee European qualification."* |
| **`SCENARIO`** | User-defined or simulated transfer packages and constraints. | *"Scenario A assumes €38M fee and €110k/wk wage."* | Treating negotiation projections as agreed terms. |
| **`ASSUMPTION`** | Explicit mathematical and environmental conditions. | *"Assumes 2,400 season minutes and 88% availability."* | Hidden, undocumented assumptions. |

---

### 3. Non-Causal Analytics Policy
1. **Associative, Not Causal**: Statistical models evaluate multi-dimensional correlations and calibrated probability distributions. Unless randomized control trials or empirical instrumental variables exist, no causal assertions are permitted.
2. **Forbidden Causal Verbs**:
   - ❌ *"Player X causes Player Y to improve."*
   - ❌ *"This formation will make the team win."*
   - ❌ *"This signing solves our goal-scoring problem."*
3. **Mandatory Epistemic Verbs**:
   - ✅ *"Under the specified scenario assumptions, the model estimates..."*
   - ✅ *"The structural role dependency indicates that holding midfield stability enables..."*
   - ✅ *"The calibrated probability distribution shifts by +0.035 under this roster composition."*

---

### 4. Match Prediction Model Boundary Safeguards (§15)
The calibrated match prediction engine (`calibrated_multinomial_logit_v1`) operates within an empirically validated domain:
- **Roster Churn Contract**: Roster adjustments exceeding **4 starter changes** immediately trigger `SCENARIO_UNSUPPORTED`.
- **Zero Extrapolation**: The model refuses to extrapolate probabilities for uncalibrated formations or wholesale squad overhauls.
- **Epistemic Classification**: Supported outputs are explicitly labeled `COUNTERFACTUAL_MODELLED`.
