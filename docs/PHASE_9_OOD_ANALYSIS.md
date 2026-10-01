# Phase 9: Out-of-Distribution (OOD) Stress-Testing & Uncertainty Framework

## Status: AUDITED & CERTIFIED
- **Evaluation Date**: 2026-09-26
- **Validation Version**: `phase9_ood_validation_v1`
- **Core Invariant**: OOD inputs must NEVER silently produce normal-confidence predictions
- **Scenarios Evaluated**: 10 comprehensive cross-domain stress tests across 5 categories

---

## 1. OOD Taxonomy & Label Semantics

The system enforces four distinct, mutually exclusive uncertainty classifications across all API surfaces:

| Label | Definition | UI / Decision Treatment | System Action |
|---|---|---|---|
| **`IN_DISTRIBUTION`** | Input feature vector falls within the verified parameter space of training data ($N \ge 30$, low distance) | Standard confidence display; quantitative forecasts enabled | Normal inference pipeline |
| **`LOW_CONFIDENCE`** | Input within distribution domain, but exhibiting high feature variance, small sample ($30 \le N < 100$), or tactical novelty | Display with warning indicator; widen confidence intervals by $\ge 50\%$ | Flagged with caveat rationale |
| **`INSUFFICIENT_DATA`** | Sample size below analytical floor ($N < 30$ matches or $< 270$ player minutes) | Quantitative point forecasts demoted; show qualitative guidance only | Block quantitative scoring |
| **`OUT_OF_DISTRIBUTION`** | Input from an unseen competition tier, unsupported league, uncalibrated tactical formation, or future temporal horizon | Prominent warning banner; suppress automated recommendations | Explicit OOD flag emitted |

---

## 2. OOD Stress-Testing Results Across Domains

| Scenario ID | Category | Target Engine | Tested Input / Regime | Expected Label | Actual Observed System Label | Result | Evidence & Behavior |
|---|---|---|---|---|---|---|---|
| `ood_comp_mls` | Competition | Match Prediction | Major League Soccer (USA) fixture | `OUT_OF_DISTRIBUTION` | `OUT_OF_DISTRIBUTION` | **PASSED** | Match model suppresses Poisson parameters and surfaces league unsupported alert |
| `ood_comp_j_league` | Competition | Valuation | J-League (Japan) domestic transfer | `OUT_OF_DISTRIBUTION` | `OUT_OF_DISTRIBUTION` | **PASSED** | Suppresses EUR regression point estimate; demotes to qualitative comparable search |
| `ood_comp_a_league` | Competition | Player Intelligence | A-League (Australia) player profile | `INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | **PASSED** | Zero percentile ranks computed against European peer baselines |
| `ood_club_unknown` | Club | Match Prediction | Semi-pro or amateur club with 0 historical fixtures | `INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | **PASSED** | Baseline Elo initialization aborted; surfaces `INSUFFICIENT_DATA` |
| `ood_club_promoted` | Club | Tactical Fit | Newly promoted club with minimal Tier 1 tactical tracking | `LOW_CONFIDENCE` | `LOW_CONFIDENCE` | **PASSED** | Tactical fit calculated with reduced weight and explicit confidence downgrade |
| `ood_player_youth` | Player | Player Intelligence | Academy graduate with 45 career first-team minutes | `INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | **PASSED** | Sample gate (< 270 min) blocks contribution vector generation |
| `ood_player_unseen` | Player | Similarity | Player with unmapped non-European league metrics | `INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` | **PASSED** | Cosine calculation halted; prevents false matches against elite European players |
| `ood_season_future` | Season | Valuation | Future season transfer horizon (Season 2028/29) | `OUT_OF_DISTRIBUTION` | `OUT_OF_DISTRIBUTION` | **PASSED** | Temporal gate rejects post-cutoff inflation forecasts |
| `ood_tactic_unusual` | Tactical | Tactical Fit | 3-1-4-2 formation with inverted center-backs | `LOW_CONFIDENCE` | `LOW_CONFIDENCE` | **PASSED** | Emits low-confidence fit score with warning about rare archetype interaction |
| `ood_risk_crosscont` | Market | Transfer Risk | Cross-continent move (Chinese Super League $\to$ La Liga) | `LOW_CONFIDENCE` | `LOW_CONFIDENCE` | **PASSED** | League translation risk set to maximum penalty with low confidence badge |

---

## 3. Implementation of the OOD Defense Invariant

### 3.1 Gating Implementation
All intelligence endpoints invoke domain-specific pre-flight validators prior to model inference:
1. `validate_competition_support(competition_id)`: Checks membership in the verified competition registry.
2. `check_sample_sufficiency(entity_id, min_minutes)`: Validates that observation volume exceeds the minimum analytical floor.
3. `enforce_temporal_horizon(target_date, cutoff_date)`: Blocks inference requests targeting uncalibrated future horizons.

### 3.2 Frontend and API Transparency
Per Phase 9 §20:
- When any endpoint encounters an OOD or insufficient data condition, the HTTP JSON response embeds:
  - `data_status`: One of the 4 standard labels
  - `confidence`: Explicit confidence assessment (`LOW`, `MEDIUM`, `HIGH`, `INSUFFICIENT_DATA`)
  - `data_sufficiency_reasons`: Structured array of human-readable rationale explanations explaining why confidence was lowered.
- The UI surfaces these limitations with high visibility, ensuring scout decision-makers are never misled by false certainty.
