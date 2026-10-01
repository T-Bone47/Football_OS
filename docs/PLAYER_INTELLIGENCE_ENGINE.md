# Player Intelligence Engine (Phase 3.2)

## 1. Executive Summary

The **Player Intelligence Engine** constitutes the core analytical substrate of Football Intelligence OS. It synthesizes canonical event and match data, empirical action values, position-aware peer benchmarks, and contextual adjustments into a versioned, point-in-time **Player Intelligence Snapshot** and multi-layer **Player Intelligence Vector**.

In accordance with Core Architectural Principles, this engine enforces:
- **Zero Fabrication**: No coordinates, xG, xA, xT, transfer values, or percentiles are hallucinated or synthetically generated.
- **Strict Data Sufficiency Gating**: Minimum $270$ competitive minutes are required to evaluate per-90 rate metrics and peer percentiles. Spatial threat ($xT$) remains gated at `INSUFFICIENT_DATA` until continuous tracking coordinates are licensed.
- **Temporal Invariance**: All queries strictly enforce $\text{Match.date} < \text{as\_of}$. Historical snapshots are bit-for-bit immutable regardless of future matches.
- **Semantic Null Safety**: $0.0$ (observed zero) is strictly distinguished from `NULL` (unobserved) and `INSUFFICIENT_SAMPLE`.

---

## 2. Architectural Data Flow

```
Canonical Bronze (DataSnapshot)
           ↓
Canonical Match & Lineup Normalization (Silver)
           ↓
Canonical Events & Statistics (PlayerMatchStats)
           ↓
Canonical Action Taxonomy (CanonicalAction)
           ↓
Leakage-Safe Feature Engineering (FeatureSnapshot)
           ↓
Phase 3.1 Player Contribution & Empirical Action Value
           ↓
Phase 3.2 Player Intelligence Engine
 ├── Contextual Engine (Competition tier, starter ratio, exposure share)
 ├── Peer Benchmarking Engine (Position groups GK/DEF/MID/ATT, Z-scores, normal percentiles)
 ├── Longitudinal Trajectory Compiler (Chronological match-by-match timelines)
 ├── Deterministic Explanation Generator (why_strong, why_different, why_low_confidence)
 └── Player Intelligence Snapshot (PostgreSQL Table: player_intelligence_snapshots)
           ↓
Downstream Consumer Layers:
 [Role Discovery V2] [Similarity V2] [Tactical Fit V2] [Scout Copilot] [Transfer Valuation]
```

---

## 3. Database Schema: `player_intelligence_snapshots`

Defined in `apps/api/app/db/models/canonical.py` and applied via Alembic Migration `0011_player_intelligence_engine.py`:

| Column | Type | Constraints / Description |
| :--- | :--- | :--- |
| `id` | `UUID` | Primary Key, default UUIDv4 |
| `player_id` | `UUID` | FK -> `players.id` (ON DELETE CASCADE), Indexed |
| `club_id` | `UUID` | Nullable FK -> `clubs.id` |
| `competition_id` | `UUID` | Nullable FK -> `competitions.id` |
| `season_id` | `UUID` | Nullable FK -> `seasons.id` |
| `as_of` | `TIMESTAMPTZ` | Point-in-time calculation horizon |
| `calculation_version` | `VARCHAR(32)` | Current version: `"1.0"` |
| `data_status` | `VARCHAR(32)` | `EVALUATED`, `INSUFFICIENT_SAMPLE`, `INSUFFICIENT_DATA` |
| `sample_minutes` | `INTEGER` | Cumulative minutes observed as-of cutoff |
| `sample_matches` | `INTEGER` | Cumulative matches observed as-of cutoff |
| `confidence` | `VARCHAR(32)` | `HIGH` (>=900m), `MEDIUM` (600-899m), `LOW` (270-599m), `INSUFFICIENT_SAMPLE` (<270m) |
| `position_group` | `VARCHAR(16)` | Position Family: `GK`, `DEF`, `MID`, `ATT` |
| `contribution_vector` | `JSONB` | 7-dimensional normalized contribution vector |
| `intelligence_vector` | `JSONB` | Multi-layer canonical intelligence vector |
| `peer_benchmarks` | `JSONB` | Position-group distributions, Z-scores, and percentiles |
| `contextual_adjustments`| `JSONB` | Competition strength, starter/sub ratios, exposure share |
| `explanations` | `JSONB` | Deterministic `why_strong`, `why_different`, `why_low_confidence` |
| `trajectory` | `JSONB` | Chronological match timeline array |
| `role_profile_id` | `UUID` | Nullable FK -> `player_role_profiles.id` |
| `tactical_fit_id` | `UUID` | Nullable FK -> `player_tactical_fits.id` |
| `provenance` | `JSONB` | Version, source snapshot IDs, upstream versions |
| `created_at` | `TIMESTAMPTZ` | Record creation timestamp |

**Unique Constraint**: `("player_id", "as_of", "calculation_version")` ensures idempotent execution.

---

## 4. API Endpoints

1. `GET /api/v1/players/{id}/intelligence`:
   - Returns full `PlayerIntelligenceResponse` containing vectors, benchmarks, explanations, and context.
2. `GET /api/v1/players/{id}/trajectory`:
   - Returns chronological match-by-match performance, rolling impact, and seasonal trends.
3. `GET /api/v1/players/{id}/benchmarks`:
   - Returns position-group peer percentiles ($P \in [0, 100]$), Z-scores, and group baseline means/stds.
4. `GET /api/v1/players/{id}/similar?mode={mode}`:
   - Supports modes: `composite` (default), `contribution`, `role`, `tactical`, `replacement`.
