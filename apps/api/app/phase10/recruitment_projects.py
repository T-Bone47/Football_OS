"""Phase 10 — Persistent Recruitment Projects & Candidate Shortlists (§6, §7, §8).

Manages persistent scouting recruitment projects and candidate shortlist lifecycle:
  Requirement → Hard Constraints → Candidate Universe → Player Intelligence
  → Role → Tactical Fit → Similarity → Valuation → Transfer Risk → Squad Impact
  → Evidence → Decision.

Candidate workflow states:
  DISCOVERED → REVIEWING → SHORTLISTED → SCENARIO_TESTED → DECISION_RECORDED → ARCHIVED.

Scout notes and annotations are preserved independently and never alter underlying analytical metrics.

Truth rules: nothing is defaulted. A fact nobody supplied stays None (or "") and is reported as unknown;
a constraint that cannot be verified is None, never "met"; confidence/status are UNASSESSED because no
validated engine computes them here; assessment numbers are recorded as USER_SUPPLIED, never as model
output. Every project has an owner and an organisation (404 across tenants).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.persistence.factory import get_stores
from app.persistence.stores import CollectionStore
from app.security.tokens import Principal


class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DECIDED = "DECIDED"
    ARCHIVED = "ARCHIVED"


class CandidateState(str, Enum):
    DISCOVERED = "DISCOVERED"
    REVIEWING = "REVIEWING"
    SHORTLISTED = "SHORTLISTED"
    SCENARIO_TESTED = "SCENARIO_TESTED"
    DECISION_RECORDED = "DECISION_RECORDED"
    ARCHIVED = "ARCHIVED"


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _within(value: float | None, low: float | None, high: float | None) -> bool | None:
    """True/False when checkable; None when a bound exists but the value is unknown; True when unconstrained."""
    if low is None and high is None:
        return True
    if value is None:
        return None
    return (low is None or value >= low) and (high is None or value <= high)


_REQUIRED_PROJECT_FIELDS = ("name", "club", "season", "position", "target_role")
_ASSESSMENT_KEYS = ("tactical_fit_score", "contribution_rating", "estimated_value_eur", "overall_risk_score", "role_compatibility")
BUDGET_STRETCH = 1.15  # existing policy constant: up to 15% over budget still counts as within budget


@dataclass
class CandidateEntry:
    """A candidate player tracked inside a recruitment project. Unknown facts stay None / ""."""
    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    player_id: str = ""
    player_name: str = ""
    current_club: str = ""
    current_competition: str = ""
    position: str = ""
    age: int | None = None
    state: str = CandidateState.DISCOVERED
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Assessment values exactly as supplied by a user (source USER_SUPPLIED) or None. No engine computes them here.
    analytical_assessment: dict[str, Any] = field(default_factory=dict)
    hard_constraints_passed: bool | None = None  # True all verified, False at least one violated, None not fully verifiable
    overall_confidence: str = "UNASSESSED"
    data_status: str = "UNASSESSED"

    # Scout annotations (isolated from analytical scores)
    scout_notes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    scout_priority: str = "NORMAL"  # HIGH, NORMAL, LOW

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecruitmentProject:
    """Persistent recruitment project specification (§6). Unstated constraints are None / empty, not invented."""
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    club: str = ""
    season: str = ""
    position: str = ""
    target_role: str = ""
    formation: str = ""
    budget_eur: float | None = None
    min_age: int | None = None
    max_age: int | None = None
    risk_tolerance: str | None = None  # LOW, MODERATE, HIGH
    competition_constraints: list[str] = field(default_factory=list)
    min_minutes_played: int | None = None
    status: str = ProjectStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    candidates: list[CandidateEntry] = field(default_factory=list)
    decision_record_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    owner_id: str = ""
    organization_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecruitmentProjectManager:
    """Recruitment project store. Backed by a CollectionStore (PostgreSQL in production, in-memory otherwise),
    so projects and their candidates survive a process restart. Starts empty; nothing is seeded."""

    _COLLECTION = "phase10_projects"

    def __init__(self, store: CollectionStore | None = None) -> None:
        self._store = store
        self._projects: dict[str, RecruitmentProject] = {}
        if store is not None:
            for record in store.list(self._COLLECTION):
                self._projects[record.record_id] = self._from_payload(record.record_id, record.payload)

    @staticmethod
    def _from_payload(project_id: str, data: dict[str, Any]) -> RecruitmentProject:
        candidates = [CandidateEntry(**c) for c in data.get("candidates", [])]
        fields = {k: v for k, v in data.items() if k not in ("project_id", "candidates")}
        return RecruitmentProject(project_id=project_id, candidates=candidates, **fields)

    def _save(self, project: RecruitmentProject) -> None:
        if self._store is not None:
            self._store.put(self._COLLECTION, project.project_id, project.owner_id, project.organization_id, project.to_dict())

    # ---- access control ----------------------------------------------------------------------
    @staticmethod
    def _can_see(principal: Principal, project: RecruitmentProject) -> bool:
        in_org = principal.org_id is not None and project.organization_id == principal.org_id
        return in_org or project.owner_id == principal.user_id

    def get_project_for(self, principal: Principal, project_id: str) -> RecruitmentProject:
        """KeyError (-> 404) for a missing project AND for another tenant's project, so existence is not leaked."""
        project = self._projects.get(project_id)
        if project is None or not self._can_see(principal, project):
            raise KeyError(f"Project '{project_id}' not found")
        return project

    def list_projects_for(self, principal: Principal) -> list[RecruitmentProject]:
        return [p for p in self._projects.values() if self._can_see(principal, p)]

    # ---- projects ----------------------------------------------------------------------------
    def create_project(self, data: dict[str, Any], owner_id: str, organization_id: str | None = None) -> RecruitmentProject:
        missing = [k for k in _REQUIRED_PROJECT_FIELDS if not str(data.get(k) or "").strip()]
        if missing:
            raise ValueError(f"missing required project field(s): {', '.join(missing)}")
        if not owner_id:
            raise ValueError("owner_id is required")
        project_id = data.get("project_id") or f"proj_{uuid.uuid4().hex[:12]}"
        if project_id in self._projects:
            raise ValueError(f"project '{project_id}' already exists")
        project = RecruitmentProject(
            project_id=project_id,
            name=str(data["name"]).strip(),
            club=str(data["club"]).strip(),
            season=str(data["season"]).strip(),
            position=str(data["position"]).strip(),
            target_role=str(data["target_role"]).strip(),
            formation=str(data.get("formation") or ""),
            budget_eur=_opt_float(data.get("budget_eur")),
            min_age=_opt_int(data.get("min_age")),
            max_age=_opt_int(data.get("max_age")),
            risk_tolerance=data.get("risk_tolerance"),
            competition_constraints=list(data.get("competition_constraints") or []),
            min_minutes_played=_opt_int(data.get("min_minutes_played")),
            owner_id=owner_id,
            organization_id=organization_id,
        )
        self._projects[project_id] = project
        self._save(project)
        return project

    def get_project(self, project_id: str) -> RecruitmentProject | None:
        return self._projects.get(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._projects.values()]

    def update_project(self, project_id: str, updates: dict[str, Any]) -> RecruitmentProject | None:
        p = self._projects.get(project_id)
        if not p:
            return None
        protected = ("project_id", "created_at", "candidates", "owner_id", "organization_id")
        for k, v in updates.items():
            if hasattr(p, k) and k not in protected:
                setattr(p, k, v)
        p.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(p)
        return p

    # ---- candidates --------------------------------------------------------------------------
    def add_candidate(self, project_id: str, candidate_data: dict[str, Any]) -> CandidateEntry | None:
        """Hard constraints run first, tri-state; analytical labels are never taken from the caller."""
        p = self._projects.get(project_id)
        if not p:
            return None
        player_id = str(candidate_data.get("player_id") or "").strip()
        player_name = str(candidate_data.get("player_name") or "").strip()
        if not player_id or not player_name:
            raise ValueError("player_id and player_name are required")

        age = _opt_int(candidate_data.get("age"))
        value = _opt_float(candidate_data.get("estimated_value_eur"))
        competition = candidate_data.get("current_competition") or ""

        age_ok = _within(age, p.min_age, p.max_age)
        budget_ok = True if p.budget_eur is None else (None if value is None else value <= p.budget_eur * BUDGET_STRETCH)
        competition_ok = True if not p.competition_constraints else (None if not competition else competition in p.competition_constraints)
        checks = [age_ok, budget_ok, competition_ok]
        passed = False if any(c is False for c in checks) else (None if any(c is None for c in checks) else True)

        assessment: dict[str, Any] = {k: _opt_float(candidate_data.get(k)) for k in _ASSESSMENT_KEYS}
        assessment["source"] = "USER_SUPPLIED" if any(v is not None for v in assessment.values()) else "NONE"
        assessment["hard_constraints_breakdown"] = {"age_valid": age_ok, "budget_valid": budget_ok, "competition_valid": competition_ok}

        candidate = CandidateEntry(
            candidate_id=candidate_data.get("candidate_id") or f"cand_{uuid.uuid4().hex[:8]}",
            player_id=player_id,
            player_name=player_name,
            current_club=candidate_data.get("current_club") or "",
            current_competition=competition,
            position=candidate_data.get("position") or "",
            age=age,
            analytical_assessment=assessment,
            hard_constraints_passed=passed,
            scout_notes=list(candidate_data.get("scout_notes") or []),
            tags=list(candidate_data.get("tags") or []),
        )
        if any(c.candidate_id == candidate.candidate_id for c in p.candidates):
            raise ValueError(f"candidate '{candidate.candidate_id}' already exists in this project")
        p.candidates.append(candidate)
        p.updated_at = datetime.now(timezone.utc).isoformat()
        self._save(p)
        return candidate

    def update_candidate_state(self, project_id: str, candidate_id: str, new_state: str) -> CandidateEntry | None:
        p = self._projects.get(project_id)
        if not p:
            return None
        for c in p.candidates:
            if c.candidate_id == candidate_id:
                c.state = new_state
                p.updated_at = datetime.now(timezone.utc).isoformat()
                self._save(p)
                return c
        return None

    def annotate_candidate(
        self,
        project_id: str,
        candidate_id: str,
        notes: list[str] | None = None,
        tags: list[str] | None = None,
        priority: str | None = None,
    ) -> CandidateEntry | None:
        """Adds scout notes, tags, or priority without modifying any analytical assessments."""
        p = self._projects.get(project_id)
        if not p:
            return None
        for c in p.candidates:
            if c.candidate_id == candidate_id:
                if notes is not None:
                    c.scout_notes.extend(notes)
                if tags is not None:
                    c.tags = list(set(c.tags + tags))
                if priority is not None:
                    c.scout_priority = priority
                p.updated_at = datetime.now(timezone.utc).isoformat()
                self._save(p)
                return c
        return None

    def remove_candidate(self, project_id: str, candidate_id: str) -> bool:
        p = self._projects.get(project_id)
        if not p:
            return False
        orig_len = len(p.candidates)
        p.candidates = [c for c in p.candidates if c.candidate_id != candidate_id]
        if len(p.candidates) < orig_len:
            p.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(p)
            return True
        return False

    def compare_candidates(self, project_id: str, candidate_ids: list[str]) -> dict[str, Any]:
        """Side-by-side comparison; unknown values are None, never 0."""
        p = self._projects.get(project_id)
        if not p:
            return {"error": "Project not found"}

        candidates = [c for c in p.candidates if c.candidate_id in candidate_ids]
        if not candidates:
            return {"error": "No matching candidates found"}

        def dim(key: str) -> dict[str, Any]:
            return {c.player_name: c.analytical_assessment.get(key) for c in candidates}

        return {
            "project_id": p.project_id,
            "project_name": p.name,
            "compared_count": len(candidates),
            "candidates": [c.to_dict() for c in candidates],
            "dimension_comparison": {
                "tactical_fit": dim("tactical_fit_score"),
                "contribution_rating": dim("contribution_rating"),
                "estimated_value_eur": dim("estimated_value_eur"),
                "risk_score": dim("overall_risk_score"),
            },
        }


def _default_manager() -> RecruitmentProjectManager:
    return RecruitmentProjectManager(store=get_stores()[0])


recruitment_manager = _default_manager()
