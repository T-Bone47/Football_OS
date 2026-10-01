# PHASE 15 — UNIFIED MODEL ERROR RESEARCH
## Contextual Error Slicing across 8 Axes without Aggregate Smoothing

---

### 1. The 8 Contextual Error Slices

To prevent weak model segments from being masked by aggregate performance, error metrics (Brier score, Log Loss, MAE, ECE) are disaggregated across:

1. **`GLOBAL`**: Overall benchmark across all evaluated instances.
2. **`COMPETITION`**: Individual leagues (EPL, La Liga, Serie A, Bundesliga, Ligue 1).
3. **`POSITION`**: Positional groups (GK, DF, MF, FW).
4. **`ROLE`**: Specific tactical archetypes (Inverted Fullback, Deep-Lying Playmaker, Poacher).
5. **`AGE`**: Developmental brackets (U21, 21–24, 25–29, 30+).
6. **`CONFIDENCE`**: High, medium, and low confidence prediction bins.
7. **`OOD`**: In-domain vs marginal vs severe out-of-distribution instances.
8. **`TIME`**: Rolling temporal quarters/seasons to detect calibration drift.

---

### 2. Failure Boundary Identification

The Model Error Research Engine (`apps/api/app/phase15/model_error_research.py`) automatically flags weak subgroups:
- **`SEVERE_ERROR`**: Error metric exceeds the global baseline by more than $35\%$.
- **`MODERATE_DRIFT`**: Expected Calibration Error (ECE) $> 0.10$.
- **`INSUFFICIENT_SAMPLE`**: Subgroup $N < 10$.

Every weak subgroup is logged in the `weakest_subgroups` audit registry. Silent averaging away of weak performance is strictly audited and prevented.
