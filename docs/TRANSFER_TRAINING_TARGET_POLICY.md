# Transfer Training Target Policy & Supervised Valuation Rules (Phase 4.1B)

## 1. Executive Summary

This policy governs the selection, validation, and inclusion of historical transfer transaction records as supervised targets for subsequent valuation models in Football Intelligence OS. Under strict anti-fabrication and statistical integrity principles, the platform enforces deterministic gating: **no weak, ambiguous, or synthetic targets may silently enter the training set**.

---

## 2. Target Eligibility Classification Matrix

| Fee Status | Transaction Type | Supervised Target Status | Rationale & Policy |
| :--- | :--- | :--- | :--- |
| **`KNOWN_FEE`** | Permanent Deal | **ELIGIBLE** | Official club filing, stock market disclosure, or statutory audited figure. Highest confidence target. |
| **`REPORTED_FEE`** | Permanent Deal | **ELIGIBLE (Verified)** | Press/registry consensus fee. Eligible provided currency is normalized and no unresolved critical discrepancy exists. |
| **`ESTIMATED_FEE`** | Any | **EXCLUDED** | **Excluded by default.** Subjective or proprietary portal estimates introduce external model bias and circular reasoning. |
| **`UNKNOWN_FEE`** | Any | **EXCLUDED** | Lacks quantitative transaction value. Unusable for numerical regression. |
| **`UNDISCLOSED`** | Any | **EXCLUDED** | Explicitly withheld terms. Must never be imputed as zero. |
| **`FREE_TRANSFER`** | Free Agent / Expiry | **SEPARATE CLASS** | Zero financial transfer fee does not equal zero player value; reflects contract expiration. Excluded from permanent transfer fee regression. |
| **`LOAN`** | Temporary Deal | **EXCLUDED** | Loan compensation (loan fee + wage contribution) obeys distinct economic dynamics from asset transfer. Excluded from permanent regression. |

---

## 3. Subgroup Sample Representation Thresholds

To prevent model bias toward a single position or league tier, training data must satisfy minimum subgroup sample sizes before Phase 4.2 ML modeling can be initialized:

1. **Position Groups**:
   - Goalkeepers (`GK`): Minimum **15** verified transactions.
   - Defenders (`DEF`): Minimum **50** verified transactions.
   - Midfielders (`MID`): Minimum **50** verified transactions.
   - Attackers (`ATT`): Minimum **50** verified transactions.
2. **Fee Distribution Bands**:
   - Sub-€10M: Adequate coverage of lower-tier and domestic transfers.
   - €10M – €30M: Mid-market transactions.
   - €30M – €70M: Top-tier domestic and continental moves.
   - \>€70M: Elite marquee transfers.
3. **Age & Career Stage**:
   - U21 (Youth upside premium)
   - 21–24 (Pre-peak development)
   - 25–28 (Peak career performance)
   - 29+ (Veteran depreciation)

---

## 4. Strict Temporal Safety & Zero Leakage

For every transfer transaction occurring at date $T$:

$$\forall \text{feature } f, \quad \text{as\_of}(f) \le T$$

1. **Performance Features**: Minutes, ratings, goals, assists, and contribution scores must reflect matches played strictly prior to $T$.
2. **Tactical & Role Profiles**: Derived strictly from snapshots computed on or before $T$.
3. **Future Data Injection Invariance**: The historical training dataset evaluated at $T$ must remain bit-for-bit identical regardless of whether records dated after $T$ are subsequently ingested.
