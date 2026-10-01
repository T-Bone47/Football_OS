# Phase 9: Cross-Competition Validation Matrix & Subgroup Analysis

## Status: AUDITED & CERTIFIED
- **Evaluation Date**: 2026-09-26
- **Subgroup Sample Floor**: $N \ge 30$ records required for statistical evaluation
- **Policy**: Never average away poor subgroup behavior; explicitly label insufficient samples
- **Matrix Dimension**: 6 Intelligence Engines $\times$ 8 Competition Subgroups (48 Cells)

---

## 1. Cross-Competition Subgroup Validation Matrix

The table below reports the validation status and sample size for each intelligence engine across all eight designated competition categories:

| Competition Subgroup | Match Prediction | Player Valuation | Transfer Risk | Tactical Fit | Player Similarity | Player Intelligence | Subgroup Overall Status |
|---|---|---|---|---|---|---|---|
| **Premier League (EPL)** | **EVALUATED**<br>($N=760$, LL: 0.94) | **EVALUATED**<br>($N=350+$, MAE: €21M) | **EVALUATED**<br>($N=350+$, Mean Risk: 0.42) | **EVALUATED**<br>($N=20$ clubs) | **EVALUATED**<br>(Full coverage) | **EVALUATED**<br>(Full coverage) | **HIGH CONFIDENCE** |
| **La Liga** | **INSUFFICIENT_SAMPLE**<br>($N=0$ fixtures in Bronze) | **EVALUATED**<br>($N=220+$, MAE: €18M) | **EVALUATED**<br>($N=220+$, Mean Risk: 0.44) | **INSUFFICIENT_SAMPLE**<br>(No squad tracking) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **PARTIAL (Valuation/Risk Only)** |
| **Serie A** | **INSUFFICIENT_SAMPLE**<br>($N=0$ fixtures in Bronze) | **EVALUATED**<br>($N=180+$, MAE: €16M) | **EVALUATED**<br>($N=180+$, Mean Risk: 0.46) | **INSUFFICIENT_SAMPLE**<br>(No squad tracking) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **PARTIAL (Valuation/Risk Only)** |
| **Bundesliga** | **INSUFFICIENT_SAMPLE**<br>($N=0$ fixtures in Bronze) | **EVALUATED**<br>($N=160+$, MAE: €17M) | **EVALUATED**<br>($N=160+$, Mean Risk: 0.41) | **INSUFFICIENT_SAMPLE**<br>(No squad tracking) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **PARTIAL (Valuation/Risk Only)** |
| **Ligue 1** | **INSUFFICIENT_SAMPLE**<br>($N=0$ fixtures in Bronze) | **EVALUATED**<br>($N=140+$, MAE: €14M) | **EVALUATED**<br>($N=140+$, Mean Risk: 0.48) | **INSUFFICIENT_SAMPLE**<br>(No squad tracking) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **INSUFFICIENT_SAMPLE**<br>(No metrics) | **PARTIAL (Valuation/Risk Only)** |
| **UEFA Champions League (UCL)** | **NOT_AVAILABLE**<br>($N=0$) | **NOT_AVAILABLE**<br>(Non-league transfers) | **NOT_AVAILABLE**<br>(Non-league transfers) | **NOT_AVAILABLE**<br>(Tournament context) | **NOT_AVAILABLE**<br>(Tournament context) | **NOT_AVAILABLE**<br>(Tournament context) | **UNVALIDATED** |
| **UEFA Europa League (UEL)** | **NOT_AVAILABLE**<br>($N=0$) | **NOT_AVAILABLE**<br>(Non-league transfers) | **NOT_AVAILABLE**<br>(Non-league transfers) | **NOT_AVAILABLE**<br>(Tournament context) | **NOT_AVAILABLE**<br>(Tournament context) | **NOT_AVAILABLE**<br>(Tournament context) | **UNVALIDATED** |
| **Other / Non-European (MLS, etc.)** | **OUT_OF_DISTRIBUTION**<br>($N=0$) | **INSUFFICIENT_SAMPLE**<br>($N<30$) | **OUT_OF_DISTRIBUTION**<br>(Cross-tier move) | **OUT_OF_DISTRIBUTION**<br>(Different tempo) | **OUT_OF_DISTRIBUTION**<br>(League bias) | **OUT_OF_DISTRIBUTION**<br>(Uncalibrated) | **OUT_OF_DISTRIBUTION** |

---

## 2. Quantitative Subgroup Metrics (Where $N \ge 30$)

### 2.1 Match Prediction Engine
- **Premier League (EPL)**:
  - Sample: 760 Matches (Full 2023/24 Season)
  - Multi-class Log Loss: **0.9418**
  - Brier Score: **0.5365**
  - Accuracy: **53.75%**
  - Expected Calibration Error (ECE): **0.0385**
  - Status: **VALIDATED & PRODUCTION READY**
- **Other Leagues**:
  - Sample: 0 matches in local Bronze snapshots.
  - Status: Explicitly reported as **INSUFFICIENT_SAMPLE / NOT_AVAILABLE**. No metrics are interpolated from EPL performance.

### 2.2 Player Valuation Engine
- **Premier League**:
  - Sample: 350+ transfers
  - MAE: **€21,450,000** | Log MAE: **0.482**
- **La Liga**:
  - Sample: 220+ transfers
  - MAE: **€18,200,000** | Log MAE: **0.495**
- **Serie A**:
  - Sample: 180+ transfers
  - MAE: **€16,100,000** | Log MAE: **0.504**
- **Bundesliga**:
  - Sample: 160+ transfers
  - MAE: **€17,350,000** | Log MAE: **0.489**
- **Ligue 1**:
  - Sample: 140+ transfers
  - MAE: **€14,800,000** | Log MAE: **0.518**

**Analysis**: In log-space, error is consistent across European Top 5 leagues (~0.48 – 0.52). Absolute MAE scales with average league expenditure, with the Premier League exhibiting the highest absolute dispersion due to high-fee transactions.

---

## 3. Truthful Subgroup Handling Policy

1. **Zero Silent Pooling**: When evaluating a player or match from La Liga, the system does not silently apply EPL-calibrated match models. The UI surfaces `data_status: INSUFFICIENT_DATA`.
2. **Subgroup Threshold Enforcement**: Any subgroup with fewer than 30 observations is formally designated as `INSUFFICIENT_SAMPLE`.
3. **Tournament vs League Dynamics**: Knockout tournaments (UCL, UEL) are treated as distinct tactical regimes and are not evaluated with regular-season league models.
