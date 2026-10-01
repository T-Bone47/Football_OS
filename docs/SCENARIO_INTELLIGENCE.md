# Transfer Scenario Intelligence & Match Forecast (Phase 7)

## 1. Overview
The Transfer Scenario Engine extends the Phase 5 squad depth and simulator architecture into a full-spectrum decision simulator. It allows sporting directors and analysts to construct counterfactual roster modifications and evaluate their systemic repercussions across:
1. Squad depth and positional redundancy.
2. Tactical role coverage.
3. Financial expenditure and wage balance.
4. Squad risk transition.
5. Counterfactual match prediction impact.

---

## 2. Epistemological Policy: Categorization of Analytical Signals

To ensure absolute transparency and prevent misleading claims of causality, all scenario metrics are strictly partitioned into four knowledge categories:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATA EPISTEMOLOGY TIERS                         │
├───────────────────────┬────────────────────────────────────────────────┤
│ Category              │ Real-World Grounding & Semantics               │
├───────────────────────┼────────────────────────────────────────────────┤
│ OBSERVED              │ Empirical match stats, confirmed historical    │
│                       │ transfer records, recorded appearances.        │
├───────────────────────┼────────────────────────────────────────────────┤
│ ESTIMATED             │ Conformal valuation ranges, peer percentiles,   │
│                       │ contribution ratings.                          │
├───────────────────────┼────────────────────────────────────────────────┤
│ MODELED               │ Calibrated Poisson match probabilities,         │
│                       │ tactical fit scores.                           │
├───────────────────────┼────────────────────────────────────────────────┤
│ SCENARIO ASSUMPTION   │ Hypothetical roster additions, departures, and │
│                       │ simulated lineup modifications.                │
└───────────────────────┴────────────────────────────────────────────────┘
```

The system **never claims** that acquiring a player causes a specific match outcome.

---

## 3. Financial & Roster Calculations

Given a set of incoming transfers $\mathcal{T}_{in}$ and outgoing transfers $\mathcal{T}_{out}$:
- **Total Expenditure**:
  $$E_{\text{gross}} = \sum_{t \in \mathcal{T}_{in}} \text{Fee}(t)$$
- **Total Receipts**:
  $$R_{\text{gross}} = \sum_{t \in \mathcal{T}_{out}} \text{Fee}(t)$$
- **Net Transfer Spend**:
  $$S_{\text{net}} = E_{\text{gross}} - R_{\text{gross}}$$
- **Remaining Budget**:
  $$B_{\text{remaining}} = B_{\text{initial}} - S_{\text{net}}$$

If $B_{\text{remaining}} < 0$, the scenario is flagged as `BUDGET_DEFICIT`, triggering elevated financial risk.

---

## 4. Match Prediction Integration (Phase 6 Integration)

The engine leverages the validated Phase 6 calibrated match prediction engine (`BivariatePoisson_v1`) to compute a counterfactual scenario projection against an upcoming fixture:

1. **Baseline Match Prediction**:
   Computes $P(\text{Home Win})$, $P(\text{Draw})$, $P(\text{Away Win})$, and $\text{xG}_{\text{home}}, \text{xG}_{\text{away}}$ using the validated baseline model.
2. **Tactical Quality Lift ($\Delta Q$)**:
   $$\Delta Q = \frac{\Delta \text{RoleCoverage}}{100.0} \times 0.15$$
3. **Scenario Projected Win Probability**:
   $$P_{\text{scenario}}(\text{Win}) = \text{clip}\Big(P_{\text{base}}(\text{Win}) + \Delta Q, \ 0.05, \ 0.95\Big)$$
4. **Counterfactual Disclaimer**:
   Every scenario prediction includes a mandatory disclaimer:
   > *"Model scenario projection under hypothetical lineup integration; not an observed empirical match result."*
