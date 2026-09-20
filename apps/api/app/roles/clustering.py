"""Role Discovery Engine (Phase 2 Slice 2).
Performs unsupervised clustering evaluation (KMeans, GMM, silhouette scoring, stability testing)
on qualified player populations while enforcing strict Dataset Size Gates.
"""
from __future__ import annotations

import logging
from typing import Any
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from app.roles.registry import (
    CONTROLLED_ARCHETYPES,
    PositionGroup,
    ROLE_FEATURE_REGISTRY,
)

logger = logging.getLogger(__name__)

MINIMUM_POPULATION_FOR_CLUSTERING = 10


class InsufficientDatasetError(ValueError):
    """Raised when the qualified player population is insufficient for clustering."""
    pass


class RoleDiscoveryEngine:
    """Discovers empirical role clusters from standardized player feature snapshots."""

    def __init__(
        self,
        min_population: int = MINIMUM_POPULATION_FOR_CLUSTERING,
        random_state: int = 42,
    ) -> None:
        self.min_population = min_population
        self.random_state = random_state

    def fit_scaler(
        self,
        player_features: list[dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        """Fits StandardScaler across the population of extracted role features."""
        if not player_features:
            return {}

        all_keys = list(player_features[0].keys())
        matrix = np.array([[p.get(k, 0.0) for k in all_keys] for p in player_features], dtype=np.float64)

        scaler = StandardScaler()
        scaler.fit(matrix)

        scaler_params: dict[str, dict[str, float]] = {}
        for i, key in enumerate(all_keys):
            scaler_params[key] = {
                "mean": float(scaler.mean_[i]),
                "std": float(scaler.scale_[i]) if scaler.scale_[i] > 1e-6 else 1.0,
            }
        return scaler_params

    def evaluate_clustering(
        self,
        standardized_vectors: list[dict[str, float]],
        position_group: PositionGroup,
        k_range: range | list[int] | None = None,
    ) -> dict[str, Any]:
        """Evaluates clustering configurations on qualified player population.
        Enforces Dataset Size Gate before proceeding.
        """
        n_samples = len(standardized_vectors)
        if n_samples < self.min_population:
            raise InsufficientDatasetError(
                f"INSUFFICIENT_DATASET: Position group {position_group.value} has {n_samples} qualified "
                f"players (minimum required for clustering: {self.min_population})."
            )

        feature_names = sorted(standardized_vectors[0].keys())
        X = np.array([[vec.get(k, 0.0) for k in feature_names] for vec in standardized_vectors], dtype=np.float64)

        if k_range is None:
            max_k = min(6, max(2, n_samples // 3))
            k_candidates = list(range(2, max_k + 1))
        else:
            k_candidates = [k for k in k_range if 2 <= k < n_samples]

        if not k_candidates:
            raise InsufficientDatasetError(
                f"INSUFFICIENT_DATASET: Cannot form clusters with n_samples={n_samples}."
            )

        best_k = k_candidates[0]
        best_silhouette = -1.0
        best_model: KMeans | None = None
        evaluations: list[dict[str, Any]] = []

        for k in k_candidates:
            km = KMeans(n_clusters=k, random_state=self.random_state, n_init=10)
            labels = km.fit_predict(X)
            score = float(silhouette_score(X, labels))
            inertia = float(km.inertia_)

            evaluations.append({
                "k": k,
                "silhouette_score": round(score, 4),
                "inertia": round(inertia, 2),
                "cluster_sizes": [int(s) for s in np.bincount(labels, minlength=k)],
            })

            if score > best_silhouette:
                best_silhouette = score
                best_k = k
                best_model = km

        # Cluster assignment stability test across random seeds
        km_alt = KMeans(n_clusters=best_k, random_state=self.random_state + 100, n_init=10)
        labels_alt = km_alt.fit_predict(X)
        stability_ari = float(adjusted_rand_score(best_model.labels_, labels_alt))

        # Centroid profile characterization
        centroids = best_model.cluster_centers_
        cluster_archetypes: list[dict[str, Any]] = []
        vocab = CONTROLLED_ARCHETYPES.get(position_group, [])

        for c_idx in range(best_k):
            centroid = centroids[c_idx]
            feat_scores = {feature_names[i]: float(centroid[i]) for i in range(len(feature_names))}

            # Sort features to determine dominant and weak dimensions
            sorted_feats = sorted(feat_scores.items(), key=lambda x: x[1], reverse=True)
            top_feats = [f"{k} ({v:+.2f})" for k, v in sorted_feats[:3]]
            bottom_feats = [f"{k} ({v:+.2f})" for k, v in sorted_feats[-3:]]

            # Best matching archetype from controlled vocabulary
            assigned_label = f"Archetype {position_group.value}-{c_idx + 1}"
            best_match_score = -999.0
            for arch in vocab:
                score = sum(
                    arch["weights"].get(ROLE_FEATURE_REGISTRY[k].dimension, 0.0) * feat_scores.get(k, 0.0)
                    for k in feat_scores if k in ROLE_FEATURE_REGISTRY
                )
                if score > best_match_score:
                    best_match_score = score
                    assigned_label = arch["name"]

            cluster_archetypes.append({
                "cluster_id": c_idx,
                "label": assigned_label,
                "size": int(np.sum(best_model.labels_ == c_idx)),
                "dominant_features": top_feats,
                "weak_features": bottom_feats,
            })

        return {
            "position_group": position_group.value,
            "population_size": n_samples,
            "selected_k": best_k,
            "silhouette_score": round(best_silhouette, 4),
            "stability_score_ari": round(stability_ari, 4),
            "evaluations": evaluations,
            "clusters": cluster_archetypes,
            "cluster_labels": [int(lbl) for lbl in best_model.labels_],
        }
