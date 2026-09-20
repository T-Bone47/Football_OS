# Player Role Discovery Architecture (Phase 2 Slice 2)

## 1. Core Principle: Position vs. Functional Role

In modern football analytics, a player's nominal position (e.g., `CM`) is distinct from their functional role (e.g., `Deep Distributor`, `Progressive Midfielder`, `Ball-Winning Midfielder`, `Chance Creator`, or `Box-to-Box Midfielder`).

The Football Intelligence OS Role Discovery Engine discovers data-derived functional archetypes from empirical player behaviors captured in leakage-safe `FeatureSnapshot` records rather than hardcoding static position mappings.

---

## 2. Two-Layer Role System

The architecture separates player intelligence into two layers:

1. **Role Profile**:
   A continuous multi-dimensional representation of a player's functional tendencies across 9 dimensions:
   - `distribution`: Passing volume, completion accuracy, pass involvement
   - `progression`: Key passing, forward ball advancement, progressive dribbling
   - `creation`: Assists per 90, shot creation, goal service
   - `finishing`: Goal scoring rate, shooting volume, box efficiency
   - `defending`: Tackles, interceptions, blocked passes/shots, defensive actions per 90
   - `duels`: Contested ground and aerial duel volume, win percentage
   - `carrying`: Take-on attempts, 1v1 dribble success rate
   - `discipline`: Foul frequency, card accumulation
   - `goalkeeping`: Saves per match, goals conceded, clean sheets, save percentage

   Each dimension is normalized into a continuous score `[0.0, 1.0]` using robust logistic transformations.

2. **Role Archetype**:
   A human-readable classification derived deterministically from profile tendencies and matched against a controlled domain vocabulary.

---

## 3. Position Groups & Controlled Vocabulary

To avoid comparing goalkeepers directly against center forwards, role discovery operates within 4 broad position families:

| Position Family | Canonical Positions | Controlled Archetypes |
| :--- | :--- | :--- |
| **GK** | G, GK, Goalkeeper | `Sweeper Keeper`, `Shot Stopper` |
| **DEF** | D, DF, CB, LB, RB, WB | `Ball-Playing Defender`, `Stopper`, `Progressive Fullback`, `Defensive Fullback`, `Inverted Fullback` |
| **MID** | M, MF, CM, DM, AM | `Deep Distributor`, `Progressive Midfielder`, `Ball-Winning Midfielder`, `Chance Creator`, `Box-to-Box Midfielder` |
| **ATT** | F, FW, ST, CF, LW, RW | `Finisher`, `Wide Creator`, `Pressing Forward`, `Target Forward`, `Complete Forward` |

---

## 4. Minimum Sample Requirement & Dataset Size Gate

Assigning stable roles to players with inadequate statistical evidence generates hallucinations. The system enforces strict, transparent gating:

- **Player Sample Gate**:
  - Threshold: `minimum_minutes = 450` (or `sample_matches >= 5`).
  - Players below this threshold are marked as `role_status = INSUFFICIENT_SAMPLE`.
  - Their raw continuous tendencies are calculated and stored with full provenance, but no arbitrary archetype or cluster is fabricated.

- **Dataset Size Gate for Unsupervised Clustering**:
  - Threshold: `minimum_population = 10` qualified players per position group.
  - If fewer than 10 qualified players exist in the target population, the clustering engine halts with `InsufficientDatasetError: INSUFFICIENT_DATASET`.
  - The system reports `INSUFFICIENT_DATASET` honestly and preserves analytical integrity.

---

## 5. Standardization & Outlier Protection

- **Standardization Method**: Z-score normalization `(x - mean) / std` fitted strictly on historical or population baselines.
- **Outlier Protection**: Winsorization clamped to `[-3.0, 3.0]` standard deviations to prevent extreme individual fixtures or count anomalies from distorting cluster geometry.
- **Temporal Leakage Policy**: When evaluating historical snapshots, scaling parameters are derived solely from data available as of the snapshot timestamp (`as_of`). Future matches are strictly excluded.

---

## 6. Clustering Methodology & Stability

When the qualified population satisfies the dataset size gate:
1. **Candidate Algorithms**:
   - `KMeans` evaluated across $K \in [2, 6]$ with fixed `random_state=42`.
   - `GaussianMixture` (GMM) for probabilistic cluster boundary verification.
2. **Model Diagnostics**:
   - Objective silhouette score (`silhouette_score`) evaluation.
   - Within-cluster inertia and minimum cluster size enforcement.
3. **Stability Verification**:
   - Cluster assignments are tested across multiple seeds using Adjusted Rand Index (ARI).
   - Only cluster models exhibiting high assignment stability ($\text{ARI} \ge 0.70$) are promoted.
4. **Centroid Characterization**:
   - Each cluster centroid is profiled by dominant dimensions and mapped to the closest controlled vocabulary archetype.

---

## 7. PostgreSQL Persistence & Versioning

Role profiles are stored in the canonical `player_role_profiles` table:
- Unique constraint: `(player_id, feature_set_version, as_of)`
- Standardized feature vectors and continuous 9-dimension profile scores are stored in indexed `JSONB` columns.
- Indexes: `player_id`, `as_of`, `position_group`, `primary_archetype`.

Every profile records full provenance:
- `source_feature_snapshot_id`
- `feature_set_version` (`role_feature_set_v1`)
- `min_minutes_threshold` (450)
- `evaluation_time`
