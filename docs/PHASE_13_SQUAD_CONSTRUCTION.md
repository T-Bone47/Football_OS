# PHASE 13 — SQUAD CONSTRUCTION & PARETO FRONTIER
## Constrained Optimization, Budget Allocation, Squad Depth & Academy Pathways

### 1. Architectural Mission
The Phase 13 Squad Construction Engine frames roster assembly as a multi-objective, constrained optimization problem. Instead of collapsing competing sporting, financial, and age objectives into an arbitrary single score, the engine computes and exposes the **Pareto Decision Frontier**.

---

### 2. Optimization Formulation (§5)
**Inputs**:
- Tactical formation requirement (e.g., `4-3-3` with Inverted Fullbacks and Lone Pivot).
- Hard fiscal constraints: Total transfer budget ceiling (EUR) and weekly wage headroom (EUR/week).
- Squad registration constraints: Maximum squad size (25), minimum homegrown quota (8), non-EU limits.
- Roster policies: Maximum average age (e.g., $\le 26.0$ years) and minimum played minutes filter ($\ge 450$ minutes).

**Mathematical Execution Order**:
1. **Hard Constraints First**: Eliminate all candidates or permutations that violate statutory budget, wage ceiling, or squad registration rules.
2. **Multi-Objective Optimization**: Simultaneously evaluate non-dominated alternatives across:
   - Tactical System Coverage ($T$)
   - Squad Depth & Redundancy ($D$)
   - Action Value Contribution ($C$)
   - Net Capital Outlay ($F$)
   - Longevity & Age Curve ($A$)
   - Operational Risk Profile ($R$)
3. **Pareto Frontier Extraction**: Retain only non-dominated solutions where no single dimension can be improved without degrading another.

---

### 3. Canonical Pareto Strategies (§14)
When evaluating recruitments (e.g., Left-Sided Centre-Back), the engine presents transparent trade-off alternatives:

| Strategy | Profile | Net Spend | Tactical Fit | Depth Rating | Average Age | Risk | Strategic Trade-Off Summary |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|
| **Strategy A** | **Elite Quality** | €38.0M | 91.4 | 88.0 | 23.8y | LOW | Maximizes immediate progression volume (+4.2 pts) with young prime profile; moderate financial outlay. |
| **Strategy B** | **Balanced Depth** | €42.0M | 86.2 | 92.5 | 23.5y | LOW | Delivers domestic league physical adaptation and homegrown status, but slightly lower line-breaking passing. |
| **Strategy C** | **Academy Succession** | €0.0M | 83.0 | 78.5 | 23.2y | MODERATE | Preserves 100% of transfer budget; elevates youth pathway, but increases depth fragility during fixture congestion. |

---

### 4. Squad Depth Simulation (§11, §12)
The simulator evaluates squad resilience across 4 depth states:
- **`SOLID`**: Primary starter backed by senior specialist with $< 15\%$ contribution drop-off.
- **`ADEQUATE`**: Capable rotational cover; starter minutes share manageable ($< 75\%$).
- **`THIN`**: Starter minutes overload ($> 85\%$); injury to starter forces tactical compromise.
- **`CRITICAL_GAP`**: Complete absence of senior cover; unverified youth or out-of-position player required.

**Fixture Congestion Scenarios**:
1. **Domestic League Only**: 38 matches, ~37,620 team minutes. Rotational demands manageable.
2. **Domestic + European Knockout**: 54+ matches, ~53,460 team minutes. High vulnerability in thin positions (e.g., Right Wing).
3. **Severe Cup & League Congestion**: 3 matches per week over 6 consecutive weeks. Tests second-string starter capability.

---

### 5. Academy Integration Pathways (§17)
Academy prospects are evaluated with empirical criteria without relying solely on age:
- **`NOT_READY`**: $< 600$ academy minutes, developmental gaps in physical/tactical metrics.
- **`DEVELOPMENTAL`**: $\ge 600$ academy minutes, showing technical alignment in domestic U21 fixtures.
- **`ROTATION_READY`**: $\ge 1,200$ academy minutes with tactical fit $\ge 80.0$, or $\ge 90$ senior first-team minutes.
- **`SQUAD_READY`**: $\ge 450$ senior first-team minutes, capable of stepping into domestic cup and league rotation.
