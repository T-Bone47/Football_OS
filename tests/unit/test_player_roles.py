"""Unit tests for Player Role Discovery, Archetype Assignment, and Multi-Dimensional Similarity (Phase 2 Slice 2)."""
from __future__ import annotations

import pytest
from app.roles.clustering import InsufficientDatasetError, RoleDiscoveryEngine
from app.roles.profiler import MINIMUM_MINUTES_THRESHOLD, RoleProfiler
from app.roles.registry import (
    CONTROLLED_ARCHETYPES,
    DIMENSIONS,
    PositionGroup,
    ROLE_FEATURE_REGISTRY,
    map_position_to_group,
)
from app.roles.similarity import PlayerSimilarityEngine


def test_role_feature_registry_integrity():
    """Verifies that all registered role features conform to specification and map to the 9 dimensions."""
    assert len(ROLE_FEATURE_REGISTRY) >= 20

    for feat_name, feat_def in ROLE_FEATURE_REGISTRY.items():
        assert feat_def.name == feat_name
        assert feat_def.dimension in DIMENSIONS
        assert feat_def.direction in {"positive", "neutral", "negative"}
        assert len(feat_def.position_groups) > 0
        assert isinstance(feat_def.default_value, (int, float))

    for pg in PositionGroup:
        assert pg in CONTROLLED_ARCHETYPES
        assert len(CONTROLLED_ARCHETYPES[pg]) >= 2


def test_position_group_mapping():
    """Verifies canonical and provider positions map deterministically to position families."""
    assert map_position_to_group("G") == PositionGroup.GK
    assert map_position_to_group("Goalkeeper") == PositionGroup.GK
    assert map_position_to_group("D") == PositionGroup.DEF
    assert map_position_to_group("CB") == PositionGroup.DEF
    assert map_position_to_group("LB") == PositionGroup.DEF
    assert map_position_to_group("M") == PositionGroup.MID
    assert map_position_to_group("CM") == PositionGroup.MID
    assert map_position_to_group("DM") == PositionGroup.MID
    assert map_position_to_group("F") == PositionGroup.ATT
    assert map_position_to_group("ST") == PositionGroup.ATT
    assert map_position_to_group("LW") == PositionGroup.ATT
    assert map_position_to_group(None) == PositionGroup.MID


def test_role_feature_extraction_and_defaults():
    """Verifies features are extracted per position group and missing values fall back to defaults."""
    profiler = RoleProfiler()
    raw = {
        "passes_per_90_last_5": 55.4,
        "pass_accuracy_avg_last_5": 88.2,
        # missing passes_key_per_90_last_5
    }

    extracted = profiler.extract_role_features(raw, PositionGroup.MID)
    assert extracted["passes_per_90"] == 55.4
    assert extracted["pass_accuracy"] == 88.2
    assert "key_passes_per_90" in extracted
    assert extracted["key_passes_per_90"] == 0.0  # default value


def test_standardization_and_outlier_winsorization():
    """Verifies z-score standardization and robust clipping to [-3.0, 3.0]."""
    scaler_params = {
        "passes_per_90": {"mean": 45.0, "std": 10.0},
    }
    profiler = RoleProfiler(scaler_params=scaler_params)

    # Average
    assert profiler.standardize({"passes_per_90": 45.0})["passes_per_90"] == 0.0

    # +1 std
    assert profiler.standardize({"passes_per_90": 55.0})["passes_per_90"] == 1.0

    # Outlier capping (+5 std -> +3.0)
    assert profiler.standardize({"passes_per_90": 95.0})["passes_per_90"] == 3.0

    # Negative outlier (-5 std -> -3.0)
    assert profiler.standardize({"passes_per_90": -10.0})["passes_per_90"] == -3.0


def test_dimensional_scoring_bounds():
    """Verifies continuous [0.0, 1.0] bounds across all 9 dimensions."""
    profiler = RoleProfiler()
    standardized = {
        "passes_per_90": 1.5,
        "pass_accuracy": 1.2,
        "key_passes_per_90": 2.0,
        "assists_per_90": 1.8,
        "tackles_per_90": -1.0,
        "fouls_committed": 0.5,
    }

    scores = profiler.compute_dimensional_scores(standardized, PositionGroup.MID)
    assert set(scores.keys()) == set(DIMENSIONS)

    for dim, score in scores.items():
        assert 0.0 <= score <= 1.0, f"Dimension {dim} score {score} out of bounds"

    # Outfield player goalkeeping should be 0.0
    assert scores["goalkeeping"] == 0.0
    # Progression and creation should be high (> 0.6)
    assert scores["progression"] > 0.60
    assert scores["creation"] > 0.60


def test_controlled_archetype_assignment_midfielders():
    """Verifies data-driven assignment to controlled archetypes for midfielders."""
    profiler = RoleProfiler()

    # 1. Playmaker / Creator Midfielder profile
    creator_scores = {
        "distribution": 0.75,
        "progression": 0.85,
        "creation": 0.90,
        "finishing": 0.40,
        "defending": 0.30,
        "duels": 0.40,
        "carrying": 0.70,
        "discipline": 0.50,
        "goalkeeping": 0.0,
    }
    primary, secondary, conf = profiler.assign_archetype(creator_scores, PositionGroup.MID)
    assert primary in {"Chance Creator", "Progressive Midfielder"}
    assert conf is not None and 0.50 <= conf <= 0.99

    # 2. Ball-Winning Midfielder profile
    destroyer_scores = {
        "distribution": 0.40,
        "progression": 0.35,
        "creation": 0.20,
        "finishing": 0.15,
        "defending": 0.92,
        "duels": 0.88,
        "carrying": 0.30,
        "discipline": 0.30,
        "goalkeeping": 0.0,
    }
    primary, secondary, conf = profiler.assign_archetype(destroyer_scores, PositionGroup.MID)
    assert primary == "Ball-Winning Midfielder"
    assert conf is not None and conf > 0.60


