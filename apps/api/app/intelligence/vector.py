"""Canonical Player Contribution Vector & Player Intelligence Vector (Phase 3.2E/F).
Compiles multi-layer, interpretable intelligence representations from verified analytics.
"""
from __future__ import annotations

from typing import Any

from app.intelligence.taxonomy import (
    ConfidenceTier,
    DataStatus,
    INTELLIGENCE_FEATURE_SET_VERSION,
)


class PlayerIntelligenceVectorCompiler:
    """Compiles normalized contribution and intelligence vectors."""

    def compile_contribution_vector(
        self,
        dimensions: dict[str, Any],
        raw_metrics: dict[str, Any],
        confidence: str,
        status: str,
    ) -> dict[str, Any]:
        """Compiles the structured Player Contribution Vector (Phase 3.2E).
        Preserves nulls when sample is insufficient.
        """
        is_evaluated = status == DataStatus.EVALUATED.value

        vector: dict[str, Any] = {}
        for dim_name in ["passing", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]:
            dim_item = dimensions.get(dim_name)
            if dim_item:
                score = getattr(dim_item, "score", None) if hasattr(dim_item, "score") else dim_item.get("score")
                pct = getattr(dim_item, "percentile", None) if hasattr(dim_item, "percentile") else dim_item.get("percentile")
                metrics = getattr(dim_item, "key_metrics", {}) if hasattr(dim_item, "key_metrics") else dim_item.get("key_metrics", {})
                vector[dim_name] = {
                    "score": score if is_evaluated else None,
                    "percentile": pct if is_evaluated else None,
                    "key_metrics": metrics,
                    "confidence": confidence,
                    "status": status,
                }

        return vector

    def compile_intelligence_vector(
        self,
        player_id: str,
        position_group: str,
        raw_metrics: dict[str, Any],
        contribution_vector: dict[str, Any],
        role_profile: dict[str, Any] | None,
        context: dict[str, Any],
        action_values: dict[str, Any] | None,
        confidence: str,
        status: str,
    ) -> dict[str, Any]:
        """Compiles the canonical Player Intelligence Vector (Phase 3.2F).
        Unifies Performance, Contribution, Role, Context, Action Value, and Uncertainty.
        """
        is_evaluated = status == DataStatus.EVALUATED.value

        # 1. Performance Layer (per-90 rates)
        performance_layer = {
            "minutes": raw_metrics.get("minutes", 0),
            "matches": raw_metrics.get("matches", 0),
            "goals_p90": raw_metrics.get("goals_p90") if is_evaluated else None,
            "assists_p90": raw_metrics.get("assists_p90") if is_evaluated else None,
            "shots_p90": raw_metrics.get("shots_total_p90") if is_evaluated else None,
            "shots_on_target_p90": raw_metrics.get("shots_on_target_p90") if is_evaluated else None,
            "passes_p90": raw_metrics.get("passes_total_p90") if is_evaluated else None,
            "key_passes_p90": raw_metrics.get("passes_key_p90") if is_evaluated else None,
            "pass_accuracy": raw_metrics.get("avg_pass_accuracy"),
            "tackles_p90": raw_metrics.get("tackles_total_p90") if is_evaluated else None,
            "interceptions_p90": raw_metrics.get("interceptions_p90") if is_evaluated else None,
            "blocks_p90": raw_metrics.get("blocks_p90") if is_evaluated else None,
            "duels_won_p90": raw_metrics.get("duels_won_p90") if is_evaluated else None,
            "duel_win_pct": raw_metrics.get("duel_win_pct"),
            "dribbles_succ_p90": raw_metrics.get("dribbles_success_p90") if is_evaluated else None,
        }

        # 2. Role Layer
        role_scores = (role_profile.get("profile_scores") or {}) if role_profile else {}
        role_layer = {
            "primary_archetype": role_profile.get("primary_archetype") if role_profile else None,
            "secondary_archetype": role_profile.get("secondary_archetype") if role_profile else None,
            "archetype_confidence": role_profile.get("archetype_confidence") if role_profile else None,
            "dimension_scores": role_scores if is_evaluated else {},
        }

        # 3. Action Value Layer
        av_layer = {
            "action_impact_p90": (action_values.get("action_value_per_90") or action_values.get("impact_p90")) if action_values and is_evaluated else None,
            "net_action_value": action_values.get("net_action_value") if action_values and is_evaluated else None,
            "total_actions_evaluated": action_values.get("total_actions_evaluated", 0) if action_values else 0,
            "spatial_data_sufficient": action_values.get("spatial_data_sufficient", False) if action_values else False,
        }

        # 4. Context Layer
        context_layer = {
            "competition_tier": context.get("competition_tier", 0.75),
            "starter_ratio": context.get("starter_ratio", 0.0),
            "minutes_per_match": context.get("minutes_per_match", 0.0),
            "exposure_share": context.get("exposure_share", 0.0),
            "context_multiplier": context.get("context_multiplier", 1.0),
        }

        # 5. Uncertainty Layer
        uncertainty_layer = {
            "data_status": status,
            "confidence": confidence,
            "sample_minutes": raw_metrics.get("minutes", 0),
            "sample_matches": raw_metrics.get("matches", 0),
        }

        return {
            "feature_set_version": INTELLIGENCE_FEATURE_SET_VERSION,
            "player_id": str(player_id),
            "position_group": position_group,
            "performance": performance_layer,
            "contribution": contribution_vector,
            "role": role_layer,
            "action_value": av_layer,
            "context": context_layer,
            "uncertainty": uncertainty_layer,
        }
