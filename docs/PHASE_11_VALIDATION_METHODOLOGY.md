# Phase 11 — Cross-Competition Validation Methodology

## 1. Principles of Independent Cross-Competition Validation

Validation in Phase 11 is built upon statistical rigor and epistemic honesty. We explicitly reject:
- Pooling competitions without formal homogeneity tests.
- Claiming high predictive power based on in-sample metrics.
- Reporting accuracy without calibration metrics (Brier, Log Loss, ECE).
- Permitting test set information to leak into probability calibration.

---

## 2. Validation Metrics Framework

For every model and competition under evaluation, six primary metric categories are calculated:

### A. Categorical Outcome Metrics (Match Prediction)
1. **Multi-class Log Loss (Cross-Entropy)**:
   $$\mathcal{L} = -\frac{1}{N} \sum_{i=1}^N \sum_{c=1}^C y_{i,c} \ln(p_{i,c})$$
2. **Multi-class Brier Score**:
   $$\text{Brier} = \frac{1}{N} \sum_{i=1}^N \sum_{c=1}^C (p_{i,c} - y_{i,c})^2$$
3. **Expected Calibration Error (ECE)**:
   Dividing predictions into $M=10$ equally spaced confidence bins:
   $$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
4. **Maximum Calibration Error (MCE)**:
   $$\text{MCE} = \max_{m \in \{1,\dots,M\}} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
5. **Accuracy & Macro F1 Score**: Overall discriminative ability.

### B. Continuous Regression Metrics (Transfer Valuation)
1. **Mean Absolute Error (MAE)** & **Median Absolute Error (MedAE)**
2. **Root Mean Squared Error (RMSE)**
3. **Log MAE & Log RMSE** (robust to heavy-tailed transfer fees)
4. **Coefficient of Determination ($R^2$)**: Realized on test split only.

---

## 3. Probability Calibration Architecture (§9)

The system implements `ProbabilityCalibrationEngine` (`app/phase11/calibration_engine.py`) supporting:
- **Temperature Scaling**: Single parameter $T > 0$ optimizing categorical logits: $p_i = \text{softmax}(z_i / T)$.
- **Isotonic Regression**: Non-parametric piecewise constant isotonic fitting per class.
- **Platt Scaling**: Logistic sigmoid calibration.

### Zero-Leakage Protocol
```
Raw Training Dataset (t <= T_train)
         │
         ▼
[Base Model Fitting] ──> Base Model (raw uncalibrated logits)
                               │
                               ▼
Validation Dataset (T_train < t <= T_val)
         │
         ▼
[Calibration Fitting] ──> Calibrator Parameters (e.g. T=1.06)
                               │
                               ▼
Test Holdout Dataset (t > T_val)
         │
         ▼
[Final Evaluation] ──> OOS Unbiased Log Loss, Brier, ECE
```

Under this protocol:
- Test holdouts are NEVER touched during calibration fitting.
- If $N_{\text{val}} < 30$, calibration is aborted and `CalibrationStatus.UNCALIBRATED` is assigned.
- If post-calibration ECE degrades on validation data, the calibrator is rejected and raw probabilities are retained.

---

## 4. Multi-Engine Validation Protocol (§11–§15)

Validation extends beyond match prediction to cover all five core analytical engines:

| Engine | Primary Method | Validation Metric | Target Class Policy |
|:---|:---|:---|:---|
| **Match Prediction** | Poisson/Logit Goal Distribution | Multi-class Log Loss, Brier, ECE | Realized 90-min Full Time Results |
| **Player Intelligence** | Contribution Vector & Role Profiling | Coverage Rate, Minutes Gate ($M \ge 450$) | High confidence requires $M \ge 900$ |
| **Tactical Fit** | 4-Dimensional Fit Engine | Dimension Fit Stability & Role Coverage | Suitability score only (no causal outcome claims) |
| **Player Similarity** | Position-Gated Cosine & Euclidean | Top-$K$ Perturbation Stability Index | Top-5 overlap under feature perturbation |
| **Transfer Valuation** | Gradient Boosted Regressor (`GBR_v1.0`) | Log MAE, MedAE, $R^2$ on Test | `KNOWN_FEE` only (undisclosed/free excluded) |
| **Transfer Risk** | Associative Multi-Risk Classifier | Risk Category Alignment, Availability | Purely associative risk factors |

---

## 5. Temporal Cross-Validation & Rolling Origin

For domestic league evaluations with $N \ge 100$, evaluation employs rolling-origin temporal splits:
- Fold 1: Train Matchdays 1–19, Validate Matchdays 20–28, Test Matchdays 29–38.
- Fold 2: Train Matchdays 1–28, Validate Matchdays 29–33, Test Matchdays 34–38.

This guarantees that temporal seasonality, mid-season manager changes, and January transfer window shifts are faithfully represented in validation telemetry.
