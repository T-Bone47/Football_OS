# Contextual Performance Methodology (Phase 3.2C)

## 1. Overview and Purpose

Raw per-90 statistics fail to capture the reality of professional football when viewed in isolation. A winger generating 2.0 key passes per 90 in the English Premier League or UEFA Champions League faces an entirely different defensive structure and quality threshold than a winger generating 2.0 key passes in a secondary domestic tier. Similarly, a regular starter playing 85 minutes per match encounters fatigue and sustained tactical pressure that a substitute playing 15 minutes against tired defenders does not.

The purpose of the **Contextual Performance Engine** is **not** to manipulate or artificially inflate statistical scores. The purpose is to provide transparent, defensible, documented mathematical adjustments that make cross-player and cross-competition comparisons reliable.

---

## 2. Available and Supported Dimensions

In strict adherence to Principle 1 (Zero Fabrication) and Principle 2 (Existing Data is Source of Truth), contextual adjustments are computed **strictly from data physically present in the canonical database**:

1. **Competition Strength**: Grounded in verified competition identities (`Competition.name`, `Competition.country`).
2. **Starter Ratio**: Derived directly from `PlayerMatchStats.is_starter` ($\text{starters} / N$).
3. **Substitute Ratio**: Derived from `PlayerMatchStats.is_substitute` ($\text{substitutes} / N$).
4. **Minutes Exposure**: Derived from `PlayerMatchStats.minutes` ($\sum \text{minutes} / (N \times 90)$).
5. **Minutes per Match**: Observed average duration per appearance.

### Unsupported Dimensions (Kept Explicitly Gated)
- **Possession Share**: Team possession percentages are not recorded in individual `PlayerMatchStats` payloads for all matches. No possession normalization is applied until full match team statistics coverage is verified across 100% of fixtures.
- **Opponent Strength Differential**: Match-level opponent Elo is not synthesized or fabricated.
- **Game-State Splits**: Score-line-at-event-time is not supplied in basic event feeds.

---

## 3. Mathematical Methodology

### 3.1 Competition Tier Coefficient ($C_{\text{comp}}$)

Competitions are mapped to transparent tier weights reflecting empirical league difficulty:

| Competition | Tier Coefficient |
| :--- | :--- |
| UEFA Champions League | $1.05$ |
| Premier League, La Liga, Serie A, Bundesliga, Ligue 1 | $1.00$ |
| UEFA Europa League | $0.90$ |
| Championship, Eredivisie, Primeira Liga, Brasileirão | $0.85$ |
| Serie B, Segunda División, 2. Bundesliga, Ligue 2 | $0.80$ |
| Unlisted / Regional Competitions | $0.75$ (Default baseline) |

### 3.2 Starter Adjustment ($S_{\text{starter}}$)

Regular starters face full opponent defensive structures and sustained workload. A slight adjustment reflects starter dominance:

$$S_{\text{starter}} = 0.05 \times (\text{starter\_ratio} - 0.50)$$

- $\text{starter\_ratio} = 1.0 \implies +0.025$ boost.
- $\text{starter\_ratio} = 0.0 \implies -0.025$ penalty.

### 3.3 Composite Context Multiplier ($M_{\text{context}}$)

The final composite contextual multiplier is clamped to $[0.70, 1.10]$:

$$M_{\text{context}} = \text{clamp}(C_{\text{comp}} + S_{\text{starter}}, 0.70, 1.10)$$

---

## 4. Sample-Size Gating

Context adjustments cannot be computed from a vacuum. If observed matches $N = 0$:
- `competition_tier` $= 0.75$
- `exposure_share` $= 0.0$
- `context_multiplier` $= 0.75$
- `context_summary` $=$ `"No match appearances recorded."`

If $N \ge 1$ but cumulative minutes $< 270$:
- Context is flagged with `status: INSUFFICIENT_SAMPLE`.
