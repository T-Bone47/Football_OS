"""Role -> permission matrix (single source; moved out of phase16 so auth has no pydantic dependency).

Backend authorization is authoritative: the frontend hiding a button is not access control.
"""
from __future__ import annotations

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset({
        "data:read", "data:write", "research:execute", "research:validate",
        "decision:create", "decision:review", "scenario:simulate",
        "model:promote", "admin:access", "project:manage",
    }),
    "analyst": frozenset({
        "data:read", "research:execute", "decision:create", "decision:review",
        "scenario:simulate", "project:manage",
    }),
    "scout": frozenset({"data:read", "decision:create", "project:manage"}),
    "researcher": frozenset({"data:read", "research:execute", "research:validate"}),
    "viewer": frozenset({"data:read"}),
}


def permissions_for(roles: frozenset[str]) -> frozenset[str]:
    """Union of permissions for the given roles. Unknown roles grant nothing."""
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)
