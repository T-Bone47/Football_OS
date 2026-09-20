"""Unit tests for Tactical Fit Engine (Phase 2 Slice 3).
Tests tactical contexts, requirements, component scoring, dimensional penalties,
style alignment, evidence-based confidence, and explainability.
"""
from __future__ import annotations

import pytest
from app.roles.registry import PositionGroup
from app.tactical.calculator import TacticalFitCalculator
from app.tactical.contexts import (
    STANDARD_TACTICAL_CONTEXTS,
    TacticalContext,
    TacticalRequirement,
    build_custom_context,
    get_standard_context,
)
from app.tactical.explain import generate_tactical_explanations


def test_tactical_context_catalog():
    """Verifies pre-configured catalog contains valid tactical contexts with normalized weights."""
    assert len(STANDARD_TACTICAL_CONTEXTS) >= 10

    for ctx_id, ctx in STANDARD_TACTICAL_CONTEXTS.items():
        assert ctx.context_id == ctx_id
        assert ctx.formation in {"4-3-3", "4-2-3-1", "4-4-2", "3-5-2", "3-4-3"}
        assert ctx.position_group in PositionGroup
        assert len(ctx.requirements) >= 2

        # Check weights sum close to 1.0
        total_w = sum(r.importance_weight for r in ctx.requirements)
        assert 0.95 <= total_w <= 1.05


def test_build_custom_context():
    """Verifies dynamic tactical context generation from controlled archetype weights."""
    custom = build_custom_context(
        formation="4-3-3",
        target_position="CM",
        target_role="Progressive Midfielder",
        possession_style="HIGH_POSSESSION",
    )
    assert custom.position_group == PositionGroup.MID
    assert custom.target_role == "Progressive Midfielder"
    assert any(r.dimension == "progression" for r in custom.requirements)
    assert custom.possession_style == "HIGH_POSSESSION"


def test_position_fit_scoring():
    """Verifies positional compatibility formula across exact, group, adjacent, and divergent pairs."""
    calc = TacticalFitCalculator()

    # Exact match: 1.0
    assert calc.calculate_position_fit("DM", PositionGroup.MID, "DM", PositionGroup.MID) == 1.0

    # Same group (CM playing DM): 0.85
    assert calc.calculate_position_fit("CM", PositionGroup.MID, "DM", PositionGroup.MID) == 0.85

    # Adjacent group (MID playing ATT): 0.40
    assert calc.calculate_position_fit("M", PositionGroup.MID, "RW", PositionGroup.ATT) == 0.40

    # Completely divergent (GK playing ST): 0.05
    assert calc.calculate_position_fit("GK", PositionGroup.GK, "ST", PositionGroup.ATT) == 0.05

    # Missing position: 0.0
    assert calc.calculate_position_fit(None, PositionGroup.MID, "CM", PositionGroup.MID) == 0.0


def test_role_fit_scoring():
    """Verifies role archetype matching and functional projection."""
    calc = TacticalFitCalculator()
    profile_scores = {"distribution": 0.85, "progression": 0.75, "defending": 0.60}

    # Exact primary match: 1.0
    assert calc.calculate_role_fit("Deep Distributor", None, "Deep Distributor", profile_scores, PositionGroup.MID) == 1.0

    # Exact secondary match: 0.80
    assert calc.calculate_role_fit("Box-to-Box Midfielder", "Deep Distributor", "Deep Distributor", profile_scores, PositionGroup.MID) == 0.80

    # Functional projection on matching weights
    role_fit = calc.calculate_role_fit("Box-to-Box Midfielder", None, "Deep Distributor", profile_scores, PositionGroup.MID)
    assert 0.60 <= role_fit <= 0.90


def test_dimensional_fit_formula_and_threshold_penalties():
    """Verifies 1 - |player - required| formula and penalty when falling below minimum threshold."""
    calc = TacticalFitCalculator()

    reqs = [
        # Player has 0.80, required is 0.80 -> base_fit = 1.0
        TacticalRequirement("distribution", required_strength=0.80, importance_weight=0.50, minimum_threshold=0.60),
        # Player has 0.35, required is 0.70 -> base_fit = 0.65, below min 0.50 -> penalty applied
        TacticalRequirement("defending", required_strength=0.70, importance_weight=0.50, minimum_threshold=0.50),
    ]

    scores = {"distribution": 0.80, "defending": 0.35}
    dim_fit, breakdown = calc.calculate_dimensional_fit(scores, reqs)

    assert breakdown["distribution"]["fit_score"] == 1.0
    assert breakdown["distribution"]["deficit"] == 0.0

    # Defending base_fit is 1.0 - (0.70 - 0.35) = 0.65. Deficit = 0.15. Penalty = (0.15/0.50)*0.5 = 0.15. Fit = 0.50
    assert breakdown["defending"]["deficit"] == 0.15
    assert breakdown["defending"]["fit_score"] == 0.50

    # Weighted dim_fit = (1.0 * 0.5 + 0.50 * 0.5) / 1.0 = 0.75
    assert dim_fit == 0.75


