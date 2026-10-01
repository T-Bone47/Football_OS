"""Research Evidence Graph Builder for Phase 15.

Builds cryptographically verifiable research lineage graphs connecting:
- RESEARCH_QUESTION
- RESEARCH_HYPOTHESIS
- RESEARCH_COHORT
- RESEARCH_DATASET
- RESEARCH_EXPERIMENT
- RESEARCH_VALIDATION
- FEATURE_CANDIDATE
- PROMOTION_RECORD

Generates deterministic SHA-256 graph digest.
"""

import hashlib
import json
from typing import Any
from pydantic import BaseModel, Field
from app.phase15 import EpistemicModality


class ResearchGraphNode(BaseModel):
    node_id: str
    node_type: str  # QUESTION, HYPOTHESIS, COHORT, DATASET, EXPERIMENT, VALIDATION, FEATURE, PROMOTION
    label: str
    epistemic_status: EpistemicModality
    provenance: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ResearchGraphEdge(BaseModel):
    source_id: str
    target_id: str
    edge_type: str  # FRAMES, DERIVED_FROM, EVALUATED_BY, VALIDATED_BY, PROMOTES, CONTRADICTS
    weight: float = 1.0


class ResearchEvidenceGraph(BaseModel):
    graph_id: str
    nodes: list[ResearchGraphNode]
    edges: list[ResearchGraphEdge]
    graph_digest: str
    node_count: int
    edge_count: int


class ResearchEvidenceGraphBuilder:
    """Builds and serializes reproducible research lineage graphs."""

    @staticmethod
    def build_graph(
        graph_id: str,
        nodes: list[ResearchGraphNode],
        edges: list[ResearchGraphEdge],
    ) -> ResearchEvidenceGraph:
        sorted_nodes = sorted(nodes, key=lambda n: n.node_id)
        sorted_edges = sorted(edges, key=lambda e: (e.source_id, e.target_id, e.edge_type))

        node_repr = [
            {"id": n.node_id, "type": n.node_type, "modality": n.epistemic_status.value}
            for n in sorted_nodes
        ]
        edge_repr = [
            {"src": e.source_id, "tgt": e.target_id, "type": e.edge_type}
            for e in sorted_edges
        ]

        raw_canonical = json.dumps({"nodes": node_repr, "edges": edge_repr}, sort_keys=True)
        digest = hashlib.sha256(raw_canonical.encode("utf-8")).hexdigest()

        return ResearchEvidenceGraph(
            graph_id=graph_id,
            nodes=sorted_nodes,
            edges=sorted_edges,
            graph_digest=digest,
            node_count=len(sorted_nodes),
            edge_count=len(sorted_edges),
        )
