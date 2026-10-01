"""User, Organization, Project Workspaces & Authoritative Access Control for Phase 16.

Roles:
- ADMIN: Full system access, provider credentials, model promotion, user administration.
- ANALYST: Recruitment projects, scenario simulation, decision records, model inspection.
- SCOUT: Player intelligence, search, shortlists, basic decision reviews.
- RESEARCHER: Research workspace, cohorts, experiments, feature candidate discovery.
- VIEWER: Read-only access to published reports and dashboards.

Rule: Backend authorization is authoritative; never rely on frontend hiding alone.
"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.phase16 import UserRole


class UserProfile(BaseModel):
    user_id: str
    organization_id: str
    name: str
    email: str
    role: UserRole
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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



# Role permission matrix
ROLE_PERMISSIONS: dict[UserRole, set[str]] = {
    UserRole.ADMIN: {
        "data:read", "data:write", "research:execute", "research:validate",
        "decision:create", "decision:review", "scenario:simulate",
        "model:promote", "admin:access", "project:manage",
    },
    UserRole.ANALYST: {
        "data:read", "research:execute", "decision:create", "decision:review",
        "scenario:simulate", "project:manage",
    },
    UserRole.SCOUT: {
        "data:read", "decision:create", "project:manage",
    },
    UserRole.RESEARCHER: {
        "data:read", "research:execute", "research:validate",
    },
    UserRole.VIEWER: {
        "data:read",
    },
}


class AuthorizationError(PermissionError):
    """Raised when an operation breaches backend role-based access control."""
    pass


class ProjectAndAuthManager:
    """Authoritative backend repository for users, projects, and permissions."""

    def __init__(self, seed_demo: bool = True) -> None:
        self._users: dict[str, UserProfile] = {}
        self._projects: dict[str, RecruitmentProject] = {}
        self._watchlists: dict[str, ProductionWatchlist] = {}
        # Phase 17 (reconnaissance R10): demo users/projects are fixtures for
        # development and tests. The singleton never seeds them in staging or
        # production; real identities live in ops_users (app.phase17.auth).
        if seed_demo:
            self._seed_default_users_and_projects()

    def _seed_default_users_and_projects(self) -> None:
        # Default Admin & Scout
        self.register_user(
            user_id="admin_01",
            org_id="org_arsenal",
            name="Technical Director",
            email="director@arsenal.local",
            role=UserRole.ADMIN,
        )
        self.register_user(
            user_id="scout_01",
            org_id="org_arsenal",
            name="Head of First Team Scouting",
            email="scout@arsenal.local",
            role=UserRole.SCOUT,
        )
        self.register_user(
            user_id="analyst_01",
            org_id="org_arsenal",
            name="Lead Recruitment Analyst",
            email="analyst@arsenal.local",
            role=UserRole.ANALYST,
        )

        # Default Project
        self.create_project(
            project_id="proj_summer_2024_dm",
            org_id="org_arsenal",
            name="Summer 2024 - Elite Defensive Midfielder Replacement",
            description="Recruitment project identifying resilient progressive DMs in U25 bracket.",
            target_position="MF",
            target_role="Deep Lying Playmaker",
            budget_eur=65000000.0,
            competition_scope=["EPL", "Bundesliga", "La_Liga", "Serie_A"],
            lead_scout_id="scout_01",
        )

        # Default Watchlist
        self.create_watchlist(
            watchlist_id="wl_scout_priority",
            user_id="scout_01",
            org_id="org_arsenal",
            name="Priority Scouting & Model Operations Watchlist",
            description="Active tracking of target recruits, decision freshness, and champion models.",
        )
        self.add_watchlist_item(
            watchlist_id="wl_scout_priority",
            item_id="item_player_timber",
            entity_type="PLAYER",
            entity_id="player_jurrien_timber",
            entity_name="Jurrien Timber",
            initial_state={"status": "FIT", "role": "Inverted Fullback", "valuation_eur": 45000000.0},
        )
        self.add_watchlist_item(
            watchlist_id="wl_scout_priority",
            item_id="item_model_val",
            entity_type="MODEL",
            entity_id="valuation_ml_v1",
            entity_name="Valuation Engine Champion",
            initial_state={"status": "ACTIVE", "drift_psi": 0.04, "calibration": "CALIBRATED"},
        )


    def register_user(self, user_id: str, org_id: str, name: str, email: str, role: UserRole) -> UserProfile:
        user = UserProfile(user_id=user_id, organization_id=org_id, name=name, email=email, role=role)
        self._users[user_id] = user
        return user

    def authorize(self, user_id: str, required_permission: str) -> None:
        """Enforces authoritative RBAC checks. Raises AuthorizationError on violation."""
        user = self._users.get(user_id)
        if not user or not user.is_active:
            raise AuthorizationError(f"User '{user_id}' is unknown or inactive.")

        user_perms = ROLE_PERMISSIONS.get(user.role, set())
        if required_permission not in user_perms:
            raise AuthorizationError(
                f"Unauthorized action: User '{user_id}' with role '{user.role.value}' lacks required permission '{required_permission}'."
            )

    def create_project(
        self,
        project_id: str,
        org_id: str,
        name: str,
        description: str,
        target_position: str,
        target_role: str,
        budget_eur: float | None = None,
        competition_scope: list[str] | None = None,
        lead_scout_id: str = "scout_01",
    ) -> RecruitmentProject:
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

    def get_user(self, user_id: str) -> UserProfile:
        if user_id not in self._users:
            raise KeyError(f"User '{user_id}' not found.")
        return self._users[user_id]

    def get_project(self, project_id: str) -> RecruitmentProject:
        if project_id not in self._projects:
            raise KeyError(f"Project '{project_id}' not found.")
        return self._projects[project_id]

    def list_projects(self, org_id: str | None = None) -> list[RecruitmentProject]:
        projects = list(self._projects.values())
        if org_id:
            projects = [p for p in projects if p.organization_id == org_id]
        return projects

    def create_watchlist(
        self,
        watchlist_id: str,
        user_id: str,
        org_id: str,
        name: str,
        description: str = "",
    ) -> ProductionWatchlist:
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

    def list_watchlists(self, user_id: str | None = None) -> list[ProductionWatchlist]:
        wls = list(self._watchlists.values())
        if user_id:
            wls = [w for w in wls if w.user_id == user_id]
        return wls



_GLOBAL_PROJECT_AUTH_MANAGER: ProjectAndAuthManager | None = None


def get_project_auth_manager() -> ProjectAndAuthManager:
    global _GLOBAL_PROJECT_AUTH_MANAGER
    if _GLOBAL_PROJECT_AUTH_MANAGER is None:
        from app.config import get_settings
        from app.phase17.environments import is_hardened, resolve_environment

        hardened = is_hardened(resolve_environment(get_settings().environment))
        _GLOBAL_PROJECT_AUTH_MANAGER = ProjectAndAuthManager(seed_demo=not hardened)
    return _GLOBAL_PROJECT_AUTH_MANAGER
