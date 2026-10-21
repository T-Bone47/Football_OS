"""Which valuation-model inputs carry real information, and which are synthetic stand-ins.

ValuationMLDatasetBuilder.build_samples() fills 22 of the model's 30 features with per-position
constants (rating 7.05 for every midfielder), age proxies (minutes = age * 95) or literals
(starter_ratio 0.85 for everyone). They say nothing about an individual player, so a model trained
on them is a function of age, position and trailing market medians - not of performance - and its
feature attributions on these columns are artifacts.

tests/unit/test_feature_provenance.py keeps this declaration in sync with dataset.py by static
analysis, so a new constant feature cannot be added without being declared here. The release gate
treats a non-empty SYNTHETIC_FEATURES as a failed `training_features_observed` check.
"""
from __future__ import annotations

SYNTHETIC_FEATURES: tuple[str, ...] = (
    "observed_minutes_as_of",
    "appearances_as_of",
    "rating_avg_as_of",
    "goals_per_90_as_of",
    "assists_per_90_as_of",
    "defensive_actions_per_90_as_of",
    "pass_accuracy_as_of",
    "passing_contribution_index",
    "creation_contribution_index",
    "finishing_contribution_index",
    "defending_contribution_index",
    "duels_contribution_index",
    "retention_contribution_index",
    "goalkeeping_contribution_index",
    "role_archetype_encoded",
    "archetype_confidence",
    "trajectory_volatility_score",
    "performance_stability",
    "club_strength_baseline",
    "starter_ratio",
    "total_career_transfers_prior",
    "days_since_prior_transfer",
)

OBSERVED_FEATURES: tuple[str, ...] = (
    "age_at_transfer",
    "age_curve_factor",
    "position_group_encoded",
    "competition_tier_weight",
    "cohort_median_fee_eur",
    "cohort_iqr_fee_eur",
    "comparable_median_fee_eur",
    "comparable_count",
)


def training_features_observed() -> bool:
    """True only when every training feature is computed from real per-player data."""
    return not SYNTHETIC_FEATURES
