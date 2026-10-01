# Valuation Baseline Methodology
**Football Intelligence OS — Phase 4.1M & 4.1N**  
**Date**: September 2026  
**Status**: APPROVED & ACTIVE  

---

## 1. Executive Summary

Prior to engineering machine learning models (e.g. XGBoost, LightGBM, CatBoost) in Phase 4.2, Football Intelligence OS requires an empirical, deterministic **Valuation Baseline**.

The baseline fulfills four operational purposes:
1. **Defensibility**: Provides a transparent benchmark anchored directly in historical comparable transactions.
2. **Benchmark Metric**: Establishes the baseline error floor ($MAE_{\text{baseline}}$, $RMSE_{\text{baseline}}$) that any subsequent machine learning model must convincingly beat.
3. **Hard Sufficiency Gate**: Enforces that if comparable sample size is too small ($n < 3$), the system halts and outputs `VALUATION_UNAVAILABLE` rather than generating a fictitious number.
4. **Uncertainty Bounds Foundation**: Surfaces Interquartile Range (IQR) bounds only when statistically grounded ($n \ge 5$), returning `RANGE_NOT_AVAILABLE` otherwise.

---

## 2. Baseline Mathematical Formulation

For target player $i$ evaluated at timestamp $T$:
1. Retrieve the qualified historical comparable transactions:
   $$\mathcal{C}_i(T) = \left\{ t_j \mid t_j \le T,\; \text{is\_permanent}(j) = \text{True},\; \text{pos\_group}(j) = \text{pos\_group}(i),\; \text{fee}(j) > 0 \right\}$$
2. If $|\mathcal{C}_i(T)| < 3$:
   $$\text{status} = \text{VALUATION\_UNAVAILABLE},\quad \hat{V}_i(T) = \text{null}$$
3. If $|\mathcal{C}_i(T)| \ge 3$:
   $$\tilde{M}_i = \text{median}\left(\left\{ \text{fee}_{\text{EUR}}(j) \mid j \in \mathcal{C}_i(T) \right\}\right)$$
4. Apply the documented deterministic **Age Curve Adjustment** $f_{\text{age}}(\text{age}_i(T))$:
   $$\hat{V}_i(T) = \tilde{M}_i \times f_{\text{age}}(\text{age}_i(T))$$

### Empirical Age Curve Multipliers

| Age Range | Multiplier | Economic Rationale |
| :--- | :--- | :--- |
| $\text{age} < 21$ | **1.15** | High developmental upside, long contract horizon, premium resale option. |
| $21 \le \text{age} < 24$ | **1.10** | Proven top-flight output with significant remaining career horizon. |
| $24 \le \text{age} \le 28.5$| **1.00** | Peak career maturity and immediate tactical readiness (Neutral baseline). |
| $28.5 < \text{age} \le 31$ | **0.85** | Limited resale value; contracting duration discount. |
| $\text{age} > 31$ | **0.65** | Veteran contract depreciation; zero resale expectation. |

---

## 3. Uncertainty Interval Foundation (Phase 4.1O)

A single point valuation without an uncertainty interval conveys false precision. The baseline uses the empirical Interquartile Range (IQR) of the comparable cohort:

$$\text{Lower Bound} = Q_1(\mathcal{C}_i) \times f_{\text{age}}$$
$$\text{Upper Bound} = Q_3(\mathcal{C}_i) \times f_{\text{age}}$$

### Statistical Gating Rules
- If sample size $|\mathcal{C}_i| \ge 5$:
  $$\text{range\_status} = \text{RANGE\_AVAILABLE}$$
- If sample size $|\mathcal{C}_i| < 5$:
  $$\text{range\_status} = \text{RANGE\_NOT\_AVAILABLE},\quad \text{Lower Bound} = \text{null},\quad \text{Upper Bound} = \text{null}$$

**Zero Fabrication Rule**: The system strictly refuses to manufacture arbitrary percentage buffers (e.g. $\pm 15\%$) when the empirical cohort has fewer than 5 comparable transactions.

---

## 4. Temporal Train / Test Validation (Phase 4.1N)

The baseline is evaluated using chronological train/test separation (never random k-fold shuffling):
- **Training Universe**: Historical transfers executed before cutoff date $T_{\text{split}}$.
- **Test Universe**: Historical transfers executed on or after $T_{\text{split}}$.

Evaluation Metrics:
- **MAE (Mean Absolute Error)**: Average absolute magnitude of fee error.
- **RMSE (Root Mean Squared Error)**: Sensitivity to high-value outlier errors.
- **MedAE (Median Absolute Error)**: Robust central tendency error unskewed by extreme mega-transfers.
