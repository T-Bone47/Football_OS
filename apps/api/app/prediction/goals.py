"""Pre-Match Expected Goals (xG) & Bivariate Scoreline Distribution Engine (Phase 6.10 & 6.11).

Methodology:
- Distinct Pre-Match Expected Goals: Pre-match Poisson intensity based on attack & defense parameters.
- Dixon-Coles Low-Score Adjustment: Corrects for independence violations in (0-0, 1-0, 0-1, 1-1).
- Truncated Joint Probability Matrix: Evaluated over scorelines [0..6] x [0..6] with strict normalization.
- Derived Markets: Over/Under 1.5, 2.5, Both Teams To Score (BTTS), and exact scoreline rankings.
"""
from __future__ import annotations

import math
from typing import Any

from app.prediction.schemas import ExpectedGoals, GoalDistribution, ScorelineProbability

LEAGUE_AVG_HOME_GOALS = 1.45
LEAGUE_AVG_AWAY_GOALS = 1.15
DIXON_COLES_RHO = -0.045  # Empirical low-scoring interdependence parameter
MAX_GOALS_CONSIDERED = 6


def poisson_pmf(k: int, lmbda: float) -> float:
    """Calculates Poisson probability mass P(X = k) with parameter lambda."""
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)


def dixon_coles_tau(x: int, y: int, lmbda: float, mu: float, rho: float = DIXON_COLES_RHO) -> float:
    """Applies Dixon & Coles (1997) bivariate correction factor for low-scoring dependency."""
    if x == 0 and y == 0:
        return max(0.0, 1.0 - lmbda * mu * rho)
    if x == 0 and y == 1:
        return max(0.0, 1.0 + lmbda * rho)
    if x == 1 and y == 0:
        return max(0.0, 1.0 + mu * rho)
    if x == 1 and y == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


class GoalPredictionEngine:
    """Estimates pre-match expected goals and generates coherent scoreline distributions."""

    def __init__(
        self,
        avg_home_goals: float = LEAGUE_AVG_HOME_GOALS,
        avg_away_goals: float = LEAGUE_AVG_AWAY_GOALS,
        rho: float = DIXON_COLES_RHO,
    ) -> None:
        self.avg_home_goals = avg_home_goals
        self.avg_away_goals = avg_away_goals
        self.rho = rho

    def compute_expected_goals(
        self,
        home_attack_strength: float = 1.0,
        home_defense_strength: float = 1.0,
        away_attack_strength: float = 1.0,
        away_defense_strength: float = 1.0,
    ) -> ExpectedGoals:
        """Estimates pre-match expected goals (lambda_H, mu_A) from relative attack/defense parameters."""
        # Clamp parameters to biologically plausible football ranges [0.4, 2.5]
        h_att = max(0.40, min(2.50, home_attack_strength))
        h_def = max(0.40, min(2.50, home_defense_strength))
        a_att = max(0.40, min(2.50, away_attack_strength))
        a_def = max(0.40, min(2.50, away_defense_strength))

        lambda_home = round(max(0.20, min(4.50, self.avg_home_goals * h_att * a_def)), 2)
        mu_away = round(max(0.20, min(4.50, self.avg_away_goals * a_att * h_def)), 2)
        total = round(lambda_home + mu_away, 2)

        return ExpectedGoals(home=lambda_home, away=mu_away, total=total)

    def generate_scoreline_distribution(
        self,
        expected_goals: ExpectedGoals,
        top_k: int = 8,
    ) -> GoalDistribution:
        """Computes bivariate Poisson scoreline grid and aggregates outcome probabilities."""
        lmbda = expected_goals.home
        mu = expected_goals.away

        raw_matrix: dict[tuple[int, int], float] = {}
        total_raw_prob = 0.0

        for h in range(MAX_GOALS_CONSIDERED + 1):
            p_h = poisson_pmf(h, lmbda)
            for a in range(MAX_GOALS_CONSIDERED + 1):
                p_a = poisson_pmf(a, mu)
                tau = dixon_coles_tau(h, a, lmbda, mu, self.rho)
                prob = p_h * p_a * tau
                raw_matrix[(h, a)] = prob
                total_raw_prob += prob

        # Normalize matrix to strictly sum to 1.0
        normalized_matrix: dict[tuple[int, int], float] = {
            k: (v / total_raw_prob) for k, v in raw_matrix.items()
        }

        # Derived market metrics
        over_1_5 = sum(p for (h, a), p in normalized_matrix.items() if (h + a) > 1)
        over_2_5 = sum(p for (h, a), p in normalized_matrix.items() if (h + a) > 2)
        under_2_5 = 1.0 - over_2_5
        btts = sum(p for (h, a), p in normalized_matrix.items() if h >= 1 and a >= 1)

        # Ranked scorelines
        sorted_scorelines = sorted(
            normalized_matrix.items(), key=lambda item: item[1], reverse=True
        )

        top_scorelines = [
            ScorelineProbability(
                score=f"{h}-{a}",
                home_goals=h,
                away_goals=a,
                probability=round(p, 4),
            )
            for (h, a), p in sorted_scorelines[:top_k]
        ]

        return GoalDistribution(
            expected_goals=expected_goals,
            top_scorelines=top_scorelines,
            over_1_5=round(over_1_5, 4),
            over_2_5=round(over_2_5, 4),
            under_2_5=round(under_2_5, 4),
            both_teams_to_score=round(btts, 4),
        )

    def scorelines_to_1x2(self, distribution: GoalDistribution) -> tuple[float, float, float]:
        """Aggregates scoreline probabilities into 1X2 outcome probabilities."""
        lmbda = distribution.expected_goals.home
        mu = distribution.expected_goals.away

        p_home = 0.0
        p_draw = 0.0
        p_away = 0.0
        total = 0.0

        for h in range(MAX_GOALS_CONSIDERED + 1):
            p_h = poisson_pmf(h, lmbda)
            for a in range(MAX_GOALS_CONSIDERED + 1):
                p_a = poisson_pmf(a, mu)
                tau = dixon_coles_tau(h, a, lmbda, mu, self.rho)
                cell_prob = p_h * p_a * tau
                total += cell_prob
                if h > a:
                    p_home += cell_prob
                elif h == a:
                    p_draw += cell_prob
                else:
                    p_away += cell_prob

        h_norm = round(p_home / total, 4)
        d_norm = round(p_draw / total, 4)
        a_norm = round(1.0 - h_norm - d_norm, 4)
        return h_norm, d_norm, a_norm
