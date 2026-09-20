# Tactical Fit & System Suitability Engine (Phase 2 Slice 3)

## 1. Core Principle: System Compatibility vs. Isolated Skill

A player possessing elite individual statistics may nonetheless fail if introduced into an incompatible tactical setup (e.g., a pure defensive anchor tasked with deep playmaking, or an isolated target forward forced into a high-pressing, fluid front three).

The Football Intelligence OS Tactical Fit Engine evaluates the deterministic compatibility between:
1. A player's empirical functional tendencies (from leakage-safe `PlayerRoleProfile` and `FeatureSnapshot` data)
2. A target managerial tactical system, formation, nominal position, and role archetype requirement.

---

## 2. Multi-Component Fit Formulation

Tactical fit decomposes into 5 transparent, weighted analytical dimensions:

$$\text{Composite Fit} = \frac{w_{\text{pos}} \cdot F_{\text{pos}} + w_{\text{role}} \cdot F_{\text{role}} + w_{\text{dim}} \cdot F_{\text{dim}} + w_{\text{style}} \cdot F_{\text{style}} + w_{\text{context}} \cdot F_{\text{context}}}{w_{\text{total}}}$$

### Default Component Weights

| Component | Weight | Analytical Purpose |
| :--- | :--- | :--- |
| **Position Fit ($F_{\text{pos}}$)** | $0.20$ | Geometric and spatial compatibility between nominal position and tactical assignment. |
| **Role Fit ($F_{\text{role}}$)** | $0.25$ | Functional archetype alignment against target tactical role profile. |
| **Dimensional Fit ($F_{\text{dim}}$)** | $0.35$ | Precise requirement matching across 9 canonical dimensions with threshold deficit penalties. |
| **Style Fit ($F_{\text{style}}$)** | $0.10$ | Systemic philosophy compatibility (possession style, pressing intensity, build-up structure). |
| **Contextual Fit ($F_{\text{context}}$)** | $0.10$ | Sample maturity scaling to protect against overvaluing small samples. |

When optional components (`style_fit`, `contextual_fit`) are omitted, remaining weights are re-normalized automatically to preserve a strict `[0.0, 1.0]` composite scale.

---

## 3. Component Fit Formulations

### A. Position Fit ($F_{\text{pos}}$)
- **Exact Nominal Match**: $1.0$ (e.g., player is naturally `DM` and role requires `DM`).
- **Same Position Family**: $0.85$ (e.g., `CM` playing `DM`, both `MID`).
- **Adjacent Position Family**: $0.40$ (e.g., `MID` playing `ATT` or `DEF` playing `MID`).
- **Completely Divergent**: $0.05$ (e.g., `GK` playing outfield).
- **Missing / Unknown**: $0.0$.

