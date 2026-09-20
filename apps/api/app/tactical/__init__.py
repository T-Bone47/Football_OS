"""Tactical Fit Engine module (Phase 2 Slice 3).
Evaluates player compatibility with specific tactical contexts, formations, and roles.
"""
from app.tactical.calculator import TacticalFitCalculator
from app.tactical.contexts import (
    STANDARD_TACTICAL_CONTEXTS,
    TacticalContext,
    TacticalRequirement,
    build_custom_context,
    get_standard_context,
)
from app.tactical.service import TacticalFitService

__all__ = [
    "TacticalFitCalculator",
    "TacticalContext",
    "TacticalRequirement",
    "STANDARD_TACTICAL_CONTEXTS",
    "build_custom_context",
    "get_standard_context",
    "TacticalFitService",
]
