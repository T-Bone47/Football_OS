# Multi-Dimensional Player Similarity & Explainability Engine (Phase 2 Slice 2)

## 1. Core Principle: Multi-Dimensional vs. Naive Distance

Player similarity must never be a single naive Euclidean distance across raw unnormalized statistics. In Football Intelligence OS, similarity decomposes into three distinct analytical components:

$$\text{Overall Similarity} = w_{\text{stat}} \cdot S_{\text{stat}} + w_{\text{role}} \cdot S_{\text{role}} + w_{\text{context}} \cdot S_{\text{context}}$$

Default weights:
- $w_{\text{stat}} = 0.50$ (Statistical Similarity)
- $w_{\text{role}} = 0.35$ (Functional Role Tendency Similarity)
- $w_{\text{context}} = 0.15$ (Positional & Exposure Alignment)

---

## 2. Similarity Components

### A. Statistical Similarity ($S_{\text{stat}}$)
- **Vector Space**: Standardized feature vectors derived from the role feature registry.
- **Metric**: Scale-invariant cosine similarity:
  $$\cos(u, v) = \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
  Mapped to $[0.0, 1.0]$ via $\frac{\cos(u, v) + 1.0}{2.0}$.
- **Rationale**: Captures whether two players distribute their efforts in similar statistical proportions, independent of raw volume fluctuations.

### B. Role Similarity ($S_{\text{role}}$)
- **Vector Space**: Continuous 9-dimension profile scores $[0.0, 1.0]^9$:
  `distribution`, `progression`, `creation`, `finishing`, `defending`, `duels`, `carrying`, `discipline`, `goalkeeping`.
- **Metric**: Normalized Euclidean distance:
  $$S_{\text{role}} = 1.0 - \frac{\|s_a - s_b\|_2}{\sqrt{9}}$$
- **Rationale**: Two players might achieve comparable functional role profiles through different discrete sub-metrics (e.g., progressive carries vs. progressive passes). Comparing role profile representations guarantees tactical alignment.

### C. Contextual Similarity ($S_{\text{context}}$)
- **Positional Compatibility**:
  - Exact position group match: $1.0$
  - Adjacent functional family (e.g. `DEF` and `MID` or `MID` and `ATT`): $0.50$
  - Divergent family (e.g. `GK` and `ATT`): $0.10$
- **Sample Exposure Alignment**:
  - Compares playing time maturity to prevent matching an established regular (e.g., 2,000 minutes) with an untested substitute (90 minutes):
    $$\text{Exposure Ratio} = \frac{\min(\text{mins}_a, \text{mins}_b)}{\max(\text{mins}_a, \text{mins}_b, 1)}$$
- Composite contextual score: $0.70 \cdot \text{PosSim} + 0.30 \cdot \text{ExposureRatio}$.

---

## 3. Explainability Engine: "Why Similar" & "Why Not Similar"

A similarity score without a rationale is unacceptable for professional scouting and tactical recruitment.

The engine computes absolute delta differences $\Delta_d = |s_{a, d} - s_{b, d}|$ across all dimensions:

1. **Why Similar**:
   Identifies shared functional strengths where:
   - Delta is small ($\Delta_d \le 0.20$)
   - Both players have strong or active engagement ($\bar{s}_d \ge 0.40$)
   - Formats human-readable explanations (e.g., *"Both players exhibit high progression tendencies (0.82 vs 0.79, delta 0.03)."*)

2. **Why Not Similar**:
   Identifies key points of tactical divergence where:
   - Delta is largest ($\Delta_d \ge 0.15$)
   - Explains the directional divergence (e.g., *"Divergence in defending: Player A (0.85) rates significantly higher than Player B (0.35) with delta 0.50."*)

---

## 4. REST API Surface

| Endpoint | Method | Response Model | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/players/{id}/role` | `GET` | `RoleArchetypeResponse` | Concise data-driven archetype classification, dominant dimensions, and sample status. |
| `/api/v1/players/{id}/role-profile` | `GET` | `RoleProfileResponse` | Continuous 9-dimension profile scores, standardized feature vector, and provenance. |
| `/api/v1/players/{id}/similar` | `GET` | `SimilarPlayersResponse` | Top-N similar candidates with composite/component scores, why similar, and why different. |
| `/api/v1/players/{id}/similarity/{other_id}` | `GET` | `PlayerComparisonResponse` | Direct head-to-head comparison with dimensional deltas and explainability breakdown. |

### Query Parameters
- `as_of`: Optional temporal cutoff for point-in-time historical evaluation.
- `limit`: Result count for similar candidate lists (default: 10, max: 50).
- `position_filter`: Optional filter by position group (`GK`, `DEF`, `MID`, `ATT`).
- `min_minutes`: Minimum sample minutes required for candidate inclusion.

---

## 5. Limitations & Next Steps

1. **League Strength Adjustment**: Contextual similarity does not yet scale for inter-league difficulty gaps; that capability belongs in the upcoming contextual benchmarking slice.
2. **Tactical Fit Engine**: Role similarity evaluates functional profile compatibility between players, not player-to-manager tactical system suitability (Phase 2 Slice 3).
3. **Valuation**: No market value or recruitment fee calculations are applied at this layer.
