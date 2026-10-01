# PHASE 15 — SCOUT COPILOT V5 SPECIFICATION
## Deterministic Research Assistance across 12 Governed Query Classes

---

### 1. Architectural Philosophy

Scout Copilot V5 (`apps/api/app/phase15/copilot_v5.py`) upgrades Copilot from outcome analysis to deterministic research assistance:
- **Zero Hallucination Guarantee**: Directly executes registered tools and queries versioned databases. No synthetic statistical metrics are invented.
- **Mandatory Causality Guardrail**: All textual responses pass through `CausalityGuardrail` to eliminate causal claims ("caused", "leads to victory") in favor of associative evidence.
- **Tool Allow-Listing**: Restricted strictly to registered research engines.

---

### 2. Supported Query Classes (12 Classes)

1. **`FIND_EVIDENCE_FOR_HYPOTHESIS`**: Retrieves independent validation records and sample parameters for a hypothesis.
2. **`COMPARE_PATTERN_ACROSS_LEAGUES`**: Compares candidate relationships across distinct competition environments.
3. **`SHOW_WHERE_PATTERN_FAILS`**: Identifies boundary conditions and weak subgroup failure points.
4. **`FIND_SIMILAR_PLAYER_TRAJECTORIES`**: Matches developmental slopes and breakout signatures.
5. **`EXPLAIN_TRANSFER_MARKET_RESIDUALS`**: Dissects pre-deal model projection vs realized fee gaps.
6. **`SHOW_MODEL_CALIBRATION_BY_COMPETITION`**: Surfaces ECE and calibration reliability curves by league.
7. **`FIND_DECISION_DIVERGENCE_PATTERNS`**: Identifies recurring recruitment divergence patterns.
8. **`COMPARE_TACTICAL_ROLE_TRANSITIONS`**: Evaluates empirical positional transitions under 450-min / 5-app gating.
9. **`IDENTIFY_INSUFFICIENT_EVIDENCE`**: Highlights cells with small sample sizes ($N < 15$) or out-of-distribution flags.
10. **`EXPLAIN_WHY_HYPOTHESIS_UNVALIDATED`**: Details holdout requirements and remaining empirical hurdles.
11. **`SHOW_RESEARCH_EVIDENCE_GRAPH`**: Traverses cryptographic node/edge lineage.
12. **`COMPARE_CHAMPION_VS_CHALLENGER`**: Summarizes offline/shadow performance across identical evaluation windows.
