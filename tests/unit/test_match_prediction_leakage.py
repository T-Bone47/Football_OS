"""Automated Leakage & Temporal Invariance Tests (Phase 6.16).

Verifies the non-negotiable principles:
1. Bit-for-bit feature vector invariance:
   Inserting future matches, future statistics, or future events does NOT alter historical
   prediction feature vectors.
2. Target Leakage Invariance:
   Mutating the outcome or score of the match itself does NOT alter the pre-match feature vector.
3. Strict cutoff enforcement:
   Every feature uses ONLY matches strictly preceding kickoff (date < cutoff).
"""
from datetime import datetime, timedelta, timezone
import uuid
import pytest

from app.prediction.features import PreMatchFeatureBuilder


class TestMatchPredictionLeakage:
    """Rigorous temporal leakage verification tests."""

    def setup_method(self):
        self.builder = PreMatchFeatureBuilder()
        self.home_id = uuid.uuid4()
        self.away_id = uuid.uuid4()
        self.match_id = uuid.uuid4()
        self.kickoff = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)

        # Baseline historical matches strictly prior to kickoff
        self.base_history = [
            {
                "id": uuid.uuid4(),
                "home_club_id": self.home_id,
                "away_club_id": uuid.uuid4(),
                "home_score": 2,
                "away_score": 0,
                "date": self.kickoff - timedelta(days=14),
                "status": "FT",
            },
            {
                "id": uuid.uuid4(),
                "home_club_id": uuid.uuid4(),
                "away_club_id": self.home_id,
                "home_score": 1,
                "away_score": 1,
                "date": self.kickoff - timedelta(days=7),
                "status": "FT",
            },
            {
                "id": uuid.uuid4(),
                "home_club_id": self.away_id,
                "away_club_id": uuid.uuid4(),
                "home_score": 3,
                "away_score": 1,
                "date": self.kickoff - timedelta(days=10),
                "status": "FT",
            },
            {
                "id": uuid.uuid4(),
                "home_club_id": uuid.uuid4(),
                "away_club_id": self.away_id,
                "home_score": 0,
                "away_score": 2,
                "date": self.kickoff - timedelta(days=5),
                "status": "FT",
            },
        ]

    def test_future_match_injection_preserves_bit_for_bit_invariance(self):
        """Historical pre-match features must be bit-for-bit IDENTICAL after injecting future matches."""
        # 1. Feature snapshot before future injection
        snapshot_before = self.builder.build_features(
            match_id=self.match_id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            kickoff_time=self.kickoff,
            historical_matches=self.base_history,
        )

        # 2. Inject future matches occurring 1 day and 7 days after kickoff
        future_history = list(self.base_history) + [
            {
                "id": uuid.uuid4(),
                "home_club_id": self.home_id,
                "away_club_id": self.away_id,
                "home_score": 9,
                "away_score": 0,
                "date": self.kickoff + timedelta(days=1),
                "status": "FT",
            },
            {
                "id": uuid.uuid4(),
                "home_club_id": self.away_id,
                "away_club_id": uuid.uuid4(),
                "home_score": 5,
                "away_score": 0,
                "date": self.kickoff + timedelta(days=7),
                "status": "FT",
            },
        ]

        # 3. Feature snapshot after future injection
        snapshot_after = self.builder.build_features(
            match_id=self.match_id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            kickoff_time=self.kickoff,
            historical_matches=future_history,
        )

        # 4. Bit-for-bit assertion: every single feature must be identical
        assert snapshot_before.features == snapshot_after.features
        assert snapshot_before.home_sample_size == snapshot_after.home_sample_size
        assert snapshot_before.away_sample_size == snapshot_after.away_sample_size
        assert snapshot_before.data_status == snapshot_after.data_status

    def test_mutating_target_match_outcome_does_not_leak_into_features(self):
        """Pre-match features must NOT change if the current match is modified or injected with a result."""
        # Baseline snapshot when current match is absent from history
        snapshot_baseline = self.builder.build_features(
            match_id=self.match_id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            kickoff_time=self.kickoff,
            historical_matches=self.base_history,
        )

        # Current match included in match list with a blowout home win result (7-0)
        history_with_current_match_won = list(self.base_history) + [
            {
                "id": self.match_id,
                "home_club_id": self.home_id,
                "away_club_id": self.away_id,
                "home_score": 7,
                "away_score": 0,
                "date": self.kickoff,
                "status": "FT",
            }
        ]

        snapshot_won = self.builder.build_features(
            match_id=self.match_id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            kickoff_time=self.kickoff,
            historical_matches=history_with_current_match_won,
        )

        # Current match included in match list with a blowout away win result (0-8)
        history_with_current_match_lost = list(self.base_history) + [
            {
                "id": self.match_id,
                "home_club_id": self.home_id,
                "away_club_id": self.away_id,
                "home_score": 0,
                "away_score": 8,
                "date": self.kickoff,
                "status": "FT",
            }
        ]

        snapshot_lost = self.builder.build_features(
            match_id=self.match_id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            kickoff_time=self.kickoff,
            historical_matches=history_with_current_match_lost,
        )

        # Target outcome must NEVER alter pre-match features
        assert snapshot_baseline.features == snapshot_won.features
        assert snapshot_baseline.features == snapshot_lost.features
        assert snapshot_won.features == snapshot_lost.features

    def test_as_of_historical_rollback(self):
        """Setting as_of to an earlier date strictly prunes matches occurring between as_of and kickoff."""
        t_as_of = self.kickoff - timedelta(days=8)

        snapshot_full = self.builder.build_features(
            match_id=self.match_id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            kickoff_time=self.kickoff,
            historical_matches=self.base_history,
            as_of=self.kickoff,
        )

        snapshot_early = self.builder.build_features(
            match_id=self.match_id,
            home_club_id=self.home_id,
            away_club_id=self.away_id,
            kickoff_time=self.kickoff,
            historical_matches=self.base_history,
            as_of=t_as_of,
        )

        # The early snapshot should not include matches from days 7 and 5 before kickoff
        assert snapshot_early.home_sample_size == 1  # Only day 14 match
        assert snapshot_early.away_sample_size == 1  # Only day 10 match
        assert snapshot_full.home_sample_size == 2
        assert snapshot_full.away_sample_size == 2
