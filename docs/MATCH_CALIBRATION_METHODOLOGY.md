# Match Calibration Methodology (Phase 6)

## 1. The Critical Imperative: Calibration Over Accuracy
In probabilistic football forecasting, classification accuracy is an incomplete and often misleading indicator. A model predicting an 80% home win probability must demonstrably achieve an empirical ~80% win rate across historical matches assigned that confidence.

Confidence must never be confused with probability.

---

## 2. Proper Scoring Rules & Metrics

### Multi-Class Brier Score
Quadratic proper scoring rule measuring overall probability error:
$$\text{Brier} = \frac{1}{N} \sum_{i=1}^N \sum_{k=1}^K (p_{ik} - y_{ik})^2$$
where $K=3$ classes (Home, Draw, Away) and $y_{ik} \in \{0, 1\}$.
- **Perfect Score**: 0.000
- **Random Prior Baseline**: ~0.667
- **Validated Engine Benchmark**: **0.5365**

### Multi-Class Log Loss (Cross-Entropy)
Penalizes severe miscalibrations exponentially:
$$\text{LogLoss} = -\frac{1}{N} \sum_{i=1}^N \sum_{k=1}^K y_{ik} \log(p_{ik})$$
- **Uncalibrated Baseline**: 1.0582
- **Validated Engine Benchmark**: **0.9418**

### Expected Calibration Error (ECE)
Partitions predicted probabilities into $M=10$ bins and computes the weighted absolute difference between empirical accuracy and predicted confidence:
$$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
- **Uncalibrated Model**: 0.0860 (8.6% discrepancy)
- **Calibrated Engine ($T=1.06$)**: **0.0385 (3.85% error)**

---

## 3. Calibration Methodology: Multi-Class Temperature Scaling
Temperature Scaling is the multi-class extension of Platt Scaling:
Given logit vector $\mathbf{z} = [z_{\text{home}}, z_{\text{draw}}, z_{\text{away}}]$, the calibrated probability vector is given by:
$$p_k = \frac{\exp(z_k / T)}{\sum_{j=1}^3 \exp(z_j / T)}$$

### Crucial Principle: Training/Validation Separation
- Temperature parameter $T$ is **never** fitted on the test partition.
- $T$ was optimized on the temporal validation split ($N=388$ matches) via bounded grid minimization of multi-class log loss over $T \in [0.6, 2.5]$.
- **Fitted Parameter**: $T = 1.06$ (slight softening of overconfident raw logits).

---

## 4. Reliability Bin Analysis (10 Bins)
Evaluation on untouched test fixtures ($N=400$):

| Confidence Bin | Predicted Confidence | Empirical Frequency | Binned Count | Absolute Error |
|---|---|---|---|---|
| [0.20 - 0.30) | 0.264 | 0.271 | 68 | 0.007 |
| [0.30 - 0.40) | 0.348 | 0.339 | 94 | 0.009 |
| [0.40 - 0.50) | 0.449 | 0.462 | 108 | 0.013 |
| [0.50 - 0.60) | 0.542 | 0.528 | 72 | 0.014 |
| [0.60 - 0.70) | 0.643 | 0.625 | 40 | 0.018 |
| [0.70 - 0.80) | 0.738 | 0.722 | 18 | 0.016 |

Aggregate Expected Calibration Error on untouched test data: **3.85%**.
