"""Unit tests for Replacement Finder Engine (Phase 5B.2)."""
import math
import pytest
from app.market.replacements import ReplacementFinderEngine


class TestRoleFit:
    """Tests for the role fit scoring component."""

    def test_exact_position_and_role_match(self):
        """Perfect match on both position and role should score highest."""
        score = ReplacementFinderEngine.compute_role_fit(
            "deep_playmaker", "deep_playmaker", "MID", "MID"
        )
        assert score == 1.0

    def test_same_position_different_role(self):
        """Same position but different role archetype."""
        score = ReplacementFinderEngine.compute_role_fit(
            "deep_playmaker", "box_to_box", "MID", "MID"
        )
        assert 0.40 < score < 0.80

    def test_different_position_same_role(self):
        """Different positions but same role archetype yields mid-range fit."""
        score = ReplacementFinderEngine.compute_role_fit(
            "deep_playmaker", "deep_playmaker", "MID", "DEF"
        )
        assert 0.50 < score < 1.0

    def test_partial_role_prefix_match(self):
        """Partial archetype prefix match (e.g. deep_playmaker vs deep_distributor)."""
        score = ReplacementFinderEngine.compute_role_fit(
            "deep_playmaker", "deep_distributor", "MID", "MID"
        )
        assert 0.55 < score < 0.95

    def test_no_role_data(self):
        """Missing role data should return a neutral mid-range score."""
        score = ReplacementFinderEngine.compute_role_fit(None, None, "MID", "MID")
        assert 0.40 <= score <= 0.80

    def test_no_position_data(self):
        """Missing position data returns a baseline score."""
        score = ReplacementFinderEngine.compute_role_fit("box_to_box", "box_to_box", None, None)
        assert 0.70 <= score <= 1.0

    def test_score_bounded(self):
        """Score must always be in [0, 1]."""
        for target_role, cand_role, target_pos, cand_pos in [
            ("deep_playmaker", "target_forward", "MID", "ATT"),
            (None, None, None, None),
            ("sweeper_keeper", "sweeper_keeper", "GK", "GK"),
        ]:
            score = ReplacementFinderEngine.compute_role_fit(target_role, cand_role, target_pos, cand_pos)
            assert 0.0 <= score <= 1.0


class TestAgeFit:
    """Tests for the age fit scoring component."""

    def test_exact_age_match(self):
        """Same target and candidate age yields perfect score."""
        score = ReplacementFinderEngine.compute_age_fit(25.0, 25.0)
        assert score >= 0.95

    def test_large_age_difference(self):
        """Large age diff significantly reduces fit."""
        score = ReplacementFinderEngine.compute_age_fit(25.0, 35.0)
        assert score < 0.40

    def test_max_age_gate(self):
        """Candidate above max_age should be hard-rejected (0.0)."""
        score = ReplacementFinderEngine.compute_age_fit(25.0, 31.0, max_age=30.0)
        assert score == 0.0

    def test_below_max_age(self):
        """Candidate within max_age should pass."""
        score = ReplacementFinderEngine.compute_age_fit(25.0, 28.0, max_age=30.0)
        assert score > 0.0

    def test_no_target_age_prime_window(self):
        """No target age, candidate in prime window (22-28) yields high score."""
        score = ReplacementFinderEngine.compute_age_fit(None, 25.0)
        assert score >= 0.85

    def test_no_target_age_old_candidate(self):
        """No target age, older candidate yields lower score."""
        score = ReplacementFinderEngine.compute_age_fit(None, 33.0)
        assert score < 0.50

    def test_none_candidate_age(self):
        """None candidate age returns neutral score."""
        score = ReplacementFinderEngine.compute_age_fit(25.0, None)
        assert score == 0.50


class TestValueFit:
    """Tests for the value fit scoring component."""

    def test_within_budget(self):
        """Value below max yields positive fit."""
        score = ReplacementFinderEngine.compute_value_fit(20_000_000, max_value_eur=30_000_000)
        assert score > 0.60

    def test_over_budget(self):
        """Value above max penalizes fit."""
        score = ReplacementFinderEngine.compute_value_fit(50_000_000, max_value_eur=30_000_000)
        assert score < 0.80

    def test_no_value_data(self):
        """Missing value data returns neutral score."""
        score = ReplacementFinderEngine.compute_value_fit(None)
        assert score == 0.50

    def test_no_budget(self):
        """No budget constraint returns moderate score."""
        score = ReplacementFinderEngine.compute_value_fit(20_000_000)
        assert score == 0.65

    def test_score_bounded(self):
        """Score must always be in [0, 1]."""
        for val, max_val in [
            (0, 100_000_000),
            (100_000_000, 10_000_000),
            (None, None),
        ]:
            score = ReplacementFinderEngine.compute_value_fit(val, max_val)
            assert 0.0 <= score <= 1.0


class TestCompositeWeights:
    """Tests that composite weights are valid."""

    def test_weights_sum_to_one(self):
        """Composite weights must sum to exactly 1.0."""
        total = (
            ReplacementFinderEngine.WEIGHT_ROLE
            + ReplacementFinderEngine.WEIGHT_AGE
            + ReplacementFinderEngine.WEIGHT_VALUE
        )
        assert abs(total - 1.0) < 1e-6

    def test_role_has_highest_weight(self):
        """Role fit should have the highest weight since it's most important for replacements."""
        assert ReplacementFinderEngine.WEIGHT_ROLE >= ReplacementFinderEngine.WEIGHT_AGE
        assert ReplacementFinderEngine.WEIGHT_ROLE >= ReplacementFinderEngine.WEIGHT_VALUE
