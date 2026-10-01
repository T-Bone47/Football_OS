# PHASE 15 — HYPOTHESIS GOVERNANCE & INDEPENDENT VALIDATION
## Lifecycle Verification, Holdout Cohorts, and Anti-Leakage Controls

---

### 1. The Governed Hypothesis Lifecycle

In the Football Intelligence OS, hypotheses undergo strict epistemic progression:

```
[Discovered Pattern] ──> [Research Hypothesis] ──> [Testing Cohort]
                                                          │
          ┌───────────────────────────┬───────────────────┴───────────────────┐
          ▼                           ▼                                       ▼
    [VALIDATED]                  [REJECTED]                       [INSUFFICIENT_EVIDENCE]
  (Replicated in Holdout)     (Effect nullified / Leakage)        (Holdout Sample N < 20)
          │
          ▼
 [Production Candidate]
 (Shadow Model Tracking)
          │
          ▼
     [PROMOTED]
 (Human-Governed Signoff)
```

---

### 2. Validation Methodologies

Every hypothesis submitted to `/api/v1/research/validate` must undergo independent validation:
1. **`INDEPENDENT_COHORT`**: Re-evaluating the candidate relationship on a non-overlapping cohort of players/teams.
2. **`TEMPORAL_HOLDOUT`**: Evaluating historical data strictly within a subsequent temporal slice ($T_{\text{train}} < T_{\text{holdout}}$).
3. **`COMPETITION_HOLDOUT`**: Validating whether the pattern replicates in a different competition.
4. **`NEGATIVE_CONTROL`**: Verifying that randomized or placebo feature slices exhibit null effects.

---

### 3. Leakage & Adversarial Safeguards

- **Temporal Anti-Leakage**: If any data points in the validation cohort have observation timestamps prior to or overlapping with training data in a manner that causes data contamination, the validation is immediately disqualified and marked `NOT_SUPPORTED`.
- **Epistemic Invariance**: Under no circumstances does a hypothesis change its epistemic modality to `OBSERVED`. Observations are empirical measurements; hypotheses are testable explanations.
