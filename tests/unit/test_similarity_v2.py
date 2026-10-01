"""Unit tests for Phase 3.2H: Similarity Engine V2 with explicit multi-mode support."""
from __future__ import annotations

import pytest

from app.roles.similarity import PlayerSimilarityEngine


def test_contribution_similarity_identical():
    """Identical contribution profiles yield similarity score of 1.0."""
    engine = PlayerSimilarityEngine()
    profile = {
        "passing": {"score": 0.8},
        "creation": {"score": 0.7},
        "finishing": {"score": 0.4},
        "defending": {"score": 0.6},
        "duels": {"score": 0.5},
        "retention": {"score": 0.75},
        "goalkeeping": {"score": 0.0},
    }

    sim = engine.compute_contribution_similarity(profile, profile)
    assert sim == 1.0


def test_contribution_similarity_orthogonal():
    """Polar opposite profiles yield a low similarity score."""
    engine = PlayerSimilarityEngine()
    profile_a = {
        "passing": {"score": 1.0},
        "creation": {"score": 1.0},
        "finishing": {"score": 1.0},
        "defending": {"score": 0.0},
        "duels": {"score": 0.0},
        "retention": {"score": 1.0},
        "goalkeeping": {"score": 0.0},
    }
    profile_b = {
        "passing": {"score": 0.0},
        "creation": {"score": 0.0},
        "finishing": {"score": 0.0},
        "defending": {"score": 1.0},
        "duels": {"score": 1.0},
        "retention": {"score": 0.0},
        "goalkeeping": {"score": 1.0},
    }

    sim = engine.compute_contribution_similarity(profile_a, profile_b)
    assert 0.0 <= sim < 0.25


def test_similarity_modes():
    """Validates different explicit similarity modes: composite, contribution, role, tactical, replacement."""
    engine = PlayerSimilarityEngine()
    stat_sim = 0.80
    role_sim = 0.90
    context_sim = 0.70
    contrib_sim = 0.85

    # 1. Mode: contribution
    assert engine.compute_overall_similarity(stat_sim, role_sim, context_sim, contrib_sim, mode="contribution") == 0.85

    # 2. Mode: role
    assert engine.compute_overall_similarity(stat_sim, role_sim, context_sim, contrib_sim, mode="role") == 0.90

    # 3. Mode: tactical (0.60 * role + 0.40 * stat)
    expected_tactical = round(0.60 * 0.90 + 0.40 * 0.80, 4)
    assert engine.compute_overall_similarity(stat_sim, role_sim, context_sim, contrib_sim, mode="tactical") == expected_tactical

    # 4. Mode: replacement (0.40 * role + 0.40 * contrib + 0.20 * context)
    expected_rep = round(0.40 * 0.90 + 0.40 * 0.85 + 0.20 * 0.70, 4)
    assert engine.compute_overall_similarity(stat_sim, role_sim, context_sim, contrib_sim, mode="replacement") == expected_rep

    # 5. Mode: composite (default, backward-compatible)
    comp = engine.compute_overall_similarity(stat_sim, role_sim, context_sim, contrib_sim, mode="composite")
    assert 0.0 <= comp <= 1.0
