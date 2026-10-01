"""Multi-Dimensional Player Similarity and Explainability Engine (Phase 2 Slice 2).
Computes statistical, role, and contextual similarity scores between players and produces
feature-level explanations for 'Why Similar' and 'Why Not Similar'.
"""
from __future__ import annotations

import math
from typing import Any
import numpy as np

from app.roles.registry import DIMENSIONS, PositionGroup, ROLE_FEATURE_REGISTRY

DEFAULT_WEIGHT_STATISTICAL = 0.50
DEFAULT_WEIGHT_ROLE = 0.35
DEFAULT_WEIGHT_CONTEXTUAL = 0.15


class PlayerSimilarityEngine:
    """Calculates multi-dimensional similarity and explains feature contributions."""

    def __init__(
        self,
        w_statistical: float = DEFAULT_WEIGHT_STATISTICAL,
        w_role: float = DEFAULT_WEIGHT_ROLE,
        w_contextual: float = DEFAULT_WEIGHT_CONTEXTUAL,
    ) -> None:
        self.w_stat = w_statistical
        self.w_role = w_role
        self.w_context = w_contextual

    def compute_statistical_similarity(
        self,
        vec_a: dict[str, float],
        vec_b: dict[str, float],
    ) -> float:
        """Computes cosine similarity between standardized feature vectors."""
        common_keys = sorted(set(vec_a.keys()) & set(vec_b.keys()))
        if not common_keys:
            return 0.5

        u = np.array([vec_a[k] for k in common_keys], dtype=np.float64)
        v = np.array([vec_b[k] for k in common_keys], dtype=np.float64)

        norm_u = float(np.linalg.norm(u))
        norm_v = float(np.linalg.norm(v))

        if norm_u < 1e-6 or norm_v < 1e-6:
            return 0.5

        cos_sim = float(np.dot(u, v) / (norm_u * norm_v))
        # Map from [-1.0, 1.0] to [0.0, 1.0]
        return round(max(0.0, min(1.0, (cos_sim + 1.0) / 2.0)), 4)

    def compute_role_similarity(
        self,
        scores_a: dict[str, float],
        scores_b: dict[str, float],
    ) -> float:
        """Computes Euclidean distance-derived similarity over continuous 9-dimension profile scores."""
        diffs = []
        for dim in DIMENSIONS:
            val_a = scores_a.get(dim, 0.5)
            val_b = scores_b.get(dim, 0.5)
            diffs.append((val_a - val_b) ** 2)

        euclidean_dist = math.sqrt(sum(diffs))
        # Max theoretical distance in [0, 1]^9 is sqrt(9) = 3.0
        max_dist = math.sqrt(len(DIMENSIONS))
        sim = 1.0 - (euclidean_dist / max_dist)
        return round(max(0.0, min(1.0, sim)), 4)

    def compute_contextual_similarity(
        self,
        pos_group_a: str,
        pos_group_b: str,
        minutes_a: int,
        minutes_b: int,
    ) -> float:
        """Computes contextual similarity based on position family and sample exposure."""
        # Positional alignment
        if pos_group_a == pos_group_b:
            pos_sim = 1.0
        elif {pos_group_a, pos_group_b} in [{PositionGroup.MID.value, PositionGroup.ATT.value}, {PositionGroup.DEF.value, PositionGroup.MID.value}]:
            pos_sim = 0.50
        else:
            pos_sim = 0.10

        # Exposure alignment (penalizes comparing a 1800-minute regular with a 90-minute fringe player)
        max_min = max(minutes_a, minutes_b, 1)
        min_min = min(minutes_a, minutes_b)
        exposure_sim = min_min / max_min

        context_sim = 0.70 * pos_sim + 0.30 * exposure_sim
        return round(max(0.0, min(1.0, context_sim)), 4)

    def compute_contribution_similarity(
        self,
        contrib_a: dict[str, Any],
        contrib_b: dict[str, Any],
    ) -> float:
        """Computes Euclidean-derived similarity across normalized 7 contribution dimensions (Phase 3.2H)."""
        dims = ["passing", "creation", "finishing", "defending", "duels", "retention", "goalkeeping"]
        diffs = []
        for dim in dims:
            item_a = contrib_a.get(dim)
            item_b = contrib_b.get(dim)
            raw_a = getattr(item_a, "score", None) if hasattr(item_a, "score") else (item_a.get("score") if isinstance(item_a, dict) else item_a)
            raw_b = getattr(item_b, "score", None) if hasattr(item_b, "score") else (item_b.get("score") if isinstance(item_b, dict) else item_b)
            val_a = float(raw_a) if raw_a is not None else 0.5
            val_b = float(raw_b) if raw_b is not None else 0.5
            diffs.append((val_a - val_b) ** 2)

        euclidean_dist = math.sqrt(sum(diffs))
        max_dist = math.sqrt(len(dims))
        sim = 1.0 - (euclidean_dist / max_dist)
        return round(max(0.0, min(1.0, sim)), 4)

    def compute_overall_similarity(
        self,
        stat_sim: float,
        role_sim: float,
        context_sim: float,
        contrib_sim: float | None = None,
        mode: str = "composite",
    ) -> float:
        """Computes multi-mode similarity score (Phase 3.2H).
        Supported modes: 'composite', 'contribution', 'role', 'tactical', 'replacement'.
        """
        c_sim = contrib_sim if contrib_sim is not None else role_sim

        if mode == "contribution":
            return c_sim
        elif mode == "role":
            return role_sim
        elif mode == "tactical":
            return round(0.60 * role_sim + 0.40 * stat_sim, 4)
        elif mode == "replacement":
            # Replacement mode emphasizes functional role and contribution with context penalty
            return round(0.40 * role_sim + 0.40 * c_sim + 0.20 * context_sim, 4)
        else:
            # Default composite mode: backward-compatible
            overall = (
                self.w_stat * stat_sim
                + self.w_role * role_sim
                + self.w_context * context_sim
            )
            return round(max(0.0, min(1.0, overall)), 4)

    def generate_explanations(
        self,
        scores_a: dict[str, float],
        scores_b: dict[str, float],
        vec_a: dict[str, float],
        vec_b: dict[str, float],
        player_a_name: str = "Player A",
        player_b_name: str = "Player B",
    ) -> dict[str, list[str]]:
        """Produces explainable differences: why the players are similar and where they diverge."""
        why_similar: list[str] = []
        why_different: list[str] = []

        # Analyze dimensional differences on actively specified or non-zero dimensions
        dim_deltas: list[tuple[str, float, float, float]] = []
        candidate_dims = [
            dim for dim in DIMENSIONS
            if (dim in scores_a or dim in scores_b) and (scores_a.get(dim, 0.0) > 0.0 or scores_b.get(dim, 0.0) > 0.0)
        ] or DIMENSIONS

        for dim in candidate_dims:
            val_a = scores_a.get(dim, 0.5)
            val_b = scores_b.get(dim, 0.5)
            delta = abs(val_a - val_b)
            avg_val = (val_a + val_b) / 2.0
            dim_deltas.append((dim, delta, avg_val, val_a - val_b))

        # Sort for similarity: prioritize smallest delta combined with highest active presence
        similar_dims = sorted(
            [d for d in dim_deltas if d[1] <= 0.20 and d[2] >= 0.40],
            key=lambda x: (x[1], -x[2]),
        )
        for dim, delta, avg_val, _ in similar_dims[:3]:
            val_a = scores_a.get(dim, 0.5)
            val_b = scores_b.get(dim, 0.5)
            strength_desc = "high" if avg_val >= 0.65 else "comparable"
            why_similar.append(
                f"Both players exhibit {strength_desc} {dim} tendencies ({val_a:.2f} vs {val_b:.2f}, delta {delta:.2f})."
            )

        # Fallback if few dimensional similarities found
        if not why_similar:
            common_keys = sorted(set(vec_a.keys()) & set(vec_b.keys()))
            feat_deltas = sorted(
                [(k, abs(vec_a[k] - vec_b[k])) for k in common_keys],
                key=lambda x: x[1],
            )
            for k, delta in feat_deltas[:2]:
                why_similar.append(f"Similar output on metric '{k}' (normalized delta {delta:.2f}).")

        # Sort for differences: largest delta
        different_dims = sorted(
            [d for d in dim_deltas if d[1] >= 0.15],
            key=lambda x: x[1],
            reverse=True,
        )
        for dim, delta, _, diff in different_dims[:3]:
            val_a = scores_a.get(dim, 0.5)
            val_b = scores_b.get(dim, 0.5)
            leader = player_a_name if diff > 0 else player_b_name
            trailer = player_b_name if diff > 0 else player_a_name
            why_different.append(
                f"Divergence in {dim}: {leader} ({max(val_a, val_b):.2f}) rates significantly higher than {trailer} ({min(val_a, val_b):.2f}) with delta {delta:.2f}."
            )

        if not why_different:
            why_different.append("No significant functional divergences identified across major dimensions.")

        return {
            "why_similar": why_similar,
            "why_different": why_different,
        }
