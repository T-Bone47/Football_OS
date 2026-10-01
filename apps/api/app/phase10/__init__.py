"""Phase 10 — Intelligence OS v1.0: Live Data Operations, Recruitment Workflows & Productization.

Transforms the validated Football Intelligence OS into a continuous operational
intelligence platform supporting live/scheduled data, continuous intelligence,
recruitment projects, candidate shortlists, watchlists, governed alerts,
transfer/match scenarios, immutable decision records, and evidence-backed reporting.

Release state lifecycle:
  PHASE_10_IN_PROGRESS → OPERATIONAL_INTELLIGENCE_VALIDATED
  or blocked: PHASE_10_BLOCKED / PHASE_10_RELEASE_BLOCKED
"""

PHASE_10_VERSION = "10.0.0"

RELEASE_STATES = (
    "PHASE_10_IN_PROGRESS",
    "PHASE_10_BLOCKED",
    "OPERATIONAL_INTELLIGENCE_VALIDATED",
    "PHASE_10_RELEASE_BLOCKED",
)