def test_sample_size_gate_logic():
    """Verifies that sample evidence gate cleanly filters unqualified players."""
    profiler = RoleProfiler(min_minutes=MINIMUM_MINUTES_THRESHOLD)

    # Under threshold (e.g. 90 minutes from 1 fixture)
    assert not profiler.is_sample_sufficient(sample_minutes=90, sample_matches=1)
    assert not profiler.is_sample_sufficient(sample_minutes=449, sample_matches=5)

    # Qualified threshold
    assert profiler.is_sample_sufficient(sample_minutes=450, sample_matches=5)
    assert profiler.is_sample_sufficient(sample_minutes=1200, sample_matches=14)


def test_clustering_dataset_size_gate():
    """Verifies that RoleDiscoveryEngine halts with InsufficientDatasetError when sample < 10."""
    engine = RoleDiscoveryEngine(min_population=10)
    small_pop = [{"passes_per_90": 1.0}] * 5

    with pytest.raises(InsufficientDatasetError) as exc_info:
        engine.evaluate_clustering(small_pop, PositionGroup.MID)

    assert "INSUFFICIENT_DATASET" in str(exc_info.value)


def test_clustering_evaluation_and_stability_on_synthetic_population():
    """Verifies KMeans discovery, silhouette evaluation, and stability test on a controlled benchmark population."""
    engine = RoleDiscoveryEngine(min_population=10, random_state=42)

    # 24 synthetic players: 12 deep distributors, 12 ball winners with natural spread
    population = []
    for i in range(12):
        population.append({
            "passes_per_90": 2.0 + i * 0.05,
            "pass_accuracy": 1.5 + i * 0.03,
            "tackles_per_90": -1.0 - i * 0.02,
            "duels_won": -0.8 - i * 0.02,
        })
    for i in range(12):
        population.append({
            "passes_per_90": -1.5 - i * 0.04,
            "pass_accuracy": -0.8 - i * 0.02,
            "tackles_per_90": 2.0 + i * 0.05,
            "duels_won": 1.8 + i * 0.04,
        })

    result = engine.evaluate_clustering(population, PositionGroup.MID, k_range=[2, 3])
    assert result["population_size"] == 24
    assert result["selected_k"] == 2
    assert result["silhouette_score"] > 0.60
    assert result["stability_score_ari"] == 1.0  # Perfectly stable cluster separation
    assert len(result["clusters"]) == 2


def test_multi_dimensional_similarity_and_explanations():
    """Verifies component similarity calculations and natural explainability generation."""
    engine = PlayerSimilarityEngine(w_statistical=0.50, w_role=0.35, w_contextual=0.15)

    vec_a = {"passes_per_90": 1.5, "pass_accuracy": 1.2, "tackles_per_90": 0.0}
    vec_b = {"passes_per_90": 1.4, "pass_accuracy": 1.1, "tackles_per_90": 0.1}
    vec_c = {"passes_per_90": -1.5, "pass_accuracy": -1.2, "tackles_per_90": 2.5}

    # Cosine statistical similarity
    stat_ab = engine.compute_statistical_similarity(vec_a, vec_b)
    stat_ac = engine.compute_statistical_similarity(vec_a, vec_c)
    assert stat_ab > 0.95
    assert stat_ac < 0.20

    # Role similarity
    scores_a = {"distribution": 0.82, "progression": 0.75, "creation": 0.70, "defending": 0.35}
    scores_b = {"distribution": 0.80, "progression": 0.73, "creation": 0.68, "defending": 0.38}
    scores_c = {"distribution": 0.30, "progression": 0.25, "creation": 0.20, "defending": 0.88}

    role_ab = engine.compute_role_similarity(scores_a, scores_b)
    role_ac = engine.compute_role_similarity(scores_a, scores_c)
    assert role_ab > 0.90
    assert role_ac < 0.70

    # Contextual similarity
    context_ab = engine.compute_contextual_similarity("MID", "MID", 900, 850)
    context_ac = engine.compute_contextual_similarity("MID", "DEF", 900, 90)
    assert context_ab > 0.95
    assert context_ac < 0.50

    # Overall similarity
    overall_ab = engine.compute_overall_similarity(stat_ab, role_ab, context_ab)
    overall_ac = engine.compute_overall_similarity(stat_ac, role_ac, context_ac)
    assert overall_ab > 0.90
    assert overall_ac < 0.45

    # Explainability
    exp = engine.generate_explanations(scores_a, scores_b, vec_a, vec_b, "Player A", "Player B")
    assert len(exp["why_similar"]) > 0
    assert any("distribution" in s or "progression" in s for s in exp["why_similar"])

    diff_exp = engine.generate_explanations(scores_a, scores_c, vec_a, vec_c, "Player A", "Player C")
    assert len(diff_exp["why_different"]) > 0
    assert any("defending" in s or "distribution" in s for s in diff_exp["why_different"])
