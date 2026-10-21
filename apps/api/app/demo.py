"""Demonstration fixtures are opt-in and can never run in production.

Phase 13 (Decision Lab) and Phase 14 (Outcome Intelligence) were built on hand-typed demonstration figures
(a seeded Arsenal squad with made-up ratings, seeded "verified" outcomes, hardcoded depth charts). They are
available only when FOOTBALL_OS_DEMO_DATA=1 and ENVIRONMENT is not "production"; otherwise their stores start
empty and their HTTP routes answer 409 DEMO_ONLY, until they are rebuilt on verified canonical data.
"""
from __future__ import annotations

import os

DEMO_ENV = "FOOTBALL_OS_DEMO_DATA"


def demo_data_allowed() -> bool:
    if os.environ.get("ENVIRONMENT", "development").strip().lower() == "production":
        return False
    return os.environ.get(DEMO_ENV, "").strip() == "1"
