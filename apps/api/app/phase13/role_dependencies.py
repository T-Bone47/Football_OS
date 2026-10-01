"""Phase 13 — Role Dependency Graph Engine (§9).

Models structural on-pitch inter-role dependencies:
  Example:
    Ball Playing CB
      ↓ (MODELLED_DEPENDENCY)
    Build-up Progression
      ↓ (MODELLED_DEPENDENCY)
    Midfield Receiving Structure
      ↓ (MODELLED_DEPENDENCY)
    Fullback Positioning

  Example:
    Holding Midfielder (Anchor)
      ↓ (MODELLED_DEPENDENCY)
    Transition Protection
      ↓ (MODELLED_DEPENDENCY)
    Attacking Fullback Release & Overlap

Epistemic Non-Causal Policy:
  - Label all edges as MODELLED_DEPENDENCY.
  - Never make causal claims ("Player X causes Player Y to score").
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from app.dev_fixtures import dev_seed_enabled


@dataclass
class RoleDependencyEdge:
    """A modelled structural dependency between two pitch roles."""
    source_role: str
    target_role: str
    functional_channel: str  # BUILD_UP_PROGRESSION, TRANSITION_PROTECTION, OVERLAP_RELEASE, PRESS_TRIGGER
    dependency_strength: float = 0.85  # 0.0 - 1.0
    epistemic_relation: str = "MODELLED_DEPENDENCY"
    structural_explanation: str = ""

    @property
    def relationship_type(self) -> str:
        return self.epistemic_relation

    @property
    def description(self) -> str:
        return self.structural_explanation

    @property
    def epistemic_modality(self) -> str:
        return "MODELLED"


@dataclass
class RoleDependencyGraph:
    """Structural network of role relationships in a tactical system."""
    graph_id: str = field(default_factory=lambda: f"rdg_{uuid.uuid4().hex[:12]}")
    system_name: str = "4-3-3 High-Line Positional Possession"
    edges: list[RoleDependencyEdge] = field(default_factory=list)
    system_bottlenecks: list[str] = field(default_factory=list)
    established_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "system_name": self.system_name,
            "edges": [asdict(e) for e in self.edges],
            "system_bottlenecks": self.system_bottlenecks,
            "established_at": self.established_at,
        }


class RoleDependencyEngine:
    """Evaluates how changes to one tactical role perturb adjacent roles in the system."""

    def __init__(self) -> None:
        self._graphs: dict[str, RoleDependencyGraph] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_graphs()

    def _seed_default_graphs(self) -> None:
        edges = [
            RoleDependencyEdge(
                source_role="Ball Playing Defender",
                target_role="Inverted Playmaker",
                functional_channel="BUILD_UP_PROGRESSION",
                dependency_strength=0.92,
                epistemic_relation="MODELLED_DEPENDENCY",
                structural_explanation="Centre-back first-phase line-breaking passing volume dictates inverted fullback central receiving space.",
            ),
            RoleDependencyEdge(
                source_role="Holding Midfielder",
                target_role="Attacking Fullback",
                functional_channel="TRANSITION_PROTECTION",
                dependency_strength=0.88,
                epistemic_relation="MODELLED_DEPENDENCY",
                structural_explanation="Defensive midfielder half-space rest-defense coverage enables high fullback forward positioning.",
            ),
            RoleDependencyEdge(
                source_role="Advanced Playmaker",
                target_role="Inverted Winger",
                functional_channel="OVERLAP_RELEASE",
                dependency_strength=0.84,
                epistemic_relation="MODELLED_DEPENDENCY",
                structural_explanation="Interior half-space gravity creates isolated 1v1 wide crossing corridors for wingers.",
            ),
        ]

        graph = RoleDependencyGraph(
            system_name="4-3-3 High-Line Positional Possession",
            edges=edges,
            system_bottlenecks=[
                "High reliance on Ball Playing CB first-phase passing to initiate midfield central progression.",
                "Absence of elite Holding Midfielder rest-defense exposes vacated fullback flank channels.",
            ],
        )
        self._graphs["4-3-3"] = graph

    def get_dependencies_for_system(self, formation: str = "4-3-3") -> RoleDependencyGraph:
        return self._graphs.get(formation, self._graphs.get("4-3-3"))

    def get_dependencies_for_role(self, role_name: str, formation: str = "4-3-3") -> list[RoleDependencyEdge]:
        graph = self.get_dependencies_for_system(formation)
        if not graph:
            return []
        matches = [e for e in graph.edges if role_name.lower() in e.source_role.lower() or role_name.lower() in e.target_role.lower()]
        return matches or graph.edges


role_dependency_engine = RoleDependencyEngine()
