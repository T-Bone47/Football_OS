# PHASE 15 — PATTERN DISCOVERY & EMPIRICAL CANDIDATE MINING
## Automated Cross-Contextual Scanning Across 10 Pattern Families

---

### 1. The 10 Pattern Families

The Pattern Discovery Engine (`apps/api/app/phase15/pattern_discovery.py`) scans observational data to emit `PatternCandidate` objects across 10 families:

1. **`PLAYER_TRAJECTORY`**: Accelerating or decelerating seasonal slopes in volume or efficiency metrics.
2. **`ROLE_TRANSITION`**: Recurring shifts across positional archetypes (e.g., Inverted Fullback, Wide Centre-Back).
3. **`TACTICAL_STRUCTURE`**: Symmetric vs asymmetric formations, pressing lines, and width dimensions.
4. **`SQUAD_CONSTRUCTION`**: Squad age distributions, positional depth stress points, and home-grown quotas.
5. **`TRANSFER_MARKET`**: Realized fee residuals compared to pre-transfer model projections.
6. **`PLAYER_DEVELOPMENT`**: Post-academy breakout patterns under varying minutes allocations.
7. **`MATCH_CONTEXT`**: Performance variation under schedule compression, travel density, and rest differentials.
8. **`COMPETITION_STYLE`**: Cross-league differences in physical pace, defensive block depth, and foul cadence.
9. **`DECISION_OUTCOME`**: Recruitment decision divergence patterns under high uncertainty.
10. **`MODEL_ERROR`**: Systematic regional, position-specific, or calibration residual patterns.

---

### 2. Candidate Invariant Rules

Every emitted pattern must include:
- **Sample Size ($N$)**: Explicitly reported; if $N < 10$, flagged as `LOW_SAMPLE` or `INSUFFICIENT_DATA`.
- **Temporal Scope**: Start and end observation windows.
- **Competition Scope**: Explicit league list; no silent cross-league pooling.
- **Effect Estimate & Uncertainty**: Directional magnitude with explicit confidence intervals or uncertainty description.
- **Subgroup Breakdown**: Disaggregated slices (e.g. top-tier vs mid-tier clubs).
- **Confounder Warnings**: Uncontrolled variables explicitly noted.
- **Non-Causal Formulation**: Standard associative phrasing generated via `CausalityGuardrail`.
