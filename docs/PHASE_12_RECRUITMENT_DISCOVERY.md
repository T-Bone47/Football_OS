# Phase 12 — Advanced Recruitment Discovery & Market Inefficiencies

## 1. Advanced Multi-Mode Candidate Discovery (§13, §15)

Candidate discovery extends beyond simple keyword matching to seven governed analytical modes:

| Discovery Mode | Selection Basis | Core Analytical Filter |
|:---|:---|:---|
| **`ROLE_SIMILAR`** | Dimensional Role Alignment | Cosine similarity $\ge 0.85$ against target role vector |
| **`CONTRIBUTION_SIMILAR`** | Action Value Equivalence | Overall action value within $\pm 5$ percentile points |
| **`TACTICAL_SIMILAR`** | Club Tactical System Fit | Pressing, tempo, and defensive line compatibility $\ge 82.0$ |
| **`MARKET_VALUE_GAP`** | Valuation Discrepancy | Modelled valuation $\ge 15\%$ above observed asking reference |
| **`EMERGING`** | Developmental Breakout | U23 player with development velocity $\ge 3.0$ and sample $\ge 450$ mins |
| **`REPLACEMENT`** | Direct Departure Backfill | Top-$K$ match against departing player's dimensional profile |
| **`SCENARIO_CONSTRAINED`** | Multi-Constraint Optimization | Satisfies fee budget, wage limit, and squad registration caps |

### Safety Invariants
1. **Hard Position Gating**: CB candidates are strictly gated to CB reference pools; cross-position comparison is prohibited.
2. **Minutes Gate**: Minimum $450$ competitive minutes required before a candidate enters active shortlists.
3. **Cross-Competition Asymmetry**: Non-EPL candidates retain explicit confidence tagging (`MODERATE` or `LOW_CONFIDENCE`) to prevent visual conflation with fully calibrated domestic players.

---

## 2. Versioned Benchmark Player Profiles (§14)

Scouts define versioned, immutable target profiles via `BenchmarkProfileRegistry` (`app/phase12/benchmarks.py`):

### Example: "2026/27 Elite Ball Playing CB" (v1.0.0)
- **Target Role**: Ball Playing Defender (4-3-3 System)
- **Dimension Weights**:
  - Progression: $25\%$
  - Passing: $20\%$
  - Defending: $20\%$
  - Carrying: $15\%$
  - Aerial: $10\%$
  - Retention: $10\%$
- **Archetype References**: William Saliba, John Stones, Gonçalo Inácio
- **Immutability Guarantee**: Once published, the benchmark profile cannot be modified; adjustments generate an immutable new version (`v1.1.0`).

---

## 3. Market Inefficiency & Value Gap Engine (§12)

The `MarketInefficiencyEngine` (`app/phase12/market_inefficiency.py`) detects valuation gaps:
- **Observed Market Reference**: Realized release clause or reported asking fee.
- **Modelled Valuation**: `GBR_ValuationEngine_v1.0` point estimate with $80\%$ conservative lower prediction bound.
- **Comparable Range**: Peer transfer realization band in same age and performance quintile.

### Example: Gonçalo Inácio (Sporting CP)
- Observed Release Clause: $€35.0\text{M}$
- Modelled Valuation Point Estimate: $€44.5\text{M}$
- Conservative Lower Bound ($80\%$ CI): $€40.0\text{M}$
- Comparable Peer Band: $€42.0\text{M} - €48.0\text{M}$
- Value Gap: $+€9.5\text{M}$ ($+27.1\%$ relative to release clause)
- Status: `HIGH_DATA_CONFIDENCE_VALUE_GAP` (Observed reference sits below the conservative lower bound).
