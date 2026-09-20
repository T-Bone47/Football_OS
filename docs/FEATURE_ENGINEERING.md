# Feature Engineering Layer — Phase 2 Slice 1

The Feature Engineering layer transitions the **Football Intelligence OS** from **Data Normalization** (Silver layer) to **Football Intelligence** (Gold/Analytical feature layer).

It computes versioned, reproducible, leakage-safe analytical feature snapshots for players, teams, and match contexts, strictly grounding every metric in historical canonical data available prior to match kickoff.

---

## 1. Core Architectural Principles

1. **Strict Temporal Leakage Prevention**:
   - Every analytical feature computed for Match $T$ (or as of timestamp $T$) uses **ONLY** data with `match_date < as_of`.
   - Future matches, future outcomes, future player statistics, future ratings, and future transfers are completely invisible to past feature snapshots.
   - Verified by the **Definitive Temporal Leakage Test**: inserting a high-scoring future match (e.g. Match 6 with 10 goals) has 0.0% effect on Match 5 pre-match features.

2. **Strict Null vs Zero Semantics**:
   - Explicit zero performance (e.g. 0 goals scored in 900 minutes) produces `0.0` for rates (`goals_per_90 = 0.0`).
   - Unrecorded / missing data (e.g. missing pass accuracy or null metric) produces `None`/`NULL`.
   - If minutes played is <= 0, per-90 rates evaluate to `None`/`NULL` rather than fabricating zero.

3. **Goalkeeper vs Outfield Metric Isolation**:
   - Goalkeeping metrics (`saves`, `goals_conceded`, `clean_sheets`, `save_rate`) are computed exclusively for goalkeepers (`position == 'G'`).
   - Outfield players receive explicit `None`/`NULL` for all goalkeeping metrics.

4. **Exposure & Small-Sample Transparency**:
   - Features preserve sample context (`sample_matches`, `appearances`, `starts`, `minutes`) alongside rates so downstream models can account for sample size uncertainty without relying on fabricated confidence scores.

5. **Deterministic Provenance & Versioning**:
   - Every feature snapshot stores `feature_set`, `calculation_version`, and full `provenance` metadata containing `source_entity`, `source_match_ids`, `record_count`, and `calculated_at`.

---

## 2. Canonical Model: `FeatureSnapshot`

