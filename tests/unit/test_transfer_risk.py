"""Unit tests for Transfer Risk Classification Engine (Phase 5B.3)."""
import pytest
from app.market.risk import TransferRiskEngine


class TestRiskLevelClassification:
    """Tests for the numeric-to-categorical risk level mapping."""

    def test_critical_risk(self):
        """Score >= 0.75 should be CRITICAL."""
        assert TransferRiskEngine.classify_risk_level(0.80) == "CRITICAL"
        assert TransferRiskEngine.classify_risk_level(0.75) == "CRITICAL"
        assert TransferRiskEngine.classify_risk_level(1.0) == "CRITICAL"

    def test_high_risk(self):
        """Score in [0.55, 0.75) should be HIGH."""
        assert TransferRiskEngine.classify_risk_level(0.60) == "HIGH"
        assert TransferRiskEngine.classify_risk_level(0.55) == "HIGH"
        assert TransferRiskEngine.classify_risk_level(0.74) == "HIGH"

    def test_medium_risk(self):
        """Score in [0.30, 0.55) should be MEDIUM."""
        assert TransferRiskEngine.classify_risk_level(0.40) == "MEDIUM"
        assert TransferRiskEngine.classify_risk_level(0.30) == "MEDIUM"
        assert TransferRiskEngine.classify_risk_level(0.54) == "MEDIUM"

    def test_low_risk(self):
        """Score in [0, 0.30) should be LOW."""
        assert TransferRiskEngine.classify_risk_level(0.10) == "LOW"
        assert TransferRiskEngine.classify_risk_level(0.0) == "LOW"
        assert TransferRiskEngine.classify_risk_level(0.29) == "LOW"


class TestPerformanceRisk:
    """Tests for performance risk dimension assessment."""

    def setup_method(self):
        self.engine = TransferRiskEngine()

    def test_low_sample_increases_risk(self):
        """Limited minutes should increase performance risk."""

        class MockContext:
            sample_minutes = 300
            sample_matches = 5
            age_at_as_of = 25.0
            dimension_scores = {}

        dim = self.engine.evaluate_performance_risk(MockContext(), [])
        assert dim.score > 0.50
        assert dim.dimension == "PERFORMANCE"
        assert any("Limited sample" in e for e in dim.evidence)

    def test_strong_sample_decreases_risk(self):
        """Many minutes should decrease performance risk."""

        class MockContext:
            sample_minutes = 3000
            sample_matches = 35
            age_at_as_of = 26.0
            dimension_scores = {}

        dim = self.engine.evaluate_performance_risk(MockContext(), [])
        assert dim.score < 0.60
        assert any("Strong sample" in e for e in dim.evidence)

    def test_old_age_increases_risk(self):
        """Age >= 31 should increase performance risk."""

        class MockContext:
            sample_minutes = 2000
            sample_matches = 25
            age_at_as_of = 33.0
            dimension_scores = {}

        dim = self.engine.evaluate_performance_risk(MockContext(), [])
        assert dim.score > 0.45
        assert any("decline" in e.lower() for e in dim.evidence)

    def test_prime_age_decreases_risk(self):
        """Prime age window should decrease risk."""

        class MockContext:
            sample_minutes = 2500
            sample_matches = 30
            age_at_as_of = 25.0
            dimension_scores = {}

        dim = self.engine.evaluate_performance_risk(MockContext(), [])
        assert dim.score < 0.55
        assert any("prime" in e.lower() for e in dim.evidence)


class TestAdaptationRisk:
    """Tests for adaptation risk dimension."""

    def setup_method(self):
        self.engine = TransferRiskEngine()

    def test_no_transfer_history(self):
        """No prior transfers should increase adaptation uncertainty."""

        class MockContext:
            age_at_as_of = 25.0

        dim = self.engine.evaluate_adaptation_risk(MockContext(), [])
        assert dim.score > 0.40
        assert any("No prior transfer" in e for e in dim.evidence)

    def test_moderate_transfer_history(self):
        """2-3 transfers should demonstrate some adaptability."""

        class MockContext:
            age_at_as_of = 25.0

        dim = self.engine.evaluate_adaptation_risk(MockContext(), [1, 2, 3])
        assert dim.score < 0.45
        assert any("demonstrated adaptability" in e for e in dim.evidence)


class TestFinancialRisk:
    """Tests for financial risk dimension."""

    def setup_method(self):
        self.engine = TransferRiskEngine()

    def test_high_value_increases_risk(self):
        """Very high estimated value should increase financial risk."""

        class MockContext:
            age_at_as_of = 27.0
            last_transfer_fee_eur = 30_000_000

        dim = self.engine.evaluate_financial_risk(MockContext(), 80_000_000)
        assert dim.score > 0.50
        assert any("significant financial exposure" in e.lower() for e in dim.evidence)

    def test_low_value_decreases_risk(self):
        """Low estimated value should decrease financial risk."""

        class MockContext:
            age_at_as_of = 22.0
            last_transfer_fee_eur = None

        dim = self.engine.evaluate_financial_risk(MockContext(), 5_000_000)
        assert dim.score < 0.50
        assert any("reduced financial risk" in e.lower() for e in dim.evidence)

    def test_no_value_data(self):
        """Missing estimated value should be flagged as unclear."""

        class MockContext:
            age_at_as_of = 25.0
            last_transfer_fee_eur = None

        dim = self.engine.evaluate_financial_risk(MockContext(), None)
        assert any("unavailable" in e.lower() for e in dim.evidence)


class TestAvailabilityRisk:
    """Tests for availability risk dimension."""

    def setup_method(self):
        self.engine = TransferRiskEngine()

    def test_no_season_stats(self):
        """No season stats should return INSUFFICIENT_DATA."""

        class MockContext:
            pass

        dim = self.engine.evaluate_availability_risk([], MockContext())
        assert dim.risk_level == "INSUFFICIENT_DATA"

    def test_high_availability(self):
        """Many appearances should indicate low availability risk."""

        class MockSeason:
            appearances = 35
            lineups = 30
            minutes = 3000
            rating = None

        dim = self.engine.evaluate_availability_risk([MockSeason(), MockSeason()], None)
        assert dim.score < 0.45
        assert any("Strong availability" in e for e in dim.evidence)

    def test_low_availability(self):
        """Few appearances should indicate high availability risk."""

        class MockSeason:
            appearances = 10
            lineups = 5
            minutes = 600
            rating = None

        dim = self.engine.evaluate_availability_risk([MockSeason()], None)
        assert dim.score > 0.40
        assert any("availability concern" in e.lower() for e in dim.evidence)
