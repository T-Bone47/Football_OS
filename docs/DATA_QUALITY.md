# Data Quality, Temporal Integrity & Provenance Architecture

## Overview
Phase 8 enforces strict data quality invariants across the entire data lifecycle—from provider ingestion and feature engineering to counterfactual transfer modeling. The system guarantees temporal replay invariance, future leakage prevention, and truthful error propagation.

---

## 1. Domain Validation Rules & Null Rate Controls

Data assets are validated against rigorous business domain invariants prior to feature calculation:

| Entity | Feature / Metric | Permitted Domain Range | Max Null Rate |
|---|---|---|---|
| **Player** | Age | 15.0 - 45.0 years | 0.0% |
| **Player** | Minutes Played | $\ge 0$ minutes | 0.0% |
| **Player** | Primary Position | `GK`, `DF`, `MF`, `FW` (or standard sub-roles) | 0.0% |
| **Market** | Transfer Fee / Value | €0 - €400,000,000 | < 5.0% |
| **Performance** | Contribution Rating | 0.0 - 99.0 | < 1.0% |
| **Tactical** | Tactical Fit Score | 0.0 - 100.0% | < 1.0% |
| **Prediction** | Pre-Match xG | 0.20 - 4.50 goals | 0.0% |
| **Prediction** | 1X2 Probabilities | $\sum P_i = 1.0 \pm 10^{-4}$ | 0.0% |

---

## 2. Temporal Replay & Future Leakage Invariance

### Temporal Replay Principle
Every decision request accepts an optional `as_of: datetime` parameter. When evaluating a decision at time $T_0$:
- All player matches, statistics, and transfer histories occurring after $T_0$ are strictly excluded from the candidate universe and dimensional scoring.
- Replaying the decision at $T_0$ years later yields **bit-for-bit identical decision outputs, rankings, and evidence graph hashes**.

### Future Leakage Prevention
Match intelligence calculations are evaluated strictly on pre-match evidence up to the fixture kickoff cutoff:
- In-game events (goals, substitutions, yellow/red cards) are excluded from pre-match models.
- Post-match metrics (e.g., actual scorelines, final match ratings) are never used in feature attribution.
- Validated via `tests/unit/test_phase8_reproducibility.py::TestFutureDataInjectionInvariance`.

---

## 3. Decision Confidence Decomposition

Every candidate evaluation produces a multi-factor `ConfidenceDecomposition`:

```python
class ConfidenceDecomposition(BaseModel):
    data_confidence: float        # Completeness of historical minutes & statistics
    model_confidence: float       # In-distribution coverage and model calibration
    decision_confidence: float    # Geometric mean of data and model confidence
    confidence_tier: str          # HIGH, MEDIUM, LOW, INSUFFICIENT_DATA
    data_status: str              # DECISION_AVAILABLE, SQUAD_ALERT, DATA_GAP
    sufficiency_factors: list[str]# Explicit list of validated evidence items
    uncertainty_drivers: list[str]# Identified data gaps or risk drivers
```

### Invariant Demotion Rules:
1. **Sample Floor Invariant**: If a candidate has recorded fewer than 450 historical minutes, the tier is capped at `MEDIUM` or demoted to `LOW` regardless of raw performance scores.
2. **Missing Dimension Invariant**: If market valuation or tactical fit cannot be calculated due to missing provider feeds, the platform registers an uncertainty driver and lowers data confidence.
3. **Out-of-Distribution (OOD) Invariant**: When candidates transition from non-comparable lower-tier leagues, the model confidence is discounted to account for adaptation risk.

---

## 4. Truthful State Surfaces

The frontend and API interfaces strictly prohibit "synthetic green ticks":
- If an endpoint returns 503 or has missing provider coverage, the UI displays explicit warning banners and missingness summaries (`DataQualityPage.js`).
- Incomplete datasets surface actionable caveats rather than fabricated default values.
