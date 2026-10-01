# Player Intelligence Vector (Phase 3.2E & 3.2F)

## 1. Concept and Specification

Rather than reducing a footballer's multidimensional capability to an arbitrary, unexplainable single overall rating (e.g. FIFA "85"), Football Intelligence OS compiles a **versioned, auditable, multi-layer Player Intelligence Vector**.

The vector decouples:
1. **Performance**: Observable rate metrics per 90 minutes.
2. **Contribution**: Position-normalized functional contribution across 7 dimensions.
3. **Role Archetype**: Functional positional archetype assignments and 9-dimensional scoring.
4. **Action Value**: Empirical net impact per 90 and spatial threat status.
5. **Context**: Competition tier, starter exposure, and match context multipliers.
6. **Uncertainty**: Data sufficiency status, sample minutes, sample matches, and confidence tier.

---

## 2. Structure of `intelligence_vector`

```json
{
  "feature_set_version": "intelligence_v1",
  "player_id": "adfa8dcb-de2e-41b0-a84e-b8a4f0b02bad",
  "position_group": "MID",
  "performance": {
    "minutes": 90,
    "matches": 1,
    "goals_p90": null,
    "assists_p90": null,
    "shots_p90": null,
    "passes_p90": null,
    "key_passes_p90": null,
    "pass_accuracy": 82.5,
    "tackles_p90": null,
    "interceptions_p90": null,
    "blocks_p90": null,
    "duels_won_p90": null,
    "duel_win_pct": 55.0,
    "dribbles_succ_p90": null
  },
  "contribution": {
    "passing": { "score": null, "percentile": null, "status": "INSUFFICIENT_SAMPLE" },
    "creation": { "score": null, "percentile": null, "status": "INSUFFICIENT_SAMPLE" },
    "finishing": { "score": null, "percentile": null, "status": "INSUFFICIENT_SAMPLE" },
    "defending": { "score": null, "percentile": null, "status": "INSUFFICIENT_SAMPLE" },
    "duels": { "score": null, "percentile": null, "status": "INSUFFICIENT_SAMPLE" },
    "retention": { "score": null, "percentile": null, "status": "INSUFFICIENT_SAMPLE" },
    "goalkeeping": { "score": null, "percentile": null, "status": "INSUFFICIENT_SAMPLE" }
  },
  "role": {
    "primary_archetype": null,
    "secondary_archetype": null,
    "archetype_confidence": null,
    "dimension_scores": {}
  },
  "action_value": {
    "action_impact_p90": null,
    "net_action_value": null,
    "total_actions_evaluated": 16,
    "spatial_data_sufficient": false
  },
  "context": {
    "competition_tier": 0.85,
    "starter_ratio": 1.0,
    "minutes_per_match": 90.0,
    "exposure_share": 1.0,
    "context_multiplier": 0.875
  },
  "uncertainty": {
    "data_status": "INSUFFICIENT_SAMPLE",
    "sample_minutes": 90,
    "sample_matches": 1,
    "confidence": "INSUFFICIENT_SAMPLE"
  }
}
```

---

## 3. Contribution Vector Dimensions (Phase 3.2E)

The 7 canonical contribution dimensions represent orthogonal facets of football output:

1. **Passing**: Pass volume, accuracy, completion over expected baselines.
2. **Creation**: Key passes, shot assists, chance creation volume.
3. **Finishing**: Non-penalty goals, shots on target, box penetration.
4. **Defending**: Tackles, interceptions, clearances, blocks.
5. **Duels**: Ground and aerial duel volume and win rates.
6. **Retention**: Low turnover rate, possession preservation under pressure.
7. **Goalkeeping**: Saves, goals prevented, distribution under pressure (for GK group).

---

## 4. Reusability Across Intelligence Layers

The Player Intelligence Vector is specifically engineered as a standardized input for:
- **Role Discovery**: Validating archetype clusters against multidimensional contribution profiles.
- **Similarity Engine**: Powering `mode=contribution` and `mode=replacement` Euclidean/cosine calculations.
- **Tactical Fit**: Comparing squad tactical role templates against vector capability layers.
- **Transfer Valuation & Risk (Phase 4)**: Acting as the foundational feature matrix for performance valuation.
