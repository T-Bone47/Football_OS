# Market Comparable Methodology
**Football Intelligence OS — Phase 4.1K**  
**Date**: September 2026  
**Status**: APPROVED & ACTIVE  

---

## 1. Objectives & Principles

In professional football recruitment, player valuation without empirical transaction comps is purely speculative. Before deploying parametric or non-linear machine learning models (e.g. Gradient Boosted Trees), the system must establish **deterministic, transparent, and auditable comparable transaction retrieval**.

Core Tenets:
1. **Zero LLM Valuation**: Similarity scores and transaction retrieval are executed purely via deterministic linear and geometric formulations.
2. **Temporal Precedence**: When evaluating player valuation as of date $T$, any historical transfer executed after $T$ is strictly excluded ($t_{\text{transfer}} \le T$).
3. **No Arbitrary Heuristics**: Similarity weights are fixed, documented, and grounded in domain football economics.
4. **Position Gating**: Outfield players and Goalkeepers operate in fundamentally disjoint economic and tactical regimes. They are never paired as comparables.

---

## 2. Mathematical Similarity Formulation

For a target player profile $\mathbf{x}_{\text{target}}$ evaluated as of $T$, and each qualified candidate historical transfer transaction $j$ executed at $t_j \le T$, composite similarity $S_{\text{composite}}(j) \in [0.0, 1.0]$ is computed as:

$$S_{\text{composite}}(j) = w_{\text{role}} S_{\text{role}} + w_{\text{contrib}} S_{\text{contrib}} + w_{\text{age}} S_{\text{age}} + w_{\text{tier}} S_{\text{tier}} + w_{\text{recency}} S_{\text{recency}}$$

### Dimension Weights

| Dimension | Symbol | Weight | Rationale |
| :--- | :--- | :--- | :--- |
| **Tactical Role** | $S_{\text{role}}$ | **0.30** | A Box-to-Box midfielder trades at different market dynamics than a Pure Holding Anchor. |
| **Contribution / Performance** | $S_{\text{contrib}}$ | **0.25** | High-impact progressive/creative profiles command distinct economic tiers. |
| **Age at Transfer** | $S_{\text{age}}$ | **0.20** | Football market values exhibit strong non-linear age curves (peak value at 23–26). |
| **Competition Tier** | $S_{\text{tier}}$ | **0.15** | Purchasing and selling competition prestige impacts fee scale. |
| **Market Recency** | $S_{\text{recency}}$ | **0.10** | Accounting for transfer fee inflation over multiple seasons. |

---

## 3. Subcomponent Formulations

### 1. Age Proximity ($S_{\text{age}}$)
Let $\Delta\text{age} = |\text{age}_{\text{target}}(T) - \text{age}_{\text{cand}}(t_j)|$. The similarity decays exponentially:
$$S_{\text{age}} = \exp(-0.20 \cdot \Delta\text{age})$$
- $\Delta\text{age} = 0 \implies S_{\text{age}} = 1.00$
- $\Delta\text{age} = 2 \implies S_{\text{age}} = 0.67$
- $\Delta\text{age} = 5 \implies S_{\text{age}} = 0.37$

### 2. Role Alignment ($S_{\text{role}}$)
When role archetypes are classified:
- Identical primary role archetype (e.g. `BALL_WINNING_DEFENDER` to `BALL_WINNING_DEFENDER`): $S_{\text{role}} = 1.00$
- Same broad position group, different archetype: $S_{\text{role}} = 0.65$
- Default baseline when unprofiled: $0.75$

### 3. Contribution Vector Similarity ($S_{\text{contrib}}$)
Cosine similarity over normalized 7-dimensional contribution vectors:
$$S_{\text{contrib}} = \frac{\mathbf{v}_{\text{target}} \cdot \mathbf{v}_{\text{cand}}}{\|\mathbf{v}_{\text{target}}\| \|\mathbf{v}_{\text{cand}}\|}$$

### 4. Temporal Recency ($S_{\text{recency}}$)
Let $\Delta t$ be the difference in years between evaluation timestamp $T$ and transaction date $t_j$:
$$S_{\text{recency}} = \exp(-0.15 \cdot \Delta t)$$
Transfers within the last 2 years receive $S_{\text{recency}} \ge 0.74$; deals older than 6 years receive $S_{\text{recency}} \le 0.40$.

---

## 4. Candidate Qualification Filters

A candidate transfer is considered qualified for comparable ranking if and only if:
1. `is_permanent == True` (loans are excluded from permanent transfer comparables).
2. `fee_status in ('KNOWN_FEE', 'REPORTED_FEE')` (undisclosed or unknown transactions cannot anchor a valuation).
3. `player_id != target_player_id` (a player is not compared against their own identical deal).
4. `position_group == target_position_group` (strict position group gate).
