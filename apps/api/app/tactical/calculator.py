"""Deterministic Tactical Fit Calculator (Phase 2 Slice 3).
Calculates position fit, role fit, dimensional fit, style fit, and contextual fit
with evidence-based confidence and strict uncertainty awareness.
"""
from __future__ import annotations

import math
from typing import Any

from app.roles.registry import CONTROLLED_ARCHETYPES, PositionGroup, map_position_to_group
from app.tactical.contexts import TacticalContext, TacticalRequirement

# Default component weights
DEFAULT_WEIGHT_POSITION = 0.20
DEFAULT_WEIGHT_ROLE = 0.25
DEFAULT_WEIGHT_DIMENSION = 0.35
DEFAULT_WEIGHT_STYLE = 0.10
DEFAULT_WEIGHT_CONTEXT = 0.10

MINIMUM_EXPOSURE_MINUTES = 450
TARGET_EXPOSURE_MINUTES = 900


class TacticalFitCalculator:
    """Pure analytical calculator for evaluating tactical compatibility."""

    def __init__(
        self,
        w_position: float = DEFAULT_WEIGHT_POSITION,
        w_role: float = DEFAULT_WEIGHT_ROLE,
        w_dimension: float = DEFAULT_WEIGHT_DIMENSION,
        w_style: float = DEFAULT_WEIGHT_STYLE,
        w_context: float = DEFAULT_WEIGHT_CONTEXT,
    ) -> None:
        self.w_position = w_position
        self.w_role = w_role
        self.w_dimension = w_dimension
        self.w_style = w_style
        self.w_context = w_context

    def calculate_position_fit(
        self,
        player_position: str | None,
        player_position_group: PositionGroup,
        target_position: str,
        target_position_group: PositionGroup,
    ) -> float:
        """Evaluates positional compatibility between player's nominal position and tactical role position."""
        if not player_position:
            return 0.0

        p_pos = player_position.strip().upper()
        t_pos = target_position.strip().upper()

        # Exact nominal position match (e.g. DM == DM, CB == CB)
        if p_pos == t_pos:
            return 1.0

        # Same position group family (e.g. CM playing DM, both MID)
        if player_position_group == target_position_group:
            return 0.85

        # Adjacent tactical families (MID <-> ATT or MID <-> DEF)
        adjacent_pairs = [
            {PositionGroup.MID, PositionGroup.ATT},
            {PositionGroup.MID, PositionGroup.DEF},
        ]
        if {player_position_group, target_position_group} in adjacent_pairs:
            return 0.40

        # Completely divergent (e.g. GK <-> Outfield)
        return 0.05

    def calculate_role_fit(
        self,
        player_primary_archetype: str | None,
        player_secondary_archetype: str | None,
        target_role: str,
        profile_scores: dict[str, float],
        target_position_group: PositionGroup,
    ) -> float:
        """Evaluates functional archetype compatibility."""
        target_lower = target_role.strip().lower()

        # Direct primary archetype match
        if player_primary_archetype and player_primary_archetype.strip().lower() == target_lower:
            return 1.0

        # Direct secondary archetype match
        if player_secondary_archetype and player_secondary_archetype.strip().lower() == target_lower:
            return 0.80

        # Functional projection onto target archetype dimensional weights
        archetypes = CONTROLLED_ARCHETYPES.get(target_position_group, [])
        target_arch = next((a for a in archetypes if a["name"].lower() == target_lower), None)

        if target_arch:
            weights = target_arch["weights"]
            total_w = sum(abs(w) for w in weights.values())
            if total_w > 0:
                score = sum(w * profile_scores.get(dim, 0.5) for dim, w in weights.items())
                normalized = score / total_w
                return round(max(0.0, min(1.0, normalized)), 4)

        return 0.50

    def calculate_dimensional_fit(
        self,
        profile_scores: dict[str, float],
        requirements: list[TacticalRequirement],
    ) -> tuple[float, dict[str, Any]]:
        """Evaluates dimensional fit against individual requirements and aggregates weighted score."""
        if not requirements:
            return 0.50, {}

        breakdown: dict[str, Any] = {}
        total_weighted_fit = 0.0
        total_weight = 0.0

        for req in requirements:
            player_val = profile_scores.get(req.dimension, 0.5)
            # Compatibility formulation: 1 - |player - required|
            base_fit = max(0.0, 1.0 - abs(player_val - req.required_strength))

            # Penalty if falling below critical minimum threshold
            penalty = 0.0
            deficit = 0.0
            if req.minimum_threshold is not None and player_val < req.minimum_threshold:
                deficit = round(req.minimum_threshold - player_val, 4)
                # Proportional penalty up to 0.50 of the base fit
                penalty = round((deficit / req.minimum_threshold) * 0.50, 4)

            final_fit = max(0.0, round(base_fit - penalty, 4))
            w = req.importance_weight

            breakdown[req.dimension] = {
                "player_score": round(player_val, 4),
                "required_strength": req.required_strength,
                "fit_score": final_fit,
                "importance_weight": w,
                "minimum_threshold": req.minimum_threshold,
                "deficit": deficit,
            }

            total_weighted_fit += final_fit * w
            total_weight += w

        weighted_dim_fit = total_weighted_fit / total_weight if total_weight > 0 else 0.50
        return round(weighted_dim_fit, 4), breakdown

    def calculate_style_fit(
        self,
        profile_scores: dict[str, float],
        context: TacticalContext,
    ) -> float | None:
        """Evaluates alignment with team style requirements where specified."""
        components: list[float] = []

        if context.possession_style == "HIGH_POSSESSION":
            components.append(0.6 * profile_scores.get("distribution", 0.5) + 0.4 * profile_scores.get("carrying", 0.5))
        elif context.possession_style in {"DIRECT", "COUNTER_ATTACK"}:
            components.append(0.6 * profile_scores.get("progression", 0.5) + 0.4 * profile_scores.get("finishing", 0.5))

        if context.pressing_style == "HIGH_PRESS":
            components.append(0.6 * profile_scores.get("defending", 0.5) + 0.4 * profile_scores.get("duels", 0.5))
        elif context.pressing_style in {"LOW_BLOCK", "MID_BLOCK"}:
            components.append(0.7 * profile_scores.get("defending", 0.5) + 0.3 * profile_scores.get("discipline", 0.5))

        if context.build_up_style == "SHORT_PASSING":
            components.append(profile_scores.get("distribution", 0.5))

        if not components:
            return None

        return round(sum(components) / len(components), 4)

    def calculate_contextual_fit(
        self,
        sample_minutes: int,
        target_minutes: int = TARGET_EXPOSURE_MINUTES,
    ) -> float:
        """Evaluates exposure maturity to avoid overvaluing small samples."""
        ratio = min(1.0, sample_minutes / target_minutes)
        return round(ratio, 4)

    def calculate_composite_fit(
        self,
        position_fit: float,
        role_fit: float,
        dimension_fit: float,
        style_fit: float | None,
        contextual_fit: float | None,
    ) -> float:
        """Calculates normalized composite tactical fit score."""
        numerator = (
            self.w_position * position_fit
            + self.w_role * role_fit
            + self.w_dimension * dimension_fit
        )
        denominator = self.w_position + self.w_role + self.w_dimension

        if style_fit is not None:
            numerator += self.w_style * style_fit
            denominator += self.w_style

        if contextual_fit is not None:
            numerator += self.w_context * contextual_fit
            denominator += self.w_context

        composite = numerator / denominator if denominator > 0 else 0.50
        return round(max(0.0, min(1.0, composite)), 4)

    def evaluate_confidence_and_status(
        self,
        sample_minutes: int,
        sample_matches: int,
        role_status: str,
        composite_fit: float,
    ) -> tuple[str, str]:
        """Strictly evaluates confidence and fit status based on sample evidence."""
        # Insufficient sample gate
        if sample_minutes < MINIMUM_EXPOSURE_MINUTES or role_status == "INSUFFICIENT_SAMPLE":
            return "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"

        # Confidence level
        if sample_minutes >= TARGET_EXPOSURE_MINUTES and sample_matches >= 10:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"

        # Fit categorization
        if composite_fit >= 0.75:
            fit_status = "FIT"
        elif composite_fit >= 0.55:
            fit_status = "MODERATE_FIT"
        else:
            fit_status = "POOR_FIT"

        return confidence, fit_status
