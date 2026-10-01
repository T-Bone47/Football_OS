"""Unit tests for Market Opportunities Engine (Phase 5B.1)."""
import math
import pytest
from app.market.opportunities import MarketOpportunitiesEngine


class TestOpportunityClassification:
    """Tests for the deterministic opportunity classification logic."""

    def setup_method(self):
        self.engine = MarketOpportunitiesEngine()

    def test_undervalued_classification(self):
        """Negative gap exceeding threshold is classified as UNDERVALUED."""
        result = self.engine.classify_opportunity(-0.20)
        assert result == "UNDERVALUED"

    def test_undervalued_at_boundary(self):
        """Gap exactly at threshold is classified as UNDERVALUED."""
        result = self.engine.classify_opportunity(-0.15)
        assert result == "UNDERVALUED"

    def test_premium_classification(self):
        """Positive gap exceeding premium threshold is classified as PREMIUM."""
        result = self.engine.classify_opportunity(0.25)
        assert result == "PREMIUM"

    def test_premium_at_boundary(self):
        """Gap exactly at premium threshold is classified as PREMIUM."""
        result = self.engine.classify_opportunity(0.20)
        assert result == "PREMIUM"

    def test_fairly_valued_classification(self):
        """Gap within thresholds is classified as FAIRLY_VALUED."""
        result = self.engine.classify_opportunity(0.05)
        assert result == "FAIRLY_VALUED"

    def test_fairly_valued_negative_small(self):
        """Small negative gap within thresholds is FAIRLY_VALUED."""
        result = self.engine.classify_opportunity(-0.10)
        assert result == "FAIRLY_VALUED"

    def test_none_gap_returns_insufficient(self):
        """None gap returns INSUFFICIENT_DATA."""
        result = self.engine.classify_opportunity(None)
        assert result == "INSUFFICIENT_DATA"

    def test_zero_gap_is_fairly_valued(self):
        """Exact zero gap is FAIRLY_VALUED."""
        result = self.engine.classify_opportunity(0.0)
        assert result == "FAIRLY_VALUED"

    def test_thresholds_are_documented(self):
        """Thresholds must be explicitly accessible — no magic constants."""
        assert hasattr(MarketOpportunitiesEngine, 'UNDERVALUED_THRESHOLD')
        assert hasattr(MarketOpportunitiesEngine, 'PREMIUM_THRESHOLD')
        assert MarketOpportunitiesEngine.UNDERVALUED_THRESHOLD < 0
        assert MarketOpportunitiesEngine.PREMIUM_THRESHOLD > 0
