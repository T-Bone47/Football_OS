"""Phase 11 — Global Data Expansion, Cross-Competition Calibration & Continuous Model Validation.

Transforms the Football Intelligence OS from an EPL-centric operational platform into a
genuinely cross-competition intelligence platform with independently verified model validity,
reproducible dataset lineage, probability calibration, and continuous drift monitoring.
"""
from __future__ import annotations

__version__ = "11.0.0"

# Explicit Phase 11 Release States (§32)
RELEASE_STATES = (
    "PHASE_11_IN_PROGRESS",
    "DATA_EXPANSION_ACTIVE",
    "VALIDATION_READY",
    "CROSS_COMPETITION_VALIDATED",
    "SHADOW_VALIDATION_ACTIVE",
    "GLOBAL_INTELLIGENCE_VALIDATED",
    "PHASE_11_RELEASE_BLOCKED",
)

# Canonical Competition Validation Progression States (§6, §10)
COMPETITION_PROGRESSION_STATES = (
    "DATA_INGESTED",
    "DATA_VALIDATED",
    "FEATURE_READY",
    "VALIDATION_READY",
    "MODEL_VALIDATED",
    "PRODUCTION_READY",
)
