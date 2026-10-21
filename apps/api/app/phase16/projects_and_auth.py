"""User, Organization, Project Workspaces & Authoritative Access Control for Phase 16.

Roles:
- ADMIN: Full system access, provider credentials, model promotion, user administration.
- ANALYST: Recruitment projects, scenario simulation, decision records, model inspection.
- SCOUT: Player intelligence, search, shortlists, basic decision reviews.
- RESEARCHER: Research workspace, cohorts, experiments, feature candidate discovery.
- VIEWER: Read-only access to published reports and dashboards.

Rule: Backend authorization is authoritative; never rely on frontend hiding alone.

Identity comes ONLY from a verified token (app.security): this module never looks a user up by a
caller-supplied id, and it ships no seeded users, projects or watchlists. Projects are visible to
members of their organisation; watchlists are private to their owner. A missing or foreign object
raises KeyError (-> 404) so existence is not leaked.

STATE IS PROCESS-LOCAL IN MEMORY and is lost on restart (open issue: persistence in PostgreSQL).
"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.phase16 import UserRole
from app.security.permissions import ROLE_PERMISSIONS as _PERMISSIONS_BY_ROLE_NAME
from app.security.tokens import AuthError, Principal, require_permission


class RecruitmentProject(BaseModel):
    project_id: str
    organization_id: str
    name: str
    description: str
    target_position: str
    target_role: str
    budget_eur: float | None = None
    competition_scope: list[str] = Field(default_factory=list)
    lead_scout_id: str
    shortlist_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"  # ACTIVE, PAUSED, COMPLETED, ARCHIVED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WatchlistItem(BaseModel):
    item_id: str
    entity_type: str  # PLAYER, CLUB, COMPETITION, MODEL, DECISION, SCENARIO, RESEARCH_HYPOTHESIS
    entity_id: str
    entity_name: str
    previous_state: dict[str, Any] = Field(default_factory=dict)
    current_state: dict[str, Any] = Field(default_factory=dict)
    change: str | None = None
    evidence: list[str] = Field(default_factory=list)
    last_evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProductionWatchlist(BaseModel):
    watchlist_id: str
    user_id: str
    organization_id: str
    name: str
    description: str = ""
    items: list[WatchlistItem] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())



# Role permission matrix (single source: app.security.permissions)
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole[name.upper()]: set(perms) for name, perms in _PERMISSIONS_BY_ROLE_NAME.items()
}


class AuthorizationError(PermissionError):
    """Raised when an operation breaches backend role-based access control."""
    pass


class DuplicateIdError(ValueError):
    """A client-supplied id already exists; objects are never silently overwritten."""


class ProjectAndAuthManager:
    """Authoritative backend repository for projects and watchlists (process-local, in memory)."""

    def __init__(self) -> None:
        self._projects: dict[str, RecruitmentProject] = {}
        self._watchlists: dict[str, ProductionWatchlist] = {}

    # ---- authorization ------------------------------------------------------------------------
    def authorize(self, principal: Principal, required_permission: str) -> None:
        """Enforces role permissions for a VERIFIED principal. Raises AuthorizationError."""
        try:
            require_permission(principal, required_permission)
        except AuthError as exc:
            raise AuthorizationError(
                f"Unauthorized action: user '{principal.user_id}' lacks permission '{required_permission}'."
            ) from exc

    @staticmethod
    def _can_see_project(principal: Principal, project: RecruitmentProject) -> bool:
        in_org = principal.org_id is not None and project.organization_id == principal.org_id
        return in_org or project.lead_scout_id == principal.user_id

    # ---- projects -----------------------------------------------------------------------------
    def create_project(
        self,
        project_id: str,
        org_id: str,
        name: str,
        description: str,
        target_position: str,
        target_role: str,
        lead_scout_id: str,
        budget_eur: float | None = None,
        competition_scope: list[str] | None = None,
    ) -> RecruitmentProject:
        if project_id in self._projects:
            raise DuplicateIdError(f"Project '{project_id}' already exists.")
        project = RecruitmentProject(
            project_id=project_id,
            organization_id=org_id,
            name=name,
            description=description,
            target_position=target_position,
            target_role=target_role,
            budget_eur=budget_eur,
            competition_scope=competition_scope or [],
            lead_scout_id=lead_scout_id,
        )
        self._projects[project_id] = project
        return project

    def get_project(self, project_id: str) -> RecruitmentProject:
        if project_id not in self._projects:
            raise KeyError(f"Project '{project_id}' not found.")
        return self._projects[project_id]

    def get_project_for(self, principal: Principal, project_id: str) -> RecruitmentProject:
        project = self._projects.get(project_id)
        if project is None or not self._can_see_project(principal, project):
            raise KeyError(f"Project '{project_id}' not found.")
        return project

    def list_projects(self, org_id: str | None = None) -> list[RecruitmentProject]:
        projects = list(self._projects.values())
        if org_id:
            projects = [p for p in projects if p.organization_id == org_id]
        return projects

    def list_projects_for(self, principal: Principal) -> list[RecruitmentProject]:
        return [p for p in self._projects.values() if self._can_see_project(principal, p)]

    # ---- watchlists ---------------------------------------------------------------------------
    def create_watchlist(
        self,
        watchlist_id: str,
        user_id: str,
        org_id: str,
        name: str,
        description: str = "",
    ) -> ProductionWatchlist:
        if watchlist_id in self._watchlists:
            raise DuplicateIdError(f"Watchlist '{watchlist_id}' already exists.")
        wl = ProductionWatchlist(
            watchlist_id=watchlist_id,
            user_id=user_id,
            organization_id=org_id,
            name=name,
            description=description,
        )
        self._watchlists[watchlist_id] = wl
        return wl

    def add_watchlist_item(
        self,
        watchlist_id: str,
        item_id: str,
        entity_type: str,
        entity_id: str,
        entity_name: str,
        initial_state: dict[str, Any] | None = None,
    ) -> WatchlistItem:
        if watchlist_id not in self._watchlists:
            raise KeyError(f"Watchlist '{watchlist_id}' not found.")
        item = WatchlistItem(
            item_id=item_id,
            entity_type=entity_type.upper(),
            entity_id=entity_id,
            entity_name=entity_name,
            current_state=initial_state or {},
            previous_state={},
        )
        self._watchlists[watchlist_id].items.append(item)
        return item

    def evaluate_watchlist_item(
        self,
        watchlist_id: str,
        item_id: str,
        new_state: dict[str, Any],
        evidence: list[str] | None = None,
    ) -> WatchlistItem:
        if watchlist_id not in self._watchlists:
            raise KeyError(f"Watchlist '{watchlist_id}' not found.")
        wl = self._watchlists[watchlist_id]
        target_item = None
        for it in wl.items:
            if it.item_id == item_id:
                target_item = it
                break
        if not target_item:
            raise KeyError(f"Item '{item_id}' not found in watchlist '{watchlist_id}'.")

        # Preserve previous state, current state, change, evidence, timestamp
        target_item.previous_state = dict(target_item.current_state)
        target_item.current_state = dict(new_state)
        target_item.last_evaluated_at = datetime.now(timezone.utc).isoformat()
        target_item.evidence = evidence or []

        # Check if state changed
        diff_keys = [k for k in new_state if target_item.previous_state.get(k) != new_state[k]]
        if diff_keys:
            target_item.change = f"Attributes changed: {', '.join(diff_keys)}"
        else:
            target_item.change = None

        return target_item

    def get_watchlist(self, watchlist_id: str) -> ProductionWatchlist:
        if watchlist_id not in self._watchlists:
            raise KeyError(f"Watchlist '{watchlist_id}' not found.")
        return self._watchlists[watchlist_id]

    def get_watchlist_for(self, principal: Principal, watchlist_id: str) -> ProductionWatchlist:
        wl = self._watchlists.get(watchlist_id)
        if wl is None or wl.user_id != principal.user_id:
            raise KeyError(f"Watchlist '{watchlist_id}' not found.")
        return wl

    def list_watchlists(self, user_id: str | None = None) -> list[ProductionWatchlist]:
        wls = list(self._watchlists.values())
        if user_id:
            wls = [w for w in wls if w.user_id == user_id]
        return wls

    def list_watchlists_for(self, principal: Principal) -> list[ProductionWatchlist]:
        return [w for w in self._watchlists.values() if w.user_id == principal.user_id]


_GLOBAL_PROJECT_AUTH_MANAGER: ProjectAndAuthManager | None = None


def get_project_auth_manager() -> ProjectAndAuthManager:
    global _GLOBAL_PROJECT_AUTH_MANAGER
    if _GLOBAL_PROJECT_AUTH_MANAGER is None:
        _GLOBAL_PROJECT_AUTH_MANAGER = ProjectAndAuthManager()
    return _GLOBAL_PROJECT_AUTH_MANAGER
