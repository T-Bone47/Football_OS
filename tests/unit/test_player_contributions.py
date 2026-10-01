"""Unit tests for Player Contribution Engine and Confidence Gates (Phase 3.1E/F/G/H)."""
from dataclasses import dataclass
from app.contributions.calculator import compute_player_contribution_metrics, determine_confidence


@dataclass
class MockPlayerMatchStats:
    minutes: int
    goals: int = 0
    assists: int = 0
    shots_total: int = 0
    shots_on_target: int = 0
    passes_total: int = 0
    passes_key: int = 0
    pass_accuracy: float | None = None
    tackles_total: int = 0
    interceptions: int = 0
    blocks: int = 0
    duels_total: int = 0
    duels_won: int = 0
    dribbles_attempts: int = 0
    dribbles_success: int = 0
    fouls_committed: int = 0
    fouls_drawn: int = 0
    saves: int = 0
    goals_conceded: int = 0


def test_confidence_gates():
    # 0 mins -> INSUFFICIENT_DATA
    c, s = determine_confidence(0, 0)
    assert c == "INSUFFICIENT_DATA"
    assert s == "INSUFFICIENT_DATA"

    # < 270 mins -> INSUFFICIENT_SAMPLE
    c, s = determine_confidence(180, 2)
    assert c == "INSUFFICIENT_SAMPLE"
    assert s == "INSUFFICIENT_SAMPLE"

    # 270 - 599 mins -> LOW
    c, s = determine_confidence(450, 5)
    assert c == "LOW"
    assert s == "EVALUATED"

    # 600 - 899 mins -> MEDIUM
    c, s = determine_confidence(720, 8)
    assert c == "MEDIUM"
    assert s == "EVALUATED"

    # >= 900 mins -> HIGH
    c, s = determine_confidence(1080, 12)
    assert c == "HIGH"
    assert s == "EVALUATED"


def test_insufficient_sample_preserves_none_scores():
    stats = [MockPlayerMatchStats(minutes=90, goals=1)]
    result = compute_player_contribution_metrics(stats, "ATT")
    assert result["contribution_status"] == "INSUFFICIENT_SAMPLE"
    assert result["confidence"] == "INSUFFICIENT_SAMPLE"
    # Dimension scores must remain None without fabricating values
    for dim in result["dimensions"].values():
        assert dim.score is None
        assert dim.percentile is None


def test_evaluated_contribution_profile_midfielder():
    # 10 matches of 90 mins = 900 mins -> HIGH confidence
    stats = [
        MockPlayerMatchStats(
            minutes=90,
            passes_total=60,
            pass_accuracy=85.0,
            passes_key=2,
            tackles_total=3,
            interceptions=2,
            duels_total=8,
            duels_won=5,
            dribbles_attempts=2,
            dribbles_success=2,
        )
        for _ in range(10)
    ]

    result = compute_player_contribution_metrics(stats, "MID")
    assert result["confidence"] == "HIGH"
    assert result["contribution_status"] == "EVALUATED"
    assert result["sample_minutes"] == 900
    assert result["sample_matches"] == 10

    dims = result["dimensions"]
    assert dims["passing"].score is not None
    assert dims["passing"].score > 0.6
    assert dims["creation"].score is not None
    assert dims["defending"].score is not None
    assert dims["duels"].score is not None

    # Verify explainable strengths
    assert len(result["strengths"]) > 0
