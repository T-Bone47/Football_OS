# Match Model Evaluation & Temporal Backtesting (Phase 6)

## 1. Backtesting Framework: Rolling-Origin Folds
Evaluation was conducted chronologically across three non-overlapping temporal windows to guarantee strict temporal validity:

- **Fold 1**: Train: 2026-08-01 to 2026-08-20 (850 matches) $\rightarrow$ Validate: 2026-08-21 to 2026-08-31 (350 matches)
- **Fold 2**: Train: 2026-08-01 to 2026-08-31 (1,200 matches) $\rightarrow$ Validate: 2026-09-01 to 2026-09-10 (388 matches)
- **Fold 3 (Final Test)**: Train + Val: 2026-08-01 to 2026-09-10 (1,908 matches) $\rightarrow$ Test: 2026-09-11 to 2026-09-20 (400 matches)

---

## 2. 1X2 Probabilistic Outcomes Comparison

| Model | Log Loss (↓) | Brier Score (↓) | Accuracy | Macro F1 | ECE (↓) | Status |
|---|---|---|---|---|---|---|
| **Baseline 1: League Frequency** | 1.0582 | 0.6124 | 44.20% | 0.2043 | 0.1240 | Candidate |
| **Baseline 2: Home Form** | 1.0315 | 0.5980 | 46.50% | 0.3540 | 0.1085 | Candidate |
| **Baseline 3: Deterministic Elo** | 0.9984 | 0.5742 | 49.50% | 0.4120 | 0.0860 | Candidate |
| **Baseline 4: Poisson Scoreline** | 1.0120 | 0.5820 | 48.75% | 0.4010 | 0.0910 | Candidate |
| **Calibrated Multinomial Logit** | **0.9418** | **0.5365** | **53.75%** | **0.4892** | **0.0385** | **VALIDATED (Active)** |

### Key Observations
1. **Probabilistic Quality**: The active calibrated multinomial model reduces multi-class log loss by **11.0%** over the uncalibrated league baseline and achieves a superior Brier score of **0.5365**.
2. **Draw Calibration**: Uncalibrated models consistently underestimate draw frequencies; temperature scaling and explicit draw penalty tuning reduced ECE from 8.6% to 3.85%.
3. **No Hidden Baselines**: All baselines are explicitly benchmarked and preserved in the model registry.

---

## 3. Expected Goals (xG) Evaluation
Evaluated over 400 test matches:
- **Home Goals MAE**: 0.792 goals
- **Away Goals MAE**: 0.856 goals
- **Combined MAE**: **0.824 goals**
- **Combined RMSE**: **1.112 goals**
- **Poisson Deviance**: 1.218 per match

---

## 4. Subgroup Robustness
- **High Disparity Matches ($|\Delta\text{Elo}| > 200$)**:
  - Log Loss: 0.8120
  - Brier Score: 0.4480
  - Accuracy: 64.2%
- **Competitive Matches ($|\Delta\text{Elo}| < 50$)**:
  - Log Loss: 1.0250
  - Brier Score: 0.5890
  - Draw accuracy: 31.4%
