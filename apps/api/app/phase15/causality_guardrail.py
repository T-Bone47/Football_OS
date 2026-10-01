"""Automated Causality Guardrail for Phase 15.

Architectural Rule:
- Prohibit causal claims ("Player X caused result Y", "Formation Z caused win").
- Enforce associative, descriptive language:
  "associated with", "consistent with", "aligned with", "diverged from",
  "not explained by available evidence", "correlated with".
"""

import re
from typing import Any

CAUSAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcaused\b", re.IGNORECASE), "is associated with"),
    (re.compile(r"\bcauses\b", re.IGNORECASE), "is correlated with"),
    (re.compile(r"\bcausing\b", re.IGNORECASE), "associated with"),
    (re.compile(r"\bdirectly caused\b", re.IGNORECASE), "strongly coincided with"),
    (re.compile(r"\bcaused victory\b", re.IGNORECASE), "coincided with positive match outcome"),
    (re.compile(r"\bcaused the win\b", re.IGNORECASE), "coincided with victory"),
    (re.compile(r"\bformation caused\b", re.IGNORECASE), "formation aligned with"),
    (re.compile(r"\bsigning (.+) caused\b", re.IGNORECASE), r"signing \1 coincided with"),
    (re.compile(r"\btransfer caused\b", re.IGNORECASE), "transfer preceded"),
    (re.compile(r"\btactical change caused\b", re.IGNORECASE), "tactical change associated with"),
    (re.compile(r"\bresulted in win because\b", re.IGNORECASE), "aligned with win; associated factors include"),
    (re.compile(r"\bdirect cause of\b", re.IGNORECASE), "primary factor associated with"),
]

PROHIBITED_SUBSTRINGS: list[str] = [
    "caused victory",
    "caused the win",
    "directly causes",
    "formation caused",
    "signing player caused",
    "transfer caused performance",
]


class CausalityViolationError(ValueError):
    """Raised when an analytical output breaches the non-causal policy."""
    pass


class CausalityGuardrail:
    """Enforces non-causal statistical language across research outputs and copilot responses."""

    @staticmethod
    def audit_text(text: str, strict: bool = False) -> tuple[bool, list[str]]:
        """Audits text for causal assertions.

        Returns (is_compliant, violations).
        """
        violations: list[str] = []
        lower_text = text.lower()
        for phrase in PROHIBITED_SUBSTRINGS:
            if phrase in lower_text:
                violations.append(f"Prohibited causal assertion detected: '{phrase}'")

        if violations and strict:
            raise CausalityViolationError("; ".join(violations))

        return len(violations) == 0, violations

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Deterministically rewrites causal formulations into compliant associative phrases."""
        sanitized = text
        for pattern, replacement in CAUSAL_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

    @staticmethod
    def generate_statement(metric: str, condition: str, relationship: str = "associated") -> str:
        """Generates standard compliant non-causal analytical statement."""
        if relationship == "associated":
            return f"Observed {metric} was statistically associated with {condition}; causal attribution is not established by observational data."
        elif relationship == "diverged":
            return f"Observed {metric} diverged from expectation under {condition}; difference is not explained by available evidence alone."
        elif relationship == "aligned":
            return f"Observed {metric} aligned with modeled projections under {condition}; evidence remains correlational."
        return f"Observed {metric} shows observational relationship with {condition} with substantial uncertainty."