### B. Role Fit ($F_{\text{role}}$)
- **Primary Archetype Match**: $1.0$ (player's data-discovered primary archetype matches the target role).
- **Secondary Archetype Match**: $0.80$ (player's secondary archetype matches the target role).
- **Functional Projection**: When neither matches directly, the player's 9-dimension profile is projected onto the target archetype's dimensional weights vector:
  $$\text{Projection} = \frac{\sum_{d} w_{\text{arch}, d} \cdot s_{p, d}}{\sum_{d} |w_{\text{arch}, d}|}$$
  Normalized to $[0.0, 1.0]$.

### C. Dimensional Fit ($F_{\text{dim}}$) & Threshold Deficit Penalty
Each tactical context defines specific requirements across the 9 canonical dimensions with required strengths $r_d$, importance weights $w_d$, and critical minimum thresholds $T_{\min, d}$.

1. **Base Compatibility**:
   $$\text{BaseFit}_d = \max(0.0, 1.0 - |s_{p, d} - r_d|)$$

2. **Critical Threshold Deficit Penalty**:
   If a player falls below a non-negotiable minimum threshold ($s_{p, d} < T_{\min, d}$), a proportional penalty is applied:
   $$\text{Deficit}_d = T_{\min, d} - s_{p, d}$$
   $$\text{Penalty}_d = \frac{\text{Deficit}_d}{T_{\min, d}} \times 0.50$$
   $$\text{FinalFit}_d = \max(0.0, \text{BaseFit}_d - \text{Penalty}_d)$$

3. **Weighted Aggregation**:
   $$F_{\text{dim}} = \frac{\sum_{d} w_d \cdot \text{FinalFit}_d}{\sum_{d} w_d}$$

### D. Style Fit ($F_{\text{style}}$)
Evaluates high-level systemic alignment:
- **Possession Style**: `HIGH_POSSESSION` (distribution + carrying), `DIRECT` / `COUNTER_ATTACK` (progression + finishing).
- **Pressing Style**: `HIGH_PRESS` (defending + duels), `LOW_BLOCK` / `MID_BLOCK` (defending + discipline).
- **Build-Up Style**: `SHORT_PASSING` (distribution).

### E. Contextual Exposure Fit ($F_{\text{context}}$)
Protects against sample volatility:
$$\text{Contextual Fit} = \min\left(1.0, \frac{\text{sample\_minutes}}{900}\right)$$

---

## 4. Evidence-Based Confidence & Sample-Size Gate

Scouting software that recommends high tactical fit for players with 45 minutes of game time is hazardous. The system enforces strict confidence and status gating:

| Sample Exposure | Role Status | Calculated Fit | Assigned Confidence | Assigned Fit Status |
| :--- | :--- | :--- | :--- | :--- |
| $< 450$ minutes | Any | Any | `INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` |
| Any | `INSUFFICIENT_SAMPLE` | Any | `INSUFFICIENT_DATA` | `INSUFFICIENT_DATA` |
| $450 - 899$ minutes | `QUALIFIED` | $\ge 0.75$ | `MEDIUM` | `FIT` |
| $450 - 899$ minutes | `QUALIFIED` | $0.55 - 0.74$ | `MEDIUM` | `MODERATE_FIT` |
| $450 - 899$ minutes | `QUALIFIED` | $< 0.55$ | `MEDIUM` | `POOR_FIT` |
| $\ge 900$ mins & $\ge 10$ matches | `QUALIFIED` | $\ge 0.75$ | `HIGH` | `FIT` |
| $\ge 900$ mins & $\ge 10$ matches | `QUALIFIED` | $0.55 - 0.74$ | `HIGH` | `MODERATE_FIT` |
| $\ge 900$ mins & $\ge 10$ matches | `QUALIFIED` | $< 0.55$ | `HIGH` | `POOR_FIT` |

---

## 5. Pre-Configured Contexts Catalog & Dynamic Contexts

### Standard Pre-Configured Contexts (`STANDARD_TACTICAL_CONTEXTS`)
- **4-3-3**:
  - `433_dm_deep_distributor`: Deep tempo controller with distribution, progression, and defensive positioning.
  - `433_dm_ball_winner`: Aggressive pressing anchor prioritizing tackles, interceptions, and duel volume.
  - `433_cm_box_to_box`: High-intensity dual-box presence demanding stamina, duels, progression, and defending.
  - `433_w_inverted_winger`: Inside-cutting creator/finisher with progression, carrying, and goal threat.
  - `433_gk_sweeper_keeper`: High-line distributor and aggressive box claimer.
- **4-2-3-1**:
  - `4231_pivot_passer`: Double pivot deep playmaker controlling transitions.
  - `4231_pivot_destroyer`: Defensive shield breaking counter-attacks.
  - `4231_am_creator`: Classic #10 creative hub operating between lines.
  - `4231_st_pressing_forward`: High-pressing frontline leader pressing center-backs and finishing.
  - `4231_fb_overlapping`: Attacking full-back providing width and progressive crosses.
- **3-5-2 / 3-4-3**:
  - `352_cb_ball_player`: Wide center-back driving into midfield and initiating progression.

### Dynamic Custom Contexts
Custom contexts can be constructed on the fly using `build_custom_context(formation, target_position, target_role, possession_style, pressing_style)`, which automatically populates standard requirement weights from the controlled archetype vocabulary.

---

## 6. Traceable Explainability Engine ("Why Fit" / "Why Not Fit")

The explainability engine parses the exact numerical results and outputs transparent, human-readable scouting rationales:

### "Why Fit" Factors
1. **Positional Alignment**: Confirms nominal and spatial suitability.
2. **Role Archetype Match**: Notes alignment with target functional archetype.
3. **Dimensional Strengths**: Highlights specific dimensions meeting or exceeding requirements with numerical evidence.
4. **Style Alignment**: Identifies compatibility with systemic team pressing or possession tactics.

### "Why Not Fit" Factors
1. **Sample Warnings**: Highlights insufficient exposure where sample minutes $< 450$.
2. **Positional / Role Mismatches**: Clear warning when players operate outside target geometry.
3. **Critical Threshold Deficits**: Explicitly calls out deficits against minimum required thresholds.
4. **Dimensional Divergence**: Explains specific tactical shortfalls with exact point deltas.

---

## 7. PostgreSQL Persistence & Versioning

Stored in canonical `player_tactical_fits`:
- **Unique Constraint**: `(player_id, tactical_context_id, feature_set_version, calculation_version, as_of)`
- **Idempotency**: Repeated calculations for the same player, context, and cutoff update existing rows without duplicating primary keys.
- **JSONB Structures**: Full `dimension_breakdown`, `why_fit`, `why_not_fit`, and `provenance`.
- **Indexes**: `player_id`, `as_of`, `tactical_context_id`, `target_role`, `fit_status`.

---

## 8. Canonical REST API Surface

| Endpoint | Method | Response Model | Description |
| :--- | :--- | :--- | :--- |
| `/api/v1/tactical/contexts` | `GET` | `list[TacticalContextResponse]` | Lists all standard pre-configured tactical contexts and requirement weights. |
| `/api/v1/players/{id}/tactical-fit` | `GET` | `PlayerTacticalFitResponse` | Calculates tactical fit against a specified context ID or custom formation/role. |
| `/api/v1/players/{id}/tactical-fit/{context_id}` | `GET` | `PlayerTacticalFitResponse` | Shortcut evaluation against a pre-configured context ID. |
| `/api/v1/tactical-fit/compare` | `POST` | `TacticalFitComparisonResponse` | Head-to-head tactical comparison of two players within the same tactical system. |

---

## 9. Temporal Leakage & Time-Travel Invariance

As verified in `test_tactical_leakage.py`:
- Calculating tactical fit as of $T_0$ depends strictly on `FeatureSnapshot` and `PlayerRoleProfile` records with `as_of <= T_0`.
- Subsequent insertion of matches, performances, or feature snapshots at $T_1 > T_0$ produces **100% bit-for-bit identical** tactical fit scores, confidence classifications, and explanations for $T_0$.
