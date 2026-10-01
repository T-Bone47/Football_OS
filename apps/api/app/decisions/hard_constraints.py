"""Hard Constraints Engine (Phase 7.4).

Guarantees:
- Hard constraints (position, budget ceiling, age window, minutes floor, risk tolerance)
  are strictly evaluated BEFORE soft evidence.
- Soft scores are NEVER permitted to override hard exclusions.
- Excluded candidates retain explicit, truthful exclusion reasons.
"""
from __future__ import annotations

from typing import Any
from app.decisions.schemas import HardConstraintResult
from app.roles.registry import map_position_to_group


class HardConstraintsEngine:
    """Enforces non-negotiable boundaries for player recruitment and transfers."""

    @classmethod
    def evaluate(
        cls,
        candidate_position: str,
        target_position: str,
        age: float | None,
        min_age: float | None,
        max_age: float | None,
        minutes_played: int,
        min_minutes: int | None,
        estimated_value_eur: float,
        budget_eur: float | None,
        risk_level: str,
        risk_tolerance: str = "MEDIUM",
    ) -> HardConstraintResult:
        """Evaluates whether candidate strictly meets all hard parameters."""
        checks: dict[str, bool] = {}
        exclusion_reasons: list[str] = []

        # 1. Positional Constraint
        cand_group = map_position_to_group(candidate_position)
        target_group = map_position_to_group(target_position)
        pos_match = (
            candidate_position.upper() == target_position.upper()
            or cand_group == target_group
        )
        checks["position_match"] = pos_match
        if not pos_match:
            exclusion_reasons.append(
                f"Position mismatch: candidate plays {candidate_position} ({cand_group.name if hasattr(cand_group, 'name') else cand_group}), "
                f"which does not fulfill required {target_position} slot."
            )

        # 2. Age Window Constraint
        age_passed = True
        if age is not None:
            if min_age is not None and age < min_age:
                age_passed = False
                exclusion_reasons.append(f"Age {age:.1f} is below minimum age boundary ({min_age:.0f}).")
            if max_age is not None and age > max_age:
                age_passed = False
                exclusion_reasons.append(f"Age {age:.1f} exceeds maximum age boundary ({max_age:.0f}).")
        checks["age_window"] = age_passed

        # 3. Minutes Sample Floor
        min_passed = True
        if min_minutes is not None and minutes_played < min_minutes:
            min_passed = False
            exclusion_reasons.append(
                f"Sample insufficiency: {minutes_played} minutes played is below required minimum threshold ({min_minutes} mins)."
            )
        checks["minutes_floor"] = min_passed

        # 4. Budget Ceiling (Allows up to 10% stretch for hard ceiling)
        budget_passed = True
        if budget_eur is not None and budget_eur > 0:
            hard_ceiling = budget_eur * 1.10
            if estimated_value_eur > hard_ceiling:
                budget_passed = False
                exclusion_reasons.append(
                    f"Financial ceiling exceeded: estimated valuation €{estimated_value_eur:,.0f} "
                    f"exceeds hard budget ceiling €{hard_ceiling:,.0f}."
                )
        checks["budget_ceiling"] = budget_passed

        # 5. Risk Tolerance Threshold
        risk_passed = True
        if risk_tolerance == "LOW" and risk_level in ("HIGH", "CRITICAL"):
            risk_passed = False
            exclusion_reasons.append(
                f"Risk profile exceeded: candidate carries {risk_level} risk under a LOW risk tolerance mandate."
            )
        elif risk_tolerance == "MEDIUM" and risk_level == "CRITICAL":
            risk_passed = False
            exclusion_reasons.append(
                "Risk profile exceeded: candidate carries CRITICAL transfer risk under a MEDIUM risk tolerance mandate."
            )
        checks["risk_tolerance"] = risk_passed

        all_passed = all(checks.values())
        return HardConstraintResult(
            passed=all_passed,
            checks=checks,
            exclusion_reasons=exclusion_reasons,
        )
