"""Role Profiler (Phase 2 Slice 2).
Transforms raw analytical feature snapshots into continuous 9-dimension role profiles
and assigns data-driven role archetypes from a controlled vocabulary.
"""
from __future__ import annotations

import math
from typing import Any

from app.roles.registry import (
    CONTROLLED_ARCHETYPES,
    DIMENSIONS,
    PositionGroup,
    ROLE_FEATURE_REGISTRY,
    RoleFeatureDefinition,
)

MINIMUM_MINUTES_THRESHOLD = 450
MINIMUM_MATCHES_THRESHOLD = 5


class RoleProfiler:
    """Computes continuous player role profiles and data-driven archetypes."""

    def __init__(
        self,
        min_minutes: int = MINIMUM_MINUTES_THRESHOLD,
        min_matches: int = MINIMUM_MATCHES_THRESHOLD,
        scaler_params: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.min_minutes = min_minutes
        self.min_matches = min_matches
        self.scaler_params = scaler_params or {}

    def is_sample_sufficient(self, sample_minutes: int, sample_matches: int = 0) -> bool:
        """Determines whether player sample meets minimum evidence threshold for stable clustering/assignment."""
        return sample_minutes >= self.min_minutes

    def extract_role_features(
        self,
        raw_features: dict[str, Any],
        position_group: PositionGroup,
    ) -> dict[str, float]:
        """Extracts and validates features pertinent to the player's position family."""
        extracted: dict[str, float] = {}
        for feat_name, feat_def in ROLE_FEATURE_REGISTRY.items():
            if position_group not in feat_def.position_groups:
                continue

            val = raw_features.get(feat_def.source_feature)
            if val is None or not isinstance(val, (int, float)) or math.isnan(val):
                extracted[feat_name] = float(feat_def.default_value)
            else:
                extracted[feat_name] = float(val)
        return extracted

    def standardize(
        self,
        extracted_features: dict[str, float],
        custom_scaler_params: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, float]:
        """Standardizes role features with outlier winsorization clamping to [-3.0, 3.0]."""
        params = custom_scaler_params or self.scaler_params
        standardized: dict[str, float] = {}

        for feat_name, val in extracted_features.items():
            if feat_name in params:
                mean = params[feat_name].get("mean", 0.0)
                std = params[feat_name].get("std", 1.0)
                if std > 1e-6:
                    z = (val - mean) / std
                else:
                    z = 0.0
            else:
                # Fallback heuristic standardization if population params not yet fitted
                # Centers around default and assumes reasonable variance
                feat_def = ROLE_FEATURE_REGISTRY.get(feat_name)
                default_val = feat_def.default_value if feat_def else 0.0
                scale = max(abs(default_val), 1.0)
                z = (val - default_val) / scale

            # Winsorize / clamp to [-3.0, 3.0] to protect against extreme outliers
            standardized[feat_name] = max(-3.0, min(3.0, float(z)))

        return standardized

    def compute_dimensional_scores(
        self,
        standardized_features: dict[str, float],
        position_group: PositionGroup,
    ) -> dict[str, float]:
        """Aggregates standardized features into continuous [0.0, 1.0] dimensional profile scores."""
        dimension_values: dict[str, list[float]] = {dim: [] for dim in DIMENSIONS}

        for feat_name, z_val in standardized_features.items():
            feat_def = ROLE_FEATURE_REGISTRY.get(feat_name)
            if not feat_def or feat_def.dimension not in dimension_values:
                continue

            # Invert direction if metric is negative (e.g. fouls/yellow cards)
            effective_z = -z_val if feat_def.direction == "negative" else z_val
            dimension_values[feat_def.dimension].append(effective_z)

        profile_scores: dict[str, float] = {}
        for dim, values in dimension_values.items():
            if not values:
                # If dimension has no applicable features for position, baseline is 0.0 for GK/outfield specifics
                if dim == "goalkeeping" and position_group != PositionGroup.GK:
                    profile_scores[dim] = 0.0
                elif dim in {"finishing", "creation"} and position_group == PositionGroup.GK:
                    profile_scores[dim] = 0.0
                else:
                    profile_scores[dim] = 0.5
            else:
                # Mean z-score transformed via sigmoid to [0.0, 1.0]
                mean_z = sum(values) / len(values)
                # Logistic sigmoid: 1 / (1 + exp(-1.2 * z))
                sigmoid_val = 1.0 / (1.0 + math.exp(-1.2 * mean_z))
                profile_scores[dim] = round(sigmoid_val, 4)

        return profile_scores

    def assign_archetype(
        self,
        profile_scores: dict[str, float],
        position_group: PositionGroup,
    ) -> tuple[str | None, str | None, float | None]:
        """Assigns primary and secondary role archetypes from the controlled vocabulary with confidence."""
        archetypes = CONTROLLED_ARCHETYPES.get(position_group, [])
        if not archetypes:
            return f"Role Archetype {position_group.value}", None, 0.50

        scored_archetypes: list[tuple[str, float]] = []
        for arch in archetypes:
            score = 0.0
            total_weight = 0.0
            for dim, weight in arch["weights"].items():
                dim_score = profile_scores.get(dim, 0.5)
                score += weight * dim_score
                total_weight += abs(weight)

            normalized_score = score / total_weight if total_weight > 0 else 0.5
            scored_archetypes.append((arch["name"], normalized_score))

        scored_archetypes.sort(key=lambda x: x[1], reverse=True)

        primary_name, primary_score = scored_archetypes[0]
        secondary_name = scored_archetypes[1][0] if len(scored_archetypes) > 1 else None
        secondary_score = scored_archetypes[1][1] if len(scored_archetypes) > 1 else primary_score * 0.8

        # Confidence based on score separation and magnitude
        margin = max(0.0, primary_score - secondary_score)
        confidence = round(min(0.99, max(0.50, primary_score * 0.7 + margin * 1.5)), 4)

        return primary_name, secondary_name, confidence
