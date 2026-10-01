# Phase 14 — Model Calibration Feedback & Governed Challenger Architecture

**Certified Baseline**: Phase 13 — `DECISION_SIMULATION_VALIDATED`  
**Current Phase**: Phase 14 — `OUTCOME_AWARE_DECISION_INTELLIGENCE`  
**Core Epistemic Rule**: Empirical prediction realizations are tracked across versioned windows. Models are **never automatically retrained or promoted** based on isolated outcome metrics. Promotion requires formal governed verification.

---

### 1. Probabilistic Calibration Feedback Loop

The `PredictionCalibrationFeedbackEngine` pairs historical match forecasts with real-world observed match outcomes:

```
[ MODEL FORECAST ] (Frozen Snapshot)
  • P(Home Win) = 0.62
  • P(Draw)     = 0.23
  • P(Away Win) = 0.15
         │
         ▼
[ REALIZED MATCH OUTCOME ] (Outcome Ledger)
  • Result: Home Win (Class 0)
  • Observed Whistle: 2024-04-23
         │
         ▼
[ SLIDING WINDOW EVALUATOR ] (N = 30, 50, 100)
  • Multi-Class Log Loss (Cross-Entropy)
  • Multi-Class Brier Score (Scoring Rule)
  • Expected Calibration Error (ECE across 10 deciles)
  • Maximum Calibration Error (MCE)
  • Reliability Curve Regression Slope & Intercept
```

---

### 2. Multi-Class Scoring Standards

1. **Multi-Class Log Loss**:
   $$\text{LogLoss} = -\frac{1}{N} \sum_{i=1}^N \ln(p_{i, y_i})$$
   Evaluates probabilistic fidelity with severe penalties for overconfident mispredictions. Random benchmark: $\approx 1.0986$.
2. **Multi-Class Brier Score**:
   $$\text{Brier} = \frac{1}{N} \sum_{i=1}^N \sum_{k=1}^K (p_{i, k} - \mathbb{I}(y_i = k))^2$$
   Quadratic strictly proper scoring rule. Perfect: $0.0$; random 3-class baseline: $\approx 0.6670$.
3. **Expected Calibration Error (ECE)**:
   $$\text{ECE} = \sum_{b=1}^B \frac{|B_b|}{N} \left| \text{acc}(B_b) - \text{conf}(B_b) \right|$$
   Measures the average gap between forecasted probability and empirical win frequency across 10 confidence deciles.

---

### 3. Contextual Subgroup Monitoring (Zero Silent Averaging)

Global metrics frequently mask severe performance breakdown in critical contextual slices. The Phase 14 engine mandates disaggregation across:
- **Competition**: Premier League vs Championship vs European Cups.
- **Pitch Position**: Central Defenders vs Wingers vs Strikers.
- **Career Phase**: U21 Development vs Peak 25–28 vs Veteran 29+.
- **Distribution State**: In-Distribution vs Out-of-Distribution (OOD).

**Sufficiency Rule**: If a subgroup sample size $N < 10$, metrics are flagged as `LOW_SAMPLE` and formal promotional evaluations are withheld.

---

### 4. Governed Challenger Evaluation Standard

When a challenger model is proposed:
1. It is evaluated over **strictly identical historical realization windows**.
2. Both champion and challenger are subjected to the same leakage rules and target definitions.
3. Lower log loss alone is insufficient: the challenger must demonstrate superior or equal calibration (ECE) and stability across all context subgroups.
4. Human sign-off by the Data Operations and Head of Analytics is recorded prior to production promotion.
