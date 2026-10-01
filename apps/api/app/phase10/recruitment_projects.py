"""Phase 10 — Persistent Recruitment Projects & Candidate Shortlists (§6, §7, §8).

Manages persistent scouting recruitment projects and candidate shortlist lifecycle:
  Requirement → Hard Constraints → Candidate Universe → Player Intelligence
  → Role → Tactical Fit → Similarity → Valuation → Transfer Risk → Squad Impact
  → Evidence → Decision.

Candidate workflow states:
  DISCOVERED → REVIEWING → SHORTLISTED → SCENARIO_TESTED → DECISION_RECORDED → ARCHIVED.

Scout notes and annotations are preserved independently and never alter underlying analytical metrics.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


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


@dataclass
class CandidateEntry:
    """A candidate player tracked inside a recruitment project."""
    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    player_id: str = ""
    player_name: str = ""
    current_club: str = ""
    current_competition: str = ""
    position: str = ""
    age: int = 24
    state: str = CandidateState.DISCOVERED
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Analytical outputs (Immutable from manual edits)
    analytical_assessment: dict[str, Any] = field(default_factory=dict)
    hard_constraints_passed: bool = True
    overall_confidence: str = "HIGH"
    data_status: str = "IN_DISTRIBUTION"

    # Scout annotations (isolated from analytical scores)
    scout_notes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    scout_priority: str = "NORMAL"  # HIGH, NORMAL, LOW

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecruitmentProject:
    """Persistent recruitment project specification (§6)."""
    project_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Summer 2027 CB Recruitment"
    club: str = "Arsenal"
    season: str = "2024/2025"
    position: str = "CB"
    target_role: str = "Ball Playing Defender"
    formation: str = "4-3-3"
    budget_eur: float = 40_000_000.0
    min_age: int = 19
    max_age: int = 27
    risk_tolerance: str = "MODERATE"  # LOW, MODERATE, HIGH
    competition_constraints: list[str] = field(default_factory=lambda: ["EPL", "LaLiga", "SerieA", "Bundesliga", "Ligue1"])
    min_minutes_played: int = 900
    status: str = ProjectStatus.ACTIVE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    candidates: list[CandidateEntry] = field(default_factory=list)
    decision_record_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecruitmentProjectManager:
    """In-memory persistent project and shortlist store with pipeline evaluation."""

    def __init__(self) -> None:
        self._projects: dict[str, RecruitmentProject] = {}
        self._seed_default_projects()

    def _seed_default_projects(self) -> None:
        """Seed demo recruitment project matching Phase 10 spec."""
        proj = RecruitmentProject(
            project_id="proj_cb_summer_2027",
            name="Summer 2027 CB Recruitment",
            club="Arsenal",
            season="2024/2025",
            position="CB",
            target_role="Ball Playing Defender",
            formation="4-3-3",
            budget_eur=40_000_000.0,
            min_age=20,
            max_age=26,
            risk_tolerance="MODERATE",
            competition_constraints=["EPL", "LaLiga", "Bundesliga", "SerieA"],
            min_minutes_played=1200,
        )

        # Seed sample discovered candidates
        c1 = CandidateEntry(
            candidate_id="cand_saliba",
            player_id="p_william_saliba",
            player_name="William Saliba",
            current_club="Arsenal",
            current_competition="EPL",
            position="CB",
            age=23,
            state=CandidateState.SHORTLISTED,
            hard_constraints_passed=True,
            overall_confidence="HIGH",
            data_status="IN_DISTRIBUTION",
            analytical_assessment={
                "tactical_fit_score": 92.4,
                "contribution_rating": 88.5,
                "estimated_value_eur": 75_000_000.0,
                "overall_risk_score": 0.18,
                "role_compatibility": 94.0,
            },
            scout_notes=["Elite progression and 1v1 defensive ground duels."],
            tags=["Internal Baseline", "Elite"],
        )

        c2 = CandidateEntry(
            candidate_id="cand_inacio",
            player_id="p_goncalo_inacio",
            player_name="Gonçalo Inácio",
            current_club="Sporting CP",
            current_competition="Liga Portugal",
            position="CB",
            age=22,
            state=CandidateState.REVIEWING,
            hard_constraints_passed=True,
            overall_confidence="HIGH",
            data_status="IN_DISTRIBUTION",
            analytical_assessment={
                "tactical_fit_score": 86.2,
                "contribution_rating": 81.0,
                "estimated_value_eur": 38_000_000.0,
                "overall_risk_score": 0.32,
                "role_compatibility": 89.0,
            },
            scout_notes=["Left-footed progressive passer; fits 4-3-3 build-up."],
            tags=["Target Option", "Left-Footed"],
        )

        proj.candidates.extend([c1, c2])
        self._projects[proj.project_id] = proj

    def create_project(self, data: dict[str, Any]) -> RecruitmentProject:
        """Create and store a new persistent recruitment project."""
        p_id = data.get("project_id") or f"proj_{uuid.uuid4().hex[:12]}"
        project = RecruitmentProject(
            project_id=p_id,
            name=data.get("name", "New Recruitment Project"),
            club=data.get("club", "Arsenal"),
            season=data.get("season", "2024/2025"),
            position=data.get("position", "CB"),
            target_role=data.get("target_role", "Ball Playing Defender"),
            formation=data.get("formation", "4-3-3"),
            budget_eur=float(data.get("budget_eur", 40_000_000.0)),
            min_age=int(data.get("min_age", 18)),
            max_age=int(data.get("max_age", 32)),
            risk_tolerance=data.get("risk_tolerance", "MODERATE"),
            competition_constraints=data.get("competition_constraints", ["EPL", "LaLiga"]),
            min_minutes_played=int(data.get("min_minutes_played", 900)),
        )
        self._projects[p_id] = project
        return project

    def get_project(self, project_id: str) -> RecruitmentProject | None:
        return self._projects.get(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self._projects.values()]

    def update_project(self, project_id: str, updates: dict[str, Any]) -> RecruitmentProject | None:
        p = self._projects.get(project_id)
        if not p:
            return None
        for k, v in updates.items():
            if hasattr(p, k) and k not in ("project_id", "created_at", "candidates"):
                setattr(p, k, v)
        p.updated_at = datetime.now(timezone.utc).isoformat()
        return p

    def add_candidate(self, project_id: str, candidate_data: dict[str, Any]) -> CandidateEntry | None:
        p = self._projects.get(project_id)
        if not p:
            return None

        # Hard constraints execution (§7: Hard constraints execute BEFORE soft scoring)
        age = int(candidate_data.get("age", 24))
        val = float(candidate_data.get("estimated_value_eur", 20_000_000.0))
        comp = candidate_data.get("current_competition", "EPL")

        age_ok = p.min_age <= age <= p.max_age
        budget_ok = val <= p.budget_eur * 1.15  # Up to 15% stretch buffer
        comp_ok = not p.competition_constraints or comp in p.competition_constraints

        passed_hard_constraints = age_ok and budget_ok and comp_ok

        cand = CandidateEntry(
            candidate_id=candidate_data.get("candidate_id") or f"cand_{uuid.uuid4().hex[:8]}",
            player_id=candidate_data.get("player_id", "p_unknown"),
            player_name=candidate_data.get("player_name", "Unknown Player"),
            current_club=candidate_data.get("current_club", "Unknown Club"),
            current_competition=comp,
            position=candidate_data.get("position", p.position),
            age=age,
            state=candidate_data.get("state", CandidateState.DISCOVERED),
            hard_constraints_passed=passed_hard_constraints,
            overall_confidence=candidate_data.get("overall_confidence", "HIGH"),
            data_status=candidate_data.get("data_status", "IN_DISTRIBUTION"),
            analytical_assessment=candidate_data.get("analytical_assessment", {
                "tactical_fit_score": float(candidate_data.get("tactical_fit_score", 75.0)),
                "contribution_rating": float(candidate_data.get("contribution_rating", 70.0)),
                "estimated_value_eur": val,
                "overall_risk_score": float(candidate_data.get("overall_risk_score", 0.35)),
                "hard_constraints_breakdown": {
                    "age_valid": age_ok,
                    "budget_valid": budget_ok,
                    "competition_valid": comp_ok,
                },
            }),
            scout_notes=candidate_data.get("scout_notes", []),
            tags=candidate_data.get("tags", []),
            scout_priority=candidate_data.get("scout_priority", "NORMAL"),
        )

        p.candidates.append(cand)
        p.updated_at = datetime.now(timezone.utc).isoformat()
        return cand

    def update_candidate_state(
        self,
        project_id: str,
        candidate_id: str,
        new_state: str,
    ) -> CandidateEntry | None:
        """Transitions candidate along workflow states without altering analytical results."""
        p = self._projects.get(project_id)
        if not p:
            return None
        for c in p.candidates:
            if c.candidate_id == candidate_id:
                c.state = new_state
                p.updated_at = datetime.now(timezone.utc).isoformat()
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
            return True
        return False

    def compare_candidates(self, project_id: str, candidate_ids: list[str]) -> dict[str, Any]:
        """Multi-dimensional side-by-side comparison across all analytical dimensions (§8)."""
        p = self._projects.get(project_id)
        if not p:
            return {"error": "Project not found"}

        candidates = [c for c in p.candidates if c.candidate_id in candidate_ids]
        if not candidates:
            return {"error": "No matching candidates found"}

        return {
            "project_id": p.project_id,
            "project_name": p.name,
            "compared_count": len(candidates),
            "candidates": [c.to_dict() for c in candidates],
            "dimension_comparison": {
                "tactical_fit": {c.player_name: c.analytical_assessment.get("tactical_fit_score", 0.0) for c in candidates},
                "contribution_rating": {c.player_name: c.analytical_assessment.get("contribution_rating", 0.0) for c in candidates},
                "estimated_value_eur": {c.player_name: c.analytical_assessment.get("estimated_value_eur", 0.0) for c in candidates},
                "risk_score": {c.player_name: c.analytical_assessment.get("overall_risk_score", 0.0) for c in candidates},
            },
        }


recruitment_manager = RecruitmentProjectManager()
