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
from datetime import datetime
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
    """Constructs auditable DAG representations of decision evidence.

    Phase 18 (R23): a node exists only for evidence the assessment actually
    holds. A missing dimension is a GAP node carrying its status, so the
    graph never implies evidence that was not there.
    """

    @classmethod
    def build_graph_for_candidate(
        cls,
        decision_id: uuid.UUID,
        candidate: MultiDimensionalCandidateAssessment,
        replaced_player_name: str | None = None,
        as_of: datetime | None = None,
    ) -> EvidenceGraphResponse:
        nodes: list[EvidenceGraphNode] = []
        edges: list[EvidenceGraphEdge] = []
        cid = str(candidate.candidate_id)
        status = candidate.dimension_status
        p_node_id = f"player_{cid}"
        dec_node_id = f"decision_{decision_id}"
        nodes.append(EvidenceGraphNode(
            id=p_node_id, node_type="PLAYER", label=f"Player: {candidate.player_name}",
            value={"position": candidate.primary_position, "age": candidate.age,
                   "minutes": candidate.minutes_played, "club": candidate.current_club_name,
                   "age_status": status.get("age"), "minutes_status": status.get("minutes")},
            provenance="canonical.players"))

        def add(dim: str, node_type: str, label: str | None, value: Any, provenance: str, rel: str = "SUPPORTS") -> None:
            node_id = f"{dim}_{cid}"
            if label is None:  # no evidence: record the gap, it supports nothing
                nodes.append(EvidenceGraphNode(id=node_id, node_type="GAP", label=f"{dim}: {status.get(dim, 'NOT_ASSESSED')}",
                                               value={"dimension": dim, "status": status.get(dim, "NOT_ASSESSED")},
                                               confidence=0.0, provenance="app.decisions.candidate_evidence"))
                edges.append(EvidenceGraphEdge(from_node=node_id, to_node=dec_node_id, relationship="QUALIFIES"))
                return
            nodes.append(EvidenceGraphNode(id=node_id, node_type=node_type, label=label,
                                           value={**value, "status": status.get(dim)}, provenance=provenance))
            edges.append(EvidenceGraphEdge(from_node=p_node_id, to_node=node_id, relationship="FEEDS_INTO"))
            edges.append(EvidenceGraphEdge(from_node=node_id, to_node=dec_node_id, relationship=rel))

        perf = candidate.performance
        add("performance", "CONTRIBUTION", perf and f"Contribution Rating: {perf.contribution_rating:.1f}",
            perf and {"rating": perf.contribution_rating, "percentile": perf.percentile_in_role,
                      "sample_minutes": perf.sample_minutes, "sample_matches": perf.sample_matches},
            "player_contribution_snapshots")
        tac = candidate.tactical
        add("tactical", "TACTICAL_FIT", tac and f"Tactical Fit: {tac.tactical_fit_score:.1f}/100",
            tac and {"system": tac.system_name, "role": tac.target_role, "compatibility": tac.role_compatibility},
            "player_tactical_fits")
        sim = candidate.similarity
        target = (sim and sim.comparison_target_name) or replaced_player_name
        add("similarity", "SIMILARITY", sim and f"Similarity to {target}: {sim.overall_similarity * 100:.1f}%",
            sim and {"overall": sim.overall_similarity, "statistical": sim.statistical_similarity,
                     "role": sim.role_similarity}, "player_role_profiles")
        mkt = candidate.market
        add("market", "VALUATION", mkt and f"Valuation: €{mkt.estimated_value_eur:,.0f}",
            mkt and {"valuation": mkt.estimated_value_eur, "range": [mkt.fee_range_low_eur, mkt.fee_range_high_eur],
                     "affordability": mkt.affordability_status}, "caller_supplied")
        risk = candidate.risk
        add("risk", "RISK", risk and f"Risk Level: {risk.risk_level} ({risk.overall_risk_score:.2f})",
            risk and {"overall_risk": risk.overall_risk_score, "performance_risk": risk.performance_risk,
                      "adaptation_risk": risk.adaptation_risk, "financial_risk": risk.financial_risk,
                      "availability_risk": risk.availability_risk}, "app.market.risk", rel="CONSTRAINS")
        sq = candidate.squad_impact
        add("squad_impact", "SQUAD", sq and f"Squad Impact: {sq.depth_status_before} → {sq.depth_status_after}",
            sq and {"slot": sq.formation_slot, "net_upgrade": sq.net_squad_upgrade}, "caller_supplied")

        nodes.append(EvidenceGraphNode(
            id=dec_node_id, node_type="DECISION",
            label=f"Decision Assessment ({candidate.ranking_status}, {candidate.confidence.confidence_tier} confidence)",
            value={"ranking_status": candidate.ranking_status, "ranking_score": candidate.ranking_score,
                   "data_status": candidate.confidence.data_status,
                   "decision_confidence": candidate.confidence.decision_confidence,
                   "hard_constraints": candidate.hard_constraints.checks},
            provenance="app.decisions.service"))
        return EvidenceGraphResponse(decision_id=decision_id, nodes=nodes, edges=edges,
                                     evidence_hash=compute_evidence_hash(nodes, edges))