Table: `feature_snapshots`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID` (PK) | Unique snapshot identifier |
| `entity_type` | `VARCHAR(32)` | `'player'`, `'team'`, or `'match'` |
| `entity_id` | `UUID` | Canonical identifier (`players.id`, `clubs.id`, or `matches.id`) |
| `match_id` | `UUID` (FK) | Optional reference to target `matches.id` (ON DELETE CASCADE) |
| `feature_set` | `VARCHAR(64)` | Feature set identifier (e.g. `'player_match_v1'`, `'team_match_v1'`, `'match_context_v1'`) |
| `calculation_version`| `VARCHAR(32)` | Semantic calculation version (e.g. `'1.0.0'`) |
| `as_of` | `TIMESTAMPTZ` | Strict pre-match temporal cutoff |
| `season_id` | `UUID` (FK) | Optional reference to `seasons.id` |
| `competition_id` | `UUID` (FK) | Optional reference to `competitions.id` |
| `features` | `JSONB` | Strongly-typed dictionary of calculated features |
| `provenance` | `JSONB` | Audit trail with source match IDs and calculation metadata |
| `created_at` | `TIMESTAMPTZ` | Snapshot creation timestamp |

**Natural Uniqueness Constraint**:
```sql
UNIQUE (entity_type, entity_id, feature_set, calculation_version, as_of)
```

**Indexes**:
- `ix_feature_snapshots_entity (entity_type, entity_id)`
- `ix_feature_snapshots_match_id (match_id)`
- `ix_feature_snapshots_as_of (as_of)`
- `ix_feature_snapshots_season_id (season_id)`
- `ix_feature_snapshots_competition_id (competition_id)`

---

## 3. Rolling Windows

Features are computed across 4 deterministic rolling windows:
1. `last_3`: 3 most recent matches strictly before `as_of`.
2. `last_5`: 5 most recent matches strictly before `as_of`.
3. `last_10`: 10 most recent matches strictly before `as_of`.
4. `season_to_date`: All matches in the target competition season strictly before `as_of`.

---

## 4. Feature Taxonomy & Formulas

### Player Features (`player_match_v1`)

| Family | Feature Name Pattern | Formula / Definition |
| :--- | :--- | :--- |
| **Usage** | `appearances_{win}` | Count of matches where `minutes > 0` |
| | `starts_{win}` | Count of matches with `is_starter == True` |
| | `minutes_{win}` | Sum of minutes played in window |
| | `minutes_per_match_{win}` | `minutes / appearances` (null if appearances == 0) |
| | `starter_rate_{win}` | `starts / appearances` |
| | `substitution_rate_{win}` | `substitutions / appearances` |
| **Scoring** | `goals_{win}` | Sum of goals scored |
| | `assists_{win}` | Sum of assists |
| | `goals_per_90_{win}` | `goals / minutes * 90` (null if minutes <= 0) |
| | `assists_per_90_{win}` | `assists / minutes * 90` (null if minutes <= 0) |
| | `shots_total_{win}` | Sum of shots attempted |
| | `shots_per_90_{win}` | `shots / minutes * 90` (null if minutes <= 0) |
| | `shots_on_target_per_90_{win}` | `shots_on_target / minutes * 90` (null if minutes <= 0) |
| **Creation** | `passes_key_{win}` | Sum of key passes |
| | `passes_key_per_90_{win}` | `passes_key / minutes * 90` (null if minutes <= 0) |
| **Passing** | `passes_total_{win}` | Sum of passes attempted |
| | `passes_per_90_{win}` | `passes / minutes * 90` (null if minutes <= 0) |
| | `pass_accuracy_avg_{win}` | Average pass accuracy percentage |
| **Defending** | `tackles_total_{win}` | Sum of tackles |
| | `tackles_per_90_{win}` | `tackles / minutes * 90` (null if minutes <= 0) |
| | `interceptions_{win}` | Sum of interceptions |
| | `blocks_{win}` | Sum of blocks |
| | `defensive_actions_per_90_{win}` | `(tackles + interceptions + blocks) / minutes * 90` |
| **Duels** | `duels_total_{win}` | Sum of contested duels |
| | `duels_won_{win}` | Sum of duels won |
| | `duel_win_rate_{win}` | `duels_won / duels_total` (null if duels_total <= 0) |
| **Dribbling** | `dribbles_attempts_{win}` | Sum of dribble attempts |
| | `dribbles_success_{win}` | Sum of successful dribbles |
| | `dribble_success_rate_{win}` | `dribbles_success / dribbles_attempts` |
| **Discipline** | `yellow_cards_{win}` | Sum of yellow cards |
| | `red_cards_{win}` | Sum of red cards |
| | `fouls_committed_{win}` | Sum of fouls committed |
| | `fouls_drawn_{win}` | Sum of fouls drawn |
| **Rating** | `rating_avg_{win}` | Arithmetic mean of provider performance ratings |
| **Goalkeeping** | `saves_{win}` | Sum of saves (goalkeepers only; null for outfield) |
| | `goals_conceded_{win}` | Sum of goals conceded (goalkeepers only) |
| | `clean_sheets_{win}` | Count of matches with 0 goals conceded (goalkeepers only) |
| | `save_rate_{win}` | `saves / (saves + goals_conceded)` (goalkeepers only) |

---

### Team Features (`team_match_v1`)

| Family | Feature Name Pattern | Formula / Definition |
| :--- | :--- | :--- |
| **Results** | `matches_played_{win}` | Total matches played in window strictly before `as_of` |
| | `wins_{win}` | Count of wins |
| | `draws_{win}` | Count of draws |
| | `losses_{win}` | Count of losses |
| | `points_{win}` | Total points (`wins * 3 + draws * 1`) |
| | `points_per_match_{win}` | `points / matches_played` |
| | `win_rate_{win}` | `wins / matches_played` |
| **Goals** | `goals_scored_{win}` | Sum of goals scored |
| | `goals_conceded_{win}` | Sum of goals conceded |
| | `goal_difference_{win}` | `goals_scored - goals_conceded` |
| | `goals_scored_per_match_{win}` | `goals_scored / matches_played` |
| | `goals_conceded_per_match_{win}` | `goals_conceded / matches_played` |
| | `clean_sheets_{win}` | Matches with 0 goals conceded |
| | `clean_sheet_rate_{win}` | `clean_sheets / matches_played` |
| **Performance** | `possession_avg_{win}` | Mean possession percentage |
| | `shots_avg_{win}` | Mean shots attempted per match |
| | `shots_on_target_avg_{win}` | Mean shots on target per match |
| | `pass_accuracy_avg_{win}` | Mean pass accuracy percentage |
| | `fouls_avg_{win}` | Mean fouls committed per match |
| | `corners_avg_{win}` | Mean corner kicks won per match |
| **Home / Away** | `home_points_last_5` | Points per match in last 5 home matches before `as_of` |
| | `away_points_last_5` | Points per match in last 5 away matches before `as_of` |
| | `home_goals_scored_last_5` | Goals scored per match in last 5 home matches |
| | `away_goals_scored_last_5` | Goals scored per match in last 5 away matches |
| | `home_goals_conceded_last_5` | Goals conceded per match in last 5 home matches |
| | `away_goals_conceded_last_5` | Goals conceded per match in last 5 away matches |

---

### Match Context & Rest-Day Features (`match_context_v1`)

| Feature Name | Formula / Definition | Nullable |
| :--- | :--- | :--- |
| `days_since_previous_match` | `(target_match_date - previous_match_date).total_seconds() / 86400.0` | Yes (if first match) |
| `opponent_strength_baseline_points_per_match` | Mean points per match accumulated by opponent in last 5 matches before `as_of` | Yes |
| `opponent_strength_baseline_goal_diff` | Mean goal difference per match accumulated by opponent in last 5 matches before `as_of` | Yes |
| `team_strength_baseline_points_per_match` | Mean points per match accumulated by team in last 5 matches before `as_of` | Yes |
| `team_strength_baseline_goal_diff` | Mean goal difference per match accumulated by team in last 5 matches before `as_of` | Yes |

---

## 5. REST API Endpoints

### 1. `GET /api/v1/features/registry`
Returns the feature registry catalog and metadata.
- Query parameters:
  - `feature_set` (optional string, e.g. `player_match_v1`)
  - `entity_type` (optional string: `player`, `team`, `match`)

### 2. `GET /api/v1/players/{id}/features`
Retrieves or computes pre-match analytical features for a player.
- Query parameters:
  - `as_of` (optional ISO datetime cutoff, defaults to now or match date)
  - `match_id` (optional target match UUID for match context)
- Response: `FeatureSnapshotResponse`

### 3. `GET /api/v1/matches/{id}/features`
Retrieves or computes pre-match context, team features, rest days, and opponent strength baselines.
- Query parameters:
  - `as_of` (optional ISO datetime cutoff, defaults to target match kickoff)
- Response: `MatchContextFeaturesResponse`

---

## 6. Model-Ready Dataset Construction

The `FeatureService.build_model_ready_dataset` method constructs tabular datasets for offline training while strictly enforcing:
feature_as_of <= target_match_kickoff

Example usage:
```python
rows = await feature_service.build_model_ready_dataset(
    entity_type="team",
    feature_set="team_match_v1",
    start_date=datetime(2025, 8, 1, tzinfo=timezone.utc),
    end_date=datetime(2026, 5, 30, tzinfo=timezone.utc),
    target_column="result",
)
```

---

## 7. Known Limitations & Phase 2 Slice 2 Roadmap

- **Opponent-Adjusted Metrics**: Opponent strength is currently computed as a baseline rolling points/goal difference. Multi-level regression or opponent-adjusted rating normalization will be implemented in future modeling phases.
- **Player Role Archetypes & Similarity**: Unsupervised clustering, PCA, and vector search (`pgvector`) will be built in **Phase 2 — Slice 2**.
