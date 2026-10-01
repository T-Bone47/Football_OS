# PHASE 13 — SENSITIVITY & ROBUSTNESS ANALYSIS SPECIFICATION
## Perturbation Testing, Resiliency Classification & Non-Statistical Assumption Bounds

### 1. Architectural Mission
Real-world football recruitment and tactical planning operate under profound uncertainty. The Phase 13 Sensitivity and Robustness Engine stress-tests simulated scenarios against compounding assumption perturbations—such as transfer fee bidding wars, wage inflation, tactical friction, and physical availability shocks.

---

### 2. Sensitivity Analysis (§20)
For every major scenario, the engine calculates low, base, and high bounds across five critical operational dimensions:

| Dimension | Base Parameter | Low Bound | High Bound | Perturbation Rationale |
|:---|:---:|:---:|:---:|:---|
| **Transfer Net Spend** | €20.0M | €17.0M (-15%) | €23.0M (+15%) | Reflects negotiation premiums, add-ons, and agent fees. |
| **Weekly Wage Bill Delta** | -€80k/wk | -€88k/wk (-10%) | -€72k/wk (+10%) | Accounts for performance bonuses and loyalty escalators. |
| **Projected Season Minutes** | 2,400m | 1,920m (-20%) | 2,760m (+15%) | Models tactical rotation and fixture load variations. |
| **Squad Availability Rate** | 88.0% | 76.0% (-12%) | 92.0% (+4%) | Evaluates soft-tissue injury risk and recovery timelines. |
| **Tactical System Fit** | 88.4 | 81.9 (-6.5 pts) | 93.4 (+5.0 pts) | Models tactical adaptation friction vs immediate synergy. |

**Epistemic Rule on Confidence Intervals**:
> Sensitivity intervals represent deterministic assumption bounds and must **never** be presented as empirical statistical confidence intervals unless mathematically derived from sample error distributions. Every interval carries `epistemic_modality = ASSUMPTION` and `statistical_ci = False`.

---

### 3. Scenario Robustness Classification (§21)
Robustness analysis measures how well a scenario withstands simultaneous compounding shocks without violating club operational ceilings:

1. **+10% Transfer Fee Inflation**: Competitive bidding shock.
2. **+12% Wage Bill Escalation**: Salary matching demand shock.
3. **-10% Tactical Adaptation Attenuation**: Integration friction shock.
4. **-15% Squad Depth Shock**: Key rotational absence shock.
5. **Formation Shift Invariance**: Viability across tactical variations (e.g. 4-3-3 to 4-2-3-1).

**Robustness Classes**:
- **`STABLE`** (Resilience $\ge 80.0$): Zero constraints breached. Net spend within budget, wage ceiling preserved, tactical fit intact.
- **`SENSITIVE`** (Resilience $60.0 - 79.9$): One constraint breached (e.g., fee inflation exceeds available transfer headroom).
- **`HIGHLY_SENSITIVE`** (Resilience $< 60.0$): Multiple constraints breached. Scenario value proposition collapses under mild real-world market friction.

> **Robustness vs Probability**: A `STABLE` classification describes scenario structural resilience to parameter variation, not the real-world probability of transaction occurrence.
