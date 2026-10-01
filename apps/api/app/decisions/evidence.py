"""Decision Evidence Graph Engine (Phase 7.8).

Builds a traceable Directed Acyclic Graph (DAG) linking:
Player -> Contribution Snapshot -> Role Profile -> Tactical Fit -> Similarity
       -> Market Comparables -> Valuation -> Transfer Risk -> Squad Scenario
       -> Decision Assessment.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from app.decisions.schemas import (
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceGraphResponse,
    MultiDimensionalCandidateAssessment,
)


def compute_evidence_hash(nodes: list[EvidenceGraphNode], edges: list[EvidenceGraphEdge]) -> str:
    """Computes deterministic SHA-256 hash across canonical sorted nodes and edges."""
    node_tuples = sorted([(n.id, n.node_type, n.label, str(n.value), n.confidence, n.provenance) for n in nodes])
    edge_tuples = sorted([(e.from_node, e.to_node, e.relationship, e.weight) for e in edges])
    content = json.dumps({"nodes": node_tuples, "edges": edge_tuples}, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class DecisionEvidenceGraphBuilder:
    """Constructs auditable DAG representations of decision evidence."""

    @classmethod
    def build_graph_for_candidate(
        cls,
        decision_id: uuid.UUID,
        candidate: MultiDimensionalCandidateAssessment,
        replaced_player_name: str | None = None,
        as_of: datetime | None = None,
    ) -> EvidenceGraphResponse:
        """Constructs a fully traceable evidence subgraph for an evaluated candidate."""
        nodes: list[EvidenceGraphNode] = []
        edges: list[EvidenceGraphEdge] = []

        cid = str(candidate.candidate_id)
        p_node_id = f"player_{cid}"

        # 1. Player Node
        nodes.append(
            EvidenceGraphNode(
                id=p_node_id,
                node_type="PLAYER",
                label=f"Player: {candidate.player_name}",
                value={
                    "position": candidate.primary_position,
                    "age": candidate.age,
                    "minutes": candidate.minutes_played,
                    "club": candidate.current_club_name,
                },
                provenance="canonical.players",
            )
        )

        # 2. Contribution Node
        contrib_node_id = f"contrib_{cid}"
        nodes.append(
            EvidenceGraphNode(
                id=contrib_node_id,
                node_type="CONTRIBUTION",
                label=f"Contribution Rating: {candidate.performance.contribution_rating:.1f}",
                value={
                    "rating": candidate.performance.contribution_rating,
                    "percentile": candidate.performance.percentile_in_role,
                    "trajectory": candidate.performance.trajectory,
                },
                provenance="app.contributions.service",
            )
        )
        edges.append(
            EvidenceGraphEdge(from_node=p_node_id, to_node=contrib_node_id, relationship="FEEDS_INTO")
        )

        # 3. Role Profile Node
        role_node_id = f"role_{cid}"
        nodes.append(
            EvidenceGraphNode(
                id=role_node_id,
                node_type="ROLE",
                label=f"Role: {candidate.target_role}",
                value={"role_name": candidate.target_role},
                provenance="app.roles.service",
            )
        )
        edges.append(
            EvidenceGraphEdge(from_node=contrib_node_id, to_node=role_node_id, relationship="FEEDS_INTO")
        )

        # 4. Tactical Fit Node
        tactical_node_id = f"tactical_{cid}"
        nodes.append(
            EvidenceGraphNode(
                id=tactical_node_id,
                node_type="TACTICAL_FIT",
                label=f"Tactical Fit: {candidate.tactical.tactical_fit_score:.1f}/100",
                value={
                    "system": candidate.tactical.system_name,
                    "compatibility": candidate.tactical.role_compatibility,
                },
                provenance="app.tactical.service",
            )
        )
        edges.append(
            EvidenceGraphEdge(from_node=role_node_id, to_node=tactical_node_id, relationship="FEEDS_INTO")
        )

        # 5. Similarity Node (if applicable)
        if candidate.similarity.comparison_target_name or replaced_player_name:
            target_name = candidate.similarity.comparison_target_name or replaced_player_name
            sim_node_id = f"sim_{cid}"
            nodes.append(
                EvidenceGraphNode(
                    id=sim_node_id,
                    node_type="SIMILARITY",
                    label=f"Similarity to {target_name}: {candidate.similarity.overall_similarity * 100:.1f}%",
                    value={
                        "overall": candidate.similarity.overall_similarity,
                        "statistical": candidate.similarity.statistical_similarity,
                        "role": candidate.similarity.role_similarity,
                    },
                    provenance="app.roles.similarity",
                )
            )
            edges.append(
                EvidenceGraphEdge(from_node=p_node_id, to_node=sim_node_id, relationship="FEEDS_INTO")
            )

        # 6. Valuation Node
        val_node_id = f"val_{cid}"
        nodes.append(
            EvidenceGraphNode(
                id=val_node_id,
                node_type="VALUATION",
                label=f"Estimated Valuation: €{candidate.market.estimated_value_eur:,.0f}",
                value={
                    "valuation": candidate.market.estimated_value_eur,
                    "range": [candidate.market.fee_range_low_eur, candidate.market.fee_range_high_eur],
                    "affordability": candidate.market.affordability_status,
                },
                provenance="app.market.valuation",
            )
        )
        edges.append(
            EvidenceGraphEdge(from_node=p_node_id, to_node=val_node_id, relationship="FEEDS_INTO")
        )

        # 7. Transfer Risk Node
        risk_node_id = f"risk_{cid}"
        nodes.append(
            EvidenceGraphNode(
                id=risk_node_id,
                node_type="RISK",
                label=f"Risk Level: {candidate.risk.risk_level} ({candidate.risk.overall_risk_score:.2f})",
                value={
                    "overall_risk": candidate.risk.overall_risk_score,
                    "performance_risk": candidate.risk.performance_risk,
                    "adaptation_risk": candidate.risk.adaptation_risk,
                    "financial_risk": candidate.risk.financial_risk,
                    "availability_risk": candidate.risk.availability_risk,
                },
                provenance="app.market.risk",
            )
        )
        edges.append(
            EvidenceGraphEdge(from_node=val_node_id, to_node=risk_node_id, relationship="FEEDS_INTO")
        )

        # 8. Squad Impact Node
        squad_node_id = f"squad_{cid}"
        nodes.append(
            EvidenceGraphNode(
                id=squad_node_id,
                node_type="SQUAD",
                label=f"Squad Impact: {candidate.squad_impact.depth_status_before} → {candidate.squad_impact.depth_status_after}",
                value={
                    "slot": candidate.squad_impact.formation_slot,
                    "net_upgrade": candidate.squad_impact.net_squad_upgrade,
                },
                provenance="app.squad.service",
            )
        )
        edges.append(
            EvidenceGraphEdge(from_node=tactical_node_id, to_node=squad_node_id, relationship="FEEDS_INTO")
        )

        # 9. Top-Level Decision Assessment Node
        dec_node_id = f"decision_{str(decision_id)}"
        nodes.append(
            EvidenceGraphNode(
                id=dec_node_id,
                node_type="DECISION",
                label=f"Decision Assessment ({candidate.confidence.confidence_tier} Confidence)",
                value={
                    "status": candidate.confidence.data_status,
                    "decision_confidence": candidate.confidence.decision_confidence,
                },
                provenance="app.decisions.service",
            )
        )

        edges.append(EvidenceGraphEdge(from_node=squad_node_id, to_node=dec_node_id, relationship="SUPPORTS"))
        edges.append(EvidenceGraphEdge(from_node=risk_node_id, to_node=dec_node_id, relationship="CONSTRAINS"))

        ev_hash = compute_evidence_hash(nodes, edges)

        return EvidenceGraphResponse(
            decision_id=decision_id,
            nodes=nodes,
            edges=edges,
            evidence_hash=ev_hash,
        )
