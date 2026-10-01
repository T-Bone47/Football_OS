"""Phase 14 — Cryptographically Traceable Evidence Graph V3 (§18).

Extends Evidence Graph V2 to full lifecycle decision-learning lineage:
  - Node Types:
    DATA, FEATURE, MODEL, PREDICTION, ASSUMPTION, SCENARIO, DECISION,
    OUTCOME, EVALUATION, LEARNING_SIGNAL.
  - Edge Types:
    DERIVED_FROM, USED_BY, ASSUMED_BY, SIMULATED_BY, DECIDED_BY,
    REALIZED_AS, EVALUATED_BY, TRIGGERED, SUPPORTED_BY, CONTRADICTED_BY.
  - Epistemic Modalities:
    Every node carries explicit modality: OBSERVED, MODELLED, COUNTERFACTUAL, SCENARIO, ASSUMPTION.
  - Deterministic SHA-256 graph digest ensures non-repudiation and cryptographic lineage.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.phase14 import EpistemicModality
from app.dev_fixtures import dev_seed_enabled


class NodeTypeV3(str, Enum):
    DATA = "DATA"
    FEATURE = "FEATURE"
    MODEL = "MODEL"
    PREDICTION = "PREDICTION"
    ASSUMPTION = "ASSUMPTION"
    SCENARIO = "SCENARIO"
    DECISION = "DECISION"
    OUTCOME = "OUTCOME"
    EVALUATION = "EVALUATION"
    LEARNING_SIGNAL = "LEARNING_SIGNAL"


class EdgeTypeV3(str, Enum):
    DERIVED_FROM = "DERIVED_FROM"
    USED_BY = "USED_BY"
    ASSUMED_BY = "ASSUMED_BY"
    SIMULATED_BY = "SIMULATED_BY"
    DECIDED_BY = "DECIDED_BY"
    REALIZED_AS = "REALIZED_AS"
    EVALUATED_BY = "EVALUATED_BY"
    TRIGGERED = "TRIGGERED"
    SUPPORTED_BY = "SUPPORTED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"


@dataclass
class EvidenceNodeV3:
    """Individual node in the Evidence Graph V3 lineage (§18)."""
    node_id: str
    node_type: NodeTypeV3
    label: str
    modality: EpistemicModality
    provenance: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["node_type"] = self.node_type.value
        data["modality"] = self.modality.value
        return data


@dataclass
class EvidenceEdgeV3:
    """Directed connection between two evidence nodes in V3 lineage (§18)."""
    edge_id: str = field(default_factory=lambda: f"edge_{uuid.uuid4().hex[:8]}")
    source_id: str = ""
    target_id: str = ""
    edge_type: EdgeTypeV3 = EdgeTypeV3.DERIVED_FROM
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["edge_type"] = self.edge_type.value
        return data


@dataclass
class EvidenceGraphV3:
    """Complete cryptographic Evidence Graph V3 for a decision lifecycle (§18)."""
    graph_id: str = field(default_factory=lambda: f"eg3_{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    scenario_id: str = ""
    nodes: dict[str, EvidenceNodeV3] = field(default_factory=dict)
    edges: list[EvidenceEdgeV3] = field(default_factory=list)
    graph_digest: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_node(
        self,
        node_id: str,
        node_type: NodeTypeV3,
        label: str,
        modality: EpistemicModality,
        provenance: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> EvidenceNodeV3:
        node = EvidenceNodeV3(
            node_id=node_id,
            node_type=node_type,
            label=label,
            modality=modality,
            provenance=provenance or {},
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        )
        self.nodes[node_id] = node
        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeTypeV3,
        rationale: str = "",
    ) -> EvidenceEdgeV3:
        edge = EvidenceEdgeV3(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            rationale=rationale,
        )
        self.edges.append(edge)
        return edge

    def calculate_digest(self) -> str:
        """Computes deterministic SHA-256 hash over nodes and edges."""
        sorted_nodes = [
            self.nodes[k].to_dict()
            for k in sorted(self.nodes.keys())
        ]
        sorted_edges = sorted(
            [e.to_dict() for e in self.edges],
            key=lambda x: (x["source_id"], x["target_id"], x["edge_type"]),
        )
        payload = {
            "decision_id": self.decision_id,
            "scenario_id": self.scenario_id,
            "nodes": sorted_nodes,
            "edges": sorted_edges,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        self.graph_digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return self.graph_digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "decision_id": self.decision_id,
            "scenario_id": self.scenario_id,
            "graph_digest": self.graph_digest,
            "created_at": self.created_at,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }


class EvidenceGraphV3Builder:
    """Builds and caches Evidence Graph V3 instances."""

    def __init__(self) -> None:
        self._graphs: dict[str, EvidenceGraphV3] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_graph()

    def build_decision_graph(
        self,
        decision_id: str,
        scenario_id: str,
    ) -> EvidenceGraphV3:
        """Builds a complete decision-to-outcome-to-learning graph."""
        graph = EvidenceGraphV3(decision_id=decision_id, scenario_id=scenario_id)

        # 1. DATA node (OBSERVED)
        graph.add_node("node_raw_telemetry", NodeTypeV3.DATA, "Wyscout & Premier League Event Feeds", EpistemicModality.OBSERVED)
        # 2. FEATURE node (MODELLED)
        graph.add_node("node_features", NodeTypeV3.FEATURE, "Player Intelligence & Progression Vectors", EpistemicModality.MODELLED)
        # 3. MODEL node (MODELLED)
        graph.add_node("node_tactical_fit_model", NodeTypeV3.MODEL, "Tactical Fit Engine v2.1", EpistemicModality.MODELLED)
        # 4. PREDICTION node (MODELLED)
        graph.add_node("node_fit_prediction", NodeTypeV3.PREDICTION, "Modelled Tactical Fit Score: 88.0", EpistemicModality.MODELLED)
        # 5. ASSUMPTION node (ASSUMPTION)
        graph.add_node("node_assumptions", NodeTypeV3.ASSUMPTION, "Assumed 1,400+ Minutes & Inverted Role", EpistemicModality.ASSUMPTION)
        # 6. SCENARIO node (SCENARIO)
        graph.add_node("node_scenario", NodeTypeV3.SCENARIO, "Scenario: Sign Jurriën Timber (€40M)", EpistemicModality.SCENARIO)
        # 7. DECISION node (SCENARIO)
        graph.add_node("node_decision", NodeTypeV3.DECISION, "Final Decision: Execute Acquisition", EpistemicModality.SCENARIO)
        # 8. OUTCOME node (OBSERVED)
        graph.add_node("node_outcome_minutes", NodeTypeV3.OUTCOME, "Realized Minutes: 1,280 mins", EpistemicModality.OBSERVED)
        # 9. EVALUATION node (ANALYSIS)
        graph.add_node("node_evaluation", NodeTypeV3.EVALUATION, "Realization Evaluation: ALIGNED (91.4% mins)", EpistemicModality.ANALYSIS)
        # 10. LEARNING_SIGNAL node (ANALYSIS)
        graph.add_node("node_learning_signal", NodeTypeV3.LEARNING_SIGNAL, "Learning Signal: Monitor Year-1 Availability", EpistemicModality.ANALYSIS)

        # Edges
        graph.add_edge("node_raw_telemetry", "node_features", EdgeTypeV3.DERIVED_FROM)
        graph.add_edge("node_features", "node_tactical_fit_model", EdgeTypeV3.USED_BY)
        graph.add_edge("node_tactical_fit_model", "node_fit_prediction", EdgeTypeV3.DERIVED_FROM)
        graph.add_edge("node_assumptions", "node_scenario", EdgeTypeV3.ASSUMED_BY)
        graph.add_edge("node_fit_prediction", "node_scenario", EdgeTypeV3.SIMULATED_BY)
        graph.add_edge("node_scenario", "node_decision", EdgeTypeV3.DECIDED_BY)
        graph.add_edge("node_decision", "node_outcome_minutes", EdgeTypeV3.REALIZED_AS)
        graph.add_edge("node_outcome_minutes", "node_evaluation", EdgeTypeV3.EVALUATED_BY)
        graph.add_edge("node_evaluation", "node_learning_signal", EdgeTypeV3.TRIGGERED)

        graph.calculate_digest()
        self._graphs[decision_id] = graph
        return graph

    def get_graph(self, decision_id: str) -> EvidenceGraphV3 | None:
        return self._graphs.get(decision_id)

    def _seed_default_graph(self) -> None:
        self.build_decision_graph("dec_rec_timber_2023", "scen_timber_sign")


evidence_graph_v3_builder = EvidenceGraphV3Builder()
