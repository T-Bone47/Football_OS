# PHASE 15 — CROSS-COMPETITION GENERALIZATION & DOMAIN SHIFT
## Validating Transferability across Tier-1 Leagues without False Equivalence

---

### 1. Generalization Framework

The Cross-Competition Generalization Engine (`apps/api/app/phase15/cross_competition_generalization.py`) explicitly tests model transferability:

1. **Train Same $\to$ Test Same (`IN_DOMAIN`)**:
   - Baseline validation within the training competition.
2. **Train Competition $\to$ Test Different Competition (`CROSS_DOMAIN`)**:
   - Out-of-league transferability test. Quantifies degradation gap:
     $$\Delta_{\text{generalization}} = \frac{|\text{MAE}_{\text{cross}} - \text{MAE}_{\text{in}}|}{\text{MAE}_{\text{in}}}$$
3. **Train Multi-Competition $\to$ Held-Out Competition**:
   - Evaluates whether pooling multiple leagues achieves out-of-sample generalization or exacerbates domain shift.

---

### 2. Generalization Domain Classification

- **`IN_DOMAIN`**: Training and testing datasets originate from identical competition distributions.
- **`CROSS_DOMAIN`**: Model tested on a different league. If degradation $\le 15\%$, marked `VALIDATED`; if $15\% - 35\%$, marked `PARTIALLY_VALIDATED`; if $> 35\%$, marked `UNCALIBRATED`.
- **`LOW_SUPPORT`**: Test sample size $N < 15$.
- **`OOD`**: Population Stability Index (PSI) $> 0.25$ or explicit domain mismatch. Cannot be marked `VALIDATED`.

---

### 3. Anti-Pooling Doctrine

Competitions must never be silently pooled without reporting disaggregated cross-league metrics. A global metric that smooths away poor performance in Ligue 1 or Serie A constitutes an architectural failure.
