"""Component-status vocabulary and worst-of aggregation (handoff §7.5).

A health answer is only as good as its weakest measured component, and a component that was
not measured is UNKNOWN - never silently OK.
"""
from __future__ import annotations

OK = "OK"
DEGRADED = "DEGRADED"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
NOT_CONFIGURED = "NOT_CONFIGURED"  # component is not part of this deployment; excluded from aggregation


def aggregate_status(components: dict[str, str]) -> str:
    """UNAVAILABLE > DEGRADED > UNKNOWN > OK. NOT_CONFIGURED is ignored; nothing left -> UNKNOWN."""
    values = {v for v in components.values() if v != NOT_CONFIGURED}
    if not values:
        return UNKNOWN
    for level in (UNAVAILABLE, DEGRADED, UNKNOWN):
        if level in values:
            return level
    return OK
