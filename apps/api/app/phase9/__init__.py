"""Phase 9 — Real-World Data Expansion & Model Validation.

This package implements the data coverage audit, cross-competition validation,
OOD analysis, model stability, pipeline replay, and truthful reporting
framework mandated by Phase 9.

Release state lifecycle:
  PHASE_9_IN_PROGRESS → DATA_EXPANSION_VALIDATED → MODEL_VALIDATION_COMPLETE
  or blocked: PHASE_9_BLOCKED / PHASE_9_RELEASE_BLOCKED
"""

PHASE_9_VERSION = "9.0.0"

RELEASE_STATES = (
    "PHASE_9_IN_PROGRESS",
    "PHASE_9_BLOCKED",
    "DATA_EXPANSION_VALIDATED",
    "MODEL_VALIDATION_COMPLETE",
    "PHASE_9_RELEASE_BLOCKED",
)
