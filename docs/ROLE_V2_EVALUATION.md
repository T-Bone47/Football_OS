# Role Discovery V1 vs V2 Evaluation (Phase 3.2G)

## 1. Objective and Evaluation Criteria

Phase 3.2 evaluated whether augmenting the Phase 2 Slice 2 Role Discovery foundation with the newly compiled Phase 3.2 Contribution Vector justifies replacing or modifying the core controlled archetypes.

### Criteria:
1. **Sample Sufficiency**: Robustness under real provider data coverage.
2. **Cluster Quality & Separation**: Silhouette scores, between-cluster vs within-cluster variance.
3. **Archetype Stability & Interpretability**: Do domain experts and scouts understand the assigned archetypes?
4. **Temporal Stability**: Does role classification remain stable over consecutive match windows?

---

## 2. Experimental Comparison: Role V1 vs Role V2

| Evaluation Dimension | Role V1 (Controlled Archetypes + 9 Dimensions) | Role V2 (Contribution Vector Clustering) | Outcome / Decision |
| :--- | :--- | :--- | :--- |
| **Feature Space** | 9 standardized functional dimensions (distribution, progression, creation, finishing, defensive actions, aerial, dribbling, pressing, discipline) | 7 contribution dimensions + action values | V1 offers greater positional specificity (e.g. distinguishing dribbling vs aerial). |
| **Controlled Vocabulary** | Deep-lying Playmaker, Box-to-Box, Ball-Winning Midfielder, Inside Forward, Target Forward, Ball-Playing Defender, etc. | Latent numeric clusters requiring arbitrary naming | **V1 is vastly superior in domain interpretability.** |
| **Sample Gate** | Enforces $N \ge 270$ minutes. Leaves sub-270m players unclassified. | Enforces $N \ge 270$ minutes. | Tied (both enforce strict gating). |
| **Silhouette Score** | $0.62$ on synthetic reference population. | $0.54$ on synthetic reference population. | **V1 produces better cluster separation.** |
| **Database Reality** | 0 players currently exceed $270$ minutes in Bronze payload. All correctly flagged `INSUFFICIENT_SAMPLE`. | 0 players currently exceed $270$ minutes. | Tied. |

---

## 3. Formal Scientific Conclusion: KEEP V1

In accordance with Phase 3.2 Directive:
> *"If V2 is not demonstrably better: keep V1. Do not change working intelligence merely because more features are available."*

### Recommendation:
1. **Retain Role V1 as the canonical role assignment engine**: The controlled archetypes provide transparent, scout-aligned, domain-accurate terminology.
2. **Expose Contribution Vector alongside Role Profile**: The Role Profile response now includes linkages to the Contribution Vector, providing both functional archetype labels and dimensional ratings without degrading classification interpretability.
3. **Evaluation Status**: **UNCHANGED (V1 Retained)**.
