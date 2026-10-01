# Similarity Engine V1 vs V2 Evaluation (Phase 3.2H)

## 1. Objective and Enhancement Scope

In Phase 2 Slice 2, the similarity engine computed a single composite similarity score combining statistical, role, and contextual similarity:

$$\text{Similarity}_{\text{V1}} = 0.50 \times \text{Statistical} + 0.35 \times \text{Role} + 0.15 \times \text{Contextual}$$

Phase 3.2 evaluated whether decoupling this into **explicit, dedicated similarity modes** improves recruitment use cases.

---

## 2. Multi-Mode Similarity Architecture (V2)

The upgraded `PlayerSimilarityEngine` introduces 5 distinct similarity modes accessible via `GET /api/v1/players/{id}/similar?mode={mode}`:

1. **`mode=composite` (Default, Backward-Compatible)**:
   - Preserves exact V1 composite calculation for existing UI consumers.
2. **`mode=contribution`**:
   - Focuses strictly on functional output across the 7 normalized contribution dimensions using Euclidean distance:
     $$\text{Sim}_{\text{contrib}} = 1.0 - \frac{\sqrt{\sum_{i=1}^7 (c_{a, i} - c_{b, i})^2}}{\sqrt{7}}$$
   - Answers: *"Who produces the exact same balance of creation, passing, defending, and retention?"*
3. **`mode=role`**:
   - Compares raw 9-dimension archetype tendencies regardless of per-90 volume.
   - Answers: *"Who plays the game with the same tactical habits and positioning?"*
4. **`mode=tactical`**:
   - Blends role tendencies ($60\%$) with statistical features ($40\%$).
5. **`mode=replacement`**:
   - Tailored specifically for recruitment scout workflows:
     $$\text{Sim}_{\text{replacement}} = 0.40 \times \text{Role} + 0.40 \times \text{Contribution} + 0.20 \times \text{Context}$$
   - Answers: *"If we lose this player tomorrow, who can step directly into their tactical role and match their on-pitch contribution within an equivalent competitive exposure?"*

---

## 3. Evaluation Findings

| Criterion | Similarity V1 | Similarity V2 | Assessment |
| :--- | :--- | :--- | :--- |
| **Recruitment Utility** | Generic blend | 5 tailored operational modes | **V2 significantly superior.** |
| **Explainability** | General delta | Dimension-specific why_similar / why_different | **V2 provides granular drivers.** |
| **Backward Compatibility**| N/A | Full backward compatibility (`mode=composite` default) | **Zero regressions.** |
| **Computational Overhead**| Low ($O(N)$) | Low ($O(N)$ in-memory vectorized numpy/python) | Negligible difference. |

### Decision: IMPROVED & IMPLEMENTED
Similarity V2 is fully integrated into `app.roles.similarity`, exposed via `routes_canonical.py`, tested in `test_similarity_v2.py`, and visualized in the Emergent frontend with interactive mode selection tabs.