def test_style_fit_scoring():
    """Verifies style fit evaluation for possession and pressing setups."""
    calc = TacticalFitCalculator()
    context = get_standard_context("433_dm_deep_distributor")

    scores = {"distribution": 0.85, "carrying": 0.70, "defending": 0.60}
    style_fit = calc.calculate_style_fit(scores, context)
    assert style_fit is not None
    assert style_fit > 0.70

    # Without style requirements
    plain_context = TacticalContext(
        context_id="plain",
        formation="4-3-3",
        target_position="CM",
        position_group=PositionGroup.MID,
        target_role="Deep Distributor",
    )
    assert calc.calculate_style_fit(scores, plain_context) is None


def test_composite_fit_calculation():
    """Verifies composite weighting normalization."""
    calc = TacticalFitCalculator()
    fit = calc.calculate_composite_fit(
        position_fit=1.0,
        role_fit=1.0,
        dimension_fit=0.80,
        style_fit=0.75,
        contextual_fit=1.0,
    )
    assert 0.85 <= fit <= 0.95

    # Weight redistribution when style and context are None
    fit_partial = calc.calculate_composite_fit(
        position_fit=1.0,
        role_fit=0.80,
        dimension_fit=0.80,
        style_fit=None,
        contextual_fit=None,
    )
    assert 0.80 <= fit_partial <= 0.90


def test_confidence_and_sample_gate_enforcement():
    """Verifies that players below 450 minutes receive INSUFFICIENT_DATA."""
    calc = TacticalFitCalculator()

    # Under threshold: 90 minutes (e.g. single fixture)
    conf, status = calc.evaluate_confidence_and_status(
        sample_minutes=90,
        sample_matches=1,
        role_status="INSUFFICIENT_SAMPLE",
        composite_fit=0.92,  # Even if numerical match is high, status must be gated!
    )
    assert conf == "INSUFFICIENT_DATA"
    assert status == "INSUFFICIENT_DATA"

    # Qualified: 500 minutes, 6 matches
    conf_med, status_med = calc.evaluate_confidence_and_status(
        sample_minutes=500,
        sample_matches=6,
        role_status="QUALIFIED",
        composite_fit=0.82,
    )
    assert conf_med == "MEDIUM"
    assert status_med == "FIT"

    # High sample: 1200 minutes, 14 matches
    conf_hi, status_hi = calc.evaluate_confidence_and_status(
        sample_minutes=1200,
        sample_matches=14,
        role_status="QUALIFIED",
        composite_fit=0.82,
    )
    assert conf_hi == "HIGH"
    assert status_hi == "FIT"


def test_explainability_generation():
    """Verifies explainability engine outputs grounded rationales."""
    context = get_standard_context("433_dm_deep_distributor")
    breakdown = {
        "distribution": {"fit_score": 0.95, "player_score": 0.82, "required_strength": 0.80, "deficit": 0.0, "importance_weight": 0.35},
        "defending": {"fit_score": 0.40, "player_score": 0.30, "required_strength": 0.60, "deficit": 0.10, "minimum_threshold": 0.40, "importance_weight": 0.20},
    }

    exp = generate_tactical_explanations(
        player_name="Test Player",
        player_position="DM",
        position_fit=1.0,
        role_fit=0.90,
        dimension_breakdown=breakdown,
        style_fit=0.85,
        context=context,
        confidence="HIGH",
        sample_minutes=900,
    )

    assert any("distribution" in s.lower() for s in exp["why_fit"])
    assert any("defending" in s.lower() for s in exp["why_not_fit"])
    assert any("positional alignment" in s.lower() for s in exp["why_fit"])


def test_determinism():
    """Verifies that identical inputs produce 100% bit-for-bit identical outputs."""
    calc = TacticalFitCalculator()
    results = [
        calc.calculate_composite_fit(0.85, 0.75, 0.80, 0.70, 0.60)
        for _ in range(10)
    ]
    assert len(set(results)) == 1
