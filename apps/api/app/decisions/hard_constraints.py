"""Hard Constraints Engine (Phase 7.4).

Guarantees:
- Hard constraints (position, budget ceiling, age window, minutes floor, risk tolerance)
  are strictly evaluated BEFORE soft evidence.
- Soft scores are NEVER permitted to override hard exclusions.
- Excluded candidates retain explicit, truthful exclusion reasons.
"""
from __future__ import annotations

from app.decisions.schemas import HardConstraintResult
from app.roles.registry import map_position_to_group


class HardConstraintsEngine:
    """Enforces non-negotiable boundaries for player recruitment and transfers."""

    @classmethod
    def evaluate(
        cls,
        candidate_position: str | None,
        target_position: str,
        age: float | None,
        min_age: float | None,
        max_age: float | None,
        minutes_played: int | None,
        min_minutes: int | None,
        estimated_value_eur: float | None,
        budget_eur: float | None,
        risk_level: str | None,
        risk_tolerance: str = "MEDIUM",
    ) -> HardConstraintResult:
        """Evaluates each hard parameter against observed values only.

        Phase 18 (R23): an unknown value never passes a constraint the request
        sets. Unknown position, age (with an age window) or minutes (with a
        floor) excludes the candidate with that reason. An unknown valuation
        or risk level is recorded as unverifiable (None), not as a pass.
        """
        checks: dict[str, bool | None] = {}
        exclusion_reasons: list[str] = []

        # 1. Position
        if not candidate_position:
            checks["position_match"] = False
            exclusion_reasons.append("Position UNKNOWN: the required slot cannot be verified.")
        else:
            cand_group = map_position_to_group(candidate_position)
            target_group = map_position_to_group(target_position)
            pos_match = candidate_position.upper() == target_position.upper() or cand_group == target_group
            checks["position_match"] = pos_match
            if not pos_match:
                exclusion_reasons.append(
                    f"Position mismatch: candidate plays {candidate_position} "
                    f"({cand_group.name if hasattr(cand_group, 'name') else cand_group}), "
                    f"which does not fulfill required {target_position} slot."
                )

        # 2. Age window
        if min_age is None and max_age is None:
            checks["age_window"] = True
        elif age is None:
            checks["age_window"] = False
            exclusion_reasons.append("Age UNKNOWN: the age window cannot be verified.")
        else:
            ok = True
            if min_age is not None and age < min_age:
                ok = False
                exclusion_reasons.append(f"Age {age:.1f} is below minimum age boundary ({min_age:.0f}).")
            if max_age is not None and age > max_age:
                ok = False
                exclusion_reasons.append(f"Age {age:.1f} exceeds maximum age boundary ({max_age:.0f}).")
            checks["age_window"] = ok

        # 3. Minutes floor
        if min_minutes is None:
            checks["minutes_floor"] = True
        elif minutes_played is None:
            checks["minutes_floor"] = False
            exclusion_reasons.append("Minutes not reported by any provider: the minutes floor cannot be verified.")
        elif minutes_played < min_minutes:
            checks["minutes_floor"] = False
            exclusion_reasons.append(
                f"Sample insufficiency: {minutes_played} minutes played is below required minimum threshold ({min_minutes} mins)."
            )
        else:
            checks["minutes_floor"] = True

        # 4. Budget ceiling (10% stretch). Unknown value -> unverifiable.
        if budget_eur is None or budget_eur <= 0:
            checks["budget_ceiling"] = True
        elif estimated_value_eur is None:
            checks["budget_ceiling"] = None
        else:
            hard_ceiling = budget_eur * 1.10
            ok = estimated_value_eur <= hard_ceiling
            checks["budget_ceiling"] = ok
            if not ok:
                exclusion_reasons.append(
                    f"Financial ceiling exceeded: estimated valuation €{estimated_value_eur:,.0f} "
                    f"exceeds hard budget ceiling €{hard_ceiling:,.0f}."
                )

        # 5. Risk tolerance. Unknown risk -> unverifiable.
        if risk_level is None or risk_level == "INSUFFICIENT_DATA":
            checks["risk_tolerance"] = None
        else:
            ok = True
            if risk_tolerance == "LOW" and risk_level in ("HIGH", "CRITICAL"):
                ok = False
                exclusion_reasons.append(
                    f"Risk profile exceeded: candidate carries {risk_level} risk under a LOW risk tolerance mandate."
                )
            elif risk_tolerance == "MEDIUM" and risk_level == "CRITICAL":
                ok = False
                exclusion_reasons.append(
                    "Risk profile exceeded: candidate carries CRITICAL transfer risk under a MEDIUM risk tolerance mandate."
                )
            checks["risk_tolerance"] = ok

        return HardConstraintResult(
            passed=not any(v is False for v in checks.values()),
            checks=checks,
            exclusion_reasons=exclusion_reasons,
        )
