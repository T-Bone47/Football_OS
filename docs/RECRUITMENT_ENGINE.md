# Deterministic Recruitment Target Engine (Phase 7)

## 1. Overview
The Recruitment Target Engine is a 13-stage deterministic pipeline connecting squad requirements, tactical systems, contribution analytics, market valuations, transfer risk, and squad impact into auditable candidate assessments.

The engine operates on a fundamental mandate: **Never rank a player simply because they possess a high generic overall score.** Every recommendation must articulate **why** the candidate satisfies specific tactical, financial, and squad needs, and **where** they diverge.

---

## 2. The 13-Stage Recruitment Pipeline

```
[1. Squad Need] ──> [2. Tactical Requirement] ──> [3. Candidate Pool]
                                                            │
                                                            ▼
                                                   [4. Hard Constraints]
                                                            │
                                              ┌─────────────┴─────────────┐
                                           (Passed)                    (Excluded)
                                              │                            │
                                              ▼                            ▼
                           [5. Player Intelligence]             [Log Exclusion Reasons]
                                      │
                                      ▼
                             [6. Tactical Fit]
                                      │
                                      ▼
                        [7. Contribution Similarity]
                                      │
                                      ▼
                        [8. Replacement Similarity]
                                      │
                                      ▼
                           [9. Market Valuation]
                                      │
                                      ▼
                            [10. Transfer Risk]
                                      │
                                      ▼
                            [11. Squad Impact]
                                      │
                                      ▼
                        [12. Evidence Completeness]
                                      │
                                      ▼
                      [13. Explainable Candidate Output]
```

### Detailed Stages:
1. **Identify Squad Requirement**: Maps position (`GK`, `DEF`, `MID`, `ATT`), role archetype, and age target.
2. **Identify Tactical Requirement**: Loads pre-configured tactical context (e.g. `433_cm_progressive_midfielder`), positional group constraints, and requirement weights.
3. **Identify Candidate Universe**: Queries active squad registries and indexed transfer profiles within temporal snapshot bounds.
4. **Apply Hard Constraints**: Evaluates non-negotiable parameters:
   - Position compatibility.
   - Budget ceiling: Estimated transfer fee $\le$ Budget constraint.
   - Age window: $\text{min\_age} \le \text{age} \le \text{max\_age}$.
   - Minutes floor: Verified appearances and season minutes $\ge \text{min\_minutes}$.
   - Risk tolerance threshold: Excludes critical risk targets if user specifies `LOW` or `MEDIUM` tolerance.
   - *Candidates failing any hard constraint are immediately excluded and cataloged with specific rejection reasons.* Soft scores never override hard constraints.
5. **Calculate Player Intelligence Compatibility**: Retrieves contribution ratings, percentile peer rankings, and career trajectory (`ASCENDING`, `PEAK`, `STABLE`, `DECLINING`).
6. **Calculate Tactical Fit**: Evaluates capability weights against tactical requirements (e.g. progression, pressing intensity, defensive actions).
7. **Calculate Contribution Similarity**: Determines statistical parity across action value vectors.
8. **Calculate Replacement Similarity**: When executing replacement analysis, computes cosine similarity against the departed player's profile.
9. **Calculate Market Affordability**: Predicts valuation baseline via GBR/Cohort engines, determines fee bounds $[0.85 \times V, 1.20 \times V]$, and assigns affordability tier (`AFFORDABLE`, `BUDGET_STRETCH`, `UNAFFORDABLE`).
10. **Calculate Transfer Risk**: Synthesizes adaptation risk (league translation, cross-border moves), performance risk (sample depth, age decay), financial risk (capital commitment ratio), and availability risk (match availability).
11. **Calculate Squad Impact**: Computes squad depth transition (`THIN` $\to$ `HEALTHY`), formation slot coverage, and flags whether the candidate represents a net quality upgrade or rotational depth.
12. **Calculate Evidence Completeness**: Evaluates sample size, model coverage, and OOD status into Data, Model, and Decision confidence scores.
13. **Produce Explainable Candidate Assessments**: Generates human-readable `why_matches` and `where_differs` bullet points grounded in explicit analytical metrics.

---

## 3. Multi-Factor Deterministic Ranking (Soft Evidence)
For candidates passing all hard constraints, soft evidence components are weighted to produce an explainable ranking:

$$\text{Score} = 0.35 \cdot S_{\text{tactical}} + 0.35 \cdot S_{\text{performance}} + 0.15 \cdot S_{\text{affordability}} + 0.15 \cdot (1 - \text{Risk})$$

Where:
- $S_{\text{tactical}} = \frac{\text{TacticalFitScore}}{100}$
- $S_{\text{performance}} = \frac{\text{ContributionRating}}{100}$
- $S_{\text{affordability}} = 1.0 \text{ if AFFORDABLE else } 0.60$
- $\text{Risk} = \text{OverallRiskScore} \in [0, 1]$

No black-box or non-deterministic re-ranking is permitted.
