# Player Contribution Intelligence — Architecture & Specification

## 1. Executive Summary & Core Objective

Football Intelligence OS has transitioned from raw, uncontextualized player counting statistics to an **evidence-based player contribution intelligence layer**.

This layer systematically addresses:
- **WHAT** actions the player performs across match sequences.
- **HOW** the player contributes relative to position-specific expectations.
- **WHERE** the player impacts matches (while strictly preserving null coordinates when tracking data is unavailable).
- **HOW VALUABLE** those actions are under transparent empirical weighting.
- **IN WHAT CONTEXT** those contributions occur (competition, position group, sample minutes).
- **HOW CONFIDENT** the analytical engine is in its findings.

---

## 2. Non-Negotiable Scientific Principles

1. **Zero Fabrication**:
   - Never fabricate event coordinates $(x, y)$, expected values ($xG, xA, xT$), or synthetic contribution scores to populate UI components.
2. **Data Sufficiency as a Hard Gate**:
   - $Minutes < 270$: explicit `INSUFFICIENT_SAMPLE` state. Dimension scores and percentiles remain `None`.
   - $Minutes == 0$: explicit `INSUFFICIENT_DATA` state.
   - Spatial models with $< 80\%$ coordinate coverage return `INSUFFICIENT_DATA` with explicit data licensing requirements.
3. **Strict Temporal Safety**:
   - Calculations enforce $Match.date < as\_of$. Historical assessments never leak future match events.
4. **Preservation of Semantic Nulls**:
   - `0.0`: Observed zero (e.g. 0 tackles made in 90 minutes).
   - `None / NULL`: Unknown or unrecorded attribute (e.g. spatial coordinates in API-Football feed).
   - `INSUFFICIENT_DATA`: Missing foundational records.
   - `INSUFFICIENT_SAMPLE`: Evaluated evidence falls below statistical significance threshold.
5. **Position-Aware Normalization**:
   - Evaluations use distinct benchmark matrices for Goalkeepers (`GK`), Defenders (`DEF`), Midfielders (`MID`), and Attackers (`ATT`).
6. **Deterministic Explainability**:
   - Every strength and growth area is computed directly from relative rate thresholds against benchmarks. No LLMs calculate or invent numerical scores.

---

## 3. Data Availability Matrix (API-Football v3 Bronze vs Spatial Tracking)

| Action Category | Canonical Field | Available in Bronze? | Provider Source | Spatial $(x, y)$ | Outcome Field | Sufficient for Spatial Threat? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PASS** | `passes_total`, `passes_key`, `pass_accuracy` | **Yes** | PlayerMatchStats | **No (NULL)** | Partial (Accuracy %) | **No (Gated)** |
| **CARRY** | `dribbles_attempts`, `dribbles_success` | **Yes** | PlayerMatchStats | **No (NULL)** | Yes (Success/Fail) | **No (Gated)** |
| **SHOT** | `shots_total`, `shots_on_target`, `goals` | **Yes** | PlayerMatchStats / MatchEvent | **No (NULL)** | Yes (Goal/Target/Miss) | **No (Gated)** |
| **TACKLE** | `tackles_total`, `blocks`, `interceptions` | **Yes** | PlayerMatchStats | **No (NULL)** | Count | **No (Gated)** |
| **DUEL** | `duels_total`, `duels_won` | **Yes** | PlayerMatchStats | **No (NULL)** | Yes (Won/Lost) | **No (Gated)** |
| **DRIBBLE** | `dribbles_attempts`, `dribbles_success` | **Yes** | PlayerMatchStats | **No (NULL)** | Yes (Success/Fail) | **No (Gated)** |
| **SAVE** | `saves`, `goals_conceded` | **Yes** | PlayerMatchStats | **No (NULL)** | Count | **No (Gated)** |
| **FOUL** | `fouls_committed`, `fouls_drawn` | **Yes** | PlayerMatchStats | **No (NULL)** | Count | **No (Gated)** |
| **PRESSURE**| `pressures` | **No** | Not provided | **No** | N/A | **No (Excluded)** |
| **RECEIPT** | `ball_receipts` | **No** | Not provided | **No** | N/A | **No (Excluded)** |

*Conclusion*: While event counts and performance metrics are rich and reliable, spatial tracking coordinates are absent from standard API-Football Bronze payloads. Thus, spatial $xT$ is truthfully held at the hard gate (`INSUFFICIENT_DATA`) rather than manufactured.

---

## 4. Controlled Action Taxonomy

Defined in `app.actions.taxonomy`:
- `ActionType`:
  - `POSSESSION` (carry, dribble, reception)
  - `PASSING` (pass, key pass, assist)
  - `CREATION` (chance creation, shot assist)
  - `SHOOTING` (shot, goal, penalty goal)
  - `DEFENDING` (tackle, interception, block, clearance)
  - `DUELS` (ground duel, aerial duel)
  - `FOULS` (committed, drawn, yellow card, red card)
  - `GOALKEEPING` (save, penalty saved, goal conceded)
- `ActionOutcome`:
  - `SUCCESS`
  - `UNSUCCESSFUL`
  - `NEUTRAL`
  - `UNKNOWN`

---

## 5. Rate & Context Normalization

- **Per-90 Normalization**:
  $$\text{metric\_p90} = \frac{\text{raw\_total} \times 90.0}{\text{total\_minutes}}$$
  *Strict guard*: If $\text{total\_minutes} == 0$, $\text{metric\_p90} = \text{None}$.
- **Confidence Tiers**:
  - $\ge 900$ minutes: `HIGH` confidence.
  - $600 - 899$ minutes: `MEDIUM` confidence.
  - $270 - 599$ minutes: `LOW` confidence.
  - $< 270$ minutes: `INSUFFICIENT_SAMPLE` hard gate.
  - $0$ minutes: `INSUFFICIENT_DATA` hard gate.

---

## 6. Multi-Dimensional Position Benchmarks

Benchmark rates per 90 (derived from empirical tier-1 league distributions):
- **Goalkeepers (`GK`)**: Saves/90 ($3.0$), Clean sheet rate ($30\%$), Passes/90 ($25.0$), Pass Acc ($65\%$).
- **Defenders (`DEF`)**: Tackles/90 ($2.0$), Interceptions/90 ($1.5$), Blocks/90 ($0.8$), Duels won/90 ($3.5$), Pass Acc ($82\%$).
- **Midfielders (`MID`)**: Passes/90 ($50.0$), Pass Acc ($84\%$), Key passes/90 ($1.2$), Tackles/90 ($1.8$), Interceptions/90 ($1.2$).
- **Attackers (`ATT`)**: Shots/90 ($2.5$), Shots on Target/90 ($1.1$), Goals/90 ($0.35$), Key passes/90 ($1.4$), Dribbles/90 ($1.8$).

---

## 7. Database Persistence & Alembic Migration

- Migration: `0010_player_contributions_and_actions.py`
- Schema Tables:
  1. `canonical_actions`:
     - Holds granular, normalized action events with complete player, club, match, and snapshot foreign keys.
     - Indexes: `(match_id, player_id, minute, action_type, action_subtype, outcome)`.
  2. `player_contribution_snapshots`:
     - Point-in-time contribution state for players.
     - Enforces `UniqueConstraint("player_id", "as_of", "calculation_version")`.
