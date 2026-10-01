# PHASE 13 — TACTICAL SIMULATION & ROLE DEPENDENCIES
## Formation Compatibility, Diagnostic State Machines & Non-Causal Structural Models

### 1. Architectural Mission
The Phase 13 Tactical Simulation Engine evaluates how a club's active roster maps onto primary and alternative tactical structures. It diagnoses tactical gaps, positional overloads, and role undercoverages while modeling inter-role structural interactions without making unsubstantiated causal claims.

---

### 2. Supported Formations (§8)
The tactical simulator supports 8 canonical tactical formations:
1. `4-3-3` (Standard high-line positional possession)
2. `4-2-3-1` (Double pivot with advanced central playmaker)
3. `3-5-2` (Three central defenders with attacking wingbacks and dual strike partnership)
4. `3-4-3` (Three central defenders with fluid wide attacking triumvirate)
5. `4-4-2` (Two banks of four, compact mid-block)
6. `5-3-2` (Five-player defensive line with counter-attacking transitions)
7. `4-1-4-1` (Single holding pivot with flat midfield line)
8. `3-4-2-1` (Arteta/Alonso modern structure with dual interior 10s)

Formations outside this calibrated registry (e.g. `2-3-5`, `4-2-4`) trigger `FORMATION_UNSUPPORTED` and reject silent extrapolation.

---

### 3. Tactical Diagnostics State Machine (§8)
For every evaluated formation, the system computes:
- **`overall_compatibility_score`**: 0.0 to 100.0 scale reflecting positional coverage, role proficiency, and systemic progression.
- **`positional_coverage_pct`**: Percentage of mandatory tactical zones covered by natural starters.
- **`role_fit_average`**: Squad-level average role fit against target tactical instructions.
- **`build_up_progression_score`**: Estimated first-phase passing progression capacity.
- **`pressing_intensity_ppda`**: Passes allowed per defensive action under high press vs mid-block.
- **`transition_vulnerability_score`**: Rest-defense exposure index on turnovers.

Diagnostics States:
- **`OPTIMAL`**: Complete positional coverage, balanced role distribution, low transition vulnerability.
- **`TACTICAL_GAP`**: Absence of natural starters in critical roles (e.g., fewer than 3 central defenders available for 3-at-the-back).
- **`ROLE_OVERLOAD`**: Excessive roster congestion in identical role profiles (e.g., 6 central defenders on first-team wages).
- **`ROLE_UNDERCOVERAGE`**: Secondary depth absent behind an irreplaceable starter (e.g., lone pivot without natural backup).
- **`POSITIONAL_REDUNDANCY`**: Surplus personnel occupying conflicting spatial zones.
- **`FORMATION_UNSUPPORTED`**: Formation uncalibrated within the model parameter universe.

---

### 4. Role Dependency Graph (§9)
Structural relationships between roles are represented as directed graphs tagged with `MODELLED_DEPENDENCY`:

```
Ball Playing Centre Back
       ↓ (MODELLED_DEPENDENCY: BUILD_UP_PROGRESSION)
Inverted Fullback / Interior Playmaker
       ↓ (MODELLED_DEPENDENCY: MIDFIELD_RECEIVING_STRUCTURE)
Central Overload & Flank Release
```

```
Holding Midfielder (Lone Pivot)
       ↓ (MODELLED_DEPENDENCY: TRANSITION_PROTECTION)
Attacking Fullback High Overlap
       ↓ (MODELLED_DEPENDENCY: COUNTERPRESS_STRUCTURE)
Immediate Counterpress Regain
```

**Non-Causal Epistemic Policy**:
- Inter-role relationships represent spatial, systemic, and structural dependencies.
- The system never uses causal phrasing such as *"Signing a holding midfielder causes fullbacks to assist more goals."*
- It reports: *"Holding midfielder transition protection enables high fullback positioning within the simulated rest-defense structure."*
