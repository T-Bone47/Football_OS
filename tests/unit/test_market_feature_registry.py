"""Unit tests for Market and Valuation Feature Registry Integration (Phase 4.1P).
"""
import pytest

from app.features.registry import FEATURE_REGISTRY


VALUATION_FEATURE_NAMES = [
    "market_comparable_median_fee",
    "market_comparable_count",
    "market_fee_iqr",
    "market_age_at_evaluation",
    "market_age_curve_factor",
    "market_valuation_baseline",
]


def test_valuation_features_registered():
    """All Phase 4.1 valuation and market features must be registered in FEATURE_REGISTRY."""
    registry_map = {f.name: f for f in FEATURE_REGISTRY.values()}
    for name in VALUATION_FEATURE_NAMES:
        assert name in registry_map, f"Feature {name} is missing from FEATURE_REGISTRY"
        feat = registry_map[name]
        assert feat.entity_type == "player"
        assert feat.version == "1.0.0"
        assert feat.feature_set == "market_valuation_v1"
        assert feat.leakage_policy == "pre-match-strict"
        assert feat.description is not None and len(feat.description) > 0
        assert feat.source == "transfer_market_intelligence"
