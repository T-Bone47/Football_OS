# Match Prediction Methodology (Phase 6)

## 1. Probabilistic Football Intelligence Core Principles
Football outcomes are intrinsically stochastic. The primary objective is **not** to produce overconfident categorical classifications, but rather to evaluate well-calibrated, explainable probability distributions over:
1. **1X2 Outcome Probabilities**: $P(\text{Home Win}) + P(\text{Draw}) + P(\text{Away Win}) = 1.0$ (strictly within numerical tolerance $< 10^{-3}$).
2. **Pre-Match Expected Goals (xG)**: Independent attack and defense intensities $\lambda_H$ and $\mu_A$.
3. **Scoreline Distribution**: Joint bivariate probability matrix over realistic scorelines $[0..6] \times [0..6]$ with Dixon-Coles adjustment for low scores.

---

## 2. Chronological & Temporal Validation
Random cross-validation produces disastrous lookahead bias in sports forecasting. This system exclusively employs **Chronological Rolling-Origin Backtesting**:
- Matches are ordered strictly by kickoff datetime.
- Training occurs strictly on matches prior to $T_{\text{train\_end}}$.
- Temperature scaling calibration is fitted exclusively on $T_{\text{train\_end}} < t \le T_{\text{val\_end}}$.
- Evaluation is performed on untouched test fixtures $t > T_{\text{val\_end}}$.

---

## 3. Team Strength & Elo Engine
The team rating engine provides a continuous, deterministic baseline:
- **Initial Rating**: 1500.0
- **Base K-Factor**: 32.0
- **Home Advantage ($\Delta H$)**: +65.0 rating points
- **Margin of Victory Multiplier**: World Football Elo standard:
  $$\text{Multiplier} = \begin{cases} 1.0 & \text{if } |GF - GA| \le 1 \\ 1.5 & \text{if } |GF - GA| = 2 \\ \frac{11 + |GF - GA|}{8} & \text{if } |GF - GA| \ge 3 \end{cases}$$
- **Zero-Sum Exchange**: Rating updates are strictly zero-sum between opponents.
- **Pre-Match Freezing**: Team ratings are computed strictly chronologically and frozen as of match kickoff.

---

## 4. Bivariate Poisson Goal Model & Dixon-Coles Adjustment
Goals are modeled as Poisson processes adjusted for correlation in low-scoring draws:
$$P(X=x, Y=y) = \tau(x, y, \lambda_H, \mu_A, \rho) \cdot \frac{\lambda_H^x e^{-\lambda_H}}{x!} \cdot \frac{\mu_A^y e^{-\mu_A}}{y!}$$
where Dixon-Coles correction $\tau(x, y)$ applies:
$$\tau(0,0) = 1 - \lambda \mu \rho$$
$$\tau(0,1) = 1 + \lambda \rho$$
$$\tau(1,0) = 1 + \mu \rho$$
$$\tau(1,1) = 1 - \rho$$
$$\tau(x,y) = 1 \quad \forall x+y > 2$$

Empirical correlation parameter $\rho = -0.045$.
From this joint distribution, secondary markets are derived deterministically:
- $P(\text{Over } 2.5) = \sum_{x+y > 2} P(x, y)$
- $P(\text{Under } 2.5) = 1.0 - P(\text{Over } 2.5)$
- $P(\text{BTTS}) = \sum_{x \ge 1, y \ge 1} P(x, y)$

---

## 5. Model Architecture & Baselines Hierarchy
The prediction engine evaluates a hierarchy of baseline models before serving the active ML ensemble:
1. **Baseline 1 (Class Frequency)**: Static historical league distribution ($P_H=0.442, P_D=0.260, P_A=0.298$).
2. **Baseline 2 (Home Form)**: Empirical baseline adjusted by recent 5-match rolling points differential.
3. **Baseline 3 (Deterministic Elo)**: Logistic outcome curve parameterized by Elo rating gap.
4. **Baseline 4 (Poisson Goals)**: Aggregated 1X2 win probabilities derived from the Dixon-Coles scoreline matrix.
5. **Active Predictor (Calibrated Multinomial Logit)**: Multinomial ensemble combining Elo disparity, rolling form, attack/defense parameters, and rest fatigue, calibrated with validation Temperature Scaling ($T=1.06$).
