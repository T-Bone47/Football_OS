"""Transfer Scenario Decision Engine (Phase 7.6, rebuilt in Phase 18 for R22/R24).

A scenario is a COUNTERFACTUAL: it applies the requested roster changes to
the club's stored roster (season stats and lineups at or before as_of) and
reports what the declared squad rules say about depth and coverage.

- Fees and budget are SCENARIO ASSUMPTIONS supplied by the caller. A missing
  fee is unknown; it is never replaced with a default price.
- Squad depth and coverage are MODELLED by a declared rule (app.squad), not
  by a validated model.
- Match prediction impact is NOT_MODELLED: the registered match model has
  no player-level features, so a lineup change cannot move its output.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Club
from app.decisions.evidence import compute_evidence_hash
from app.decisions.schemas import (
    ConfidenceDecomposition,
    DecisionAssessment,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceGraphResponse,
    TransferScenarioDecisionRequest,
    TransferScenarioDecisionResponse,
)
from app.squad.schemas import TransferSimulationRequest
from app.squad.simulator import TransferSimulator

PREDICTION_NOT_MODELLED = ("NOT_MODELLED: the registered match model uses team-level pre-match features only; "
                           "a roster change cannot be propagated into its probabilities.")


class DecisionTransferScenarioEngine:
    """Applies roster changes to the stored squad; every output carries its modality."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def evaluate_scenario(self, request: TransferScenarioDecisionRequest) -> TransferScenarioDecisionResponse:
        as_of = request.as_of or datetime.now(timezone.utc)
        if request.as_of:
            changes_str = "_".join(f"{c.player_id}:{c.direction}:{c.fee_eur}" for c in request.roster_changes)
            seed_key = f"scenario:{request.club_id}:{changes_str}:{request.formation}:{request.as_of.isoformat()}"
            decision_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_key)
        else:
            decision_id = uuid.uuid4()

        ins = [c for c in request.roster_changes if c.direction == "IN"]
        outs = [c for c in request.roster_changes if c.direction == "OUT"]

        # Finances: caller-supplied assumptions only.
        fees_known = all(c.fee_eur is not None for c in request.roster_changes)
        spent = sum(c.fee_eur for c in ins if c.fee_eur is not None)
        received = sum(c.fee_eur for c in outs if c.fee_eur is not None)
        net = round(spent - received, 2) if fees_known else None
        remaining = round(request.budget_eur - net, 2) if net is not None and request.budget_eur is not None else None
        financial_impact = {
            "modality": "SCENARIO_ASSUMPTION",
            "fees_supplied_for": [str(c.player_id) for c in request.roster_changes if c.fee_eur is not None],
            "fees_missing_for": [str(c.player_id) for c in request.roster_changes if c.fee_eur is None],
            "total_expenditure_eur": spent if all(c.fee_eur is not None for c in ins) else None,
            "total_income_eur": received if all(c.fee_eur is not None for c in outs) else None,
            "net_transfer_spend_eur": net,
            "initial_budget_eur": request.budget_eur,
            "remaining_budget_eur": remaining,
            "financial_feasibility": ("UNKNOWN" if remaining is None else ("FEASIBLE" if remaining >= 0 else "DEFICIT")),
        }

        # Squad: the stored roster with the changes applied.
        squad_summary: dict = {"modality": "SCENARIO", "formation": request.formation,
                               "players_in_count": len(ins), "players_out_count": len(outs)}
        risk_before = risk_after = "NOT_ASSESSED"
        club_name = None
        if self.session is not None:
            club = (await self.session.execute(select(Club).where(Club.id == request.club_id))).scalar_one_or_none()
            if club is None:
                raise ValueError(f"Club with ID {request.club_id} not found.")
            club_name = club.name
            sim = await TransferSimulator(self.session).simulate_transfer(
                TransferSimulationRequest(club_id=request.club_id, formation=request.formation,
                                          incoming_player_ids=[c.player_id for c in ins],
                                          outgoing_player_ids=[c.player_id for c in outs]),
                as_of=as_of,
            )
            before, after = sim.before, sim.after
            found_in = {p.player_id for p in sim.incoming_players}
            squad_summary.update({
                "status": before.status,
                "squad_source": before.squad_source,
                "roster_size_before": before.total_players,
                "roster_size_after": after.total_players,
                "outgoing_not_in_roster": [str(c.player_id) for c in outs
                                           if c.player_id not in {p.player_id for p in sim.outgoing_players}],
                "incoming_not_found": [str(c.player_id) for c in ins if c.player_id not in found_in],
                "depth_status_before": before.depth_risk_level if before.total_players else "NO_SQUAD_DATA",
                "depth_status_after": after.depth_risk_level if after.total_players else "NO_SQUAD_DATA",
                "role_coverage_before": before.role_coverage_score,
                "role_coverage_after": after.role_coverage_score,
                "role_coverage_delta": round(after.role_coverage_score - before.role_coverage_score, 3),
                "key_gaps_after": after.key_gaps,
                "assumptions": before.assumptions,
            })
            if before.total_players:
                risk_before, risk_after = before.depth_risk_level, after.depth_risk_level
        else:
            squad_summary["status"] = "NOT_ASSESSED"

        observed = [fees_known, request.budget_eur is not None, squad_summary.get("roster_size_before", 0) > 0]
        data_conf = round(sum(observed) / len(observed), 2)
        drivers = ["Squad depth and coverage come from a declared rule, not a validated model.",
                   PREDICTION_NOT_MODELLED]
        if not fees_known:
            drivers.append("One or more fees were not supplied; spend and feasibility are UNKNOWN.")
        if not squad_summary.get("roster_size_before"):
            drivers.append("No stored roster for this club at as_of.")
        conf = ConfidenceDecomposition(
            data_confidence=data_conf, model_confidence=0.0, decision_confidence=0.0,
            confidence_tier="VERY_LOW", data_status="SCENARIO_ASSUMPTIONS",
            sufficiency_factors=[f"{len(ins)} incoming and {len(outs)} outgoing change(s) applied to the stored roster."],
            uncertainty_drivers=drivers,
        )

        squad_node = EvidenceGraphNode(id=f"squad_{request.club_id}", node_type="SQUAD", label="Stored roster (scenario)",
                                       value={k: squad_summary.get(k) for k in ("status", "roster_size_before",
                                                                                "role_coverage_after")},
                                       provenance="app.squad.service", created_at=as_of)
        fin_node = EvidenceGraphNode(id=f"finance_{decision_id}", node_type="SCENARIO", label="Caller-supplied fees",
                                     value={"net_spend": net, "feasibility": financial_impact["financial_feasibility"]},
                                     provenance="request", created_at=as_of)
        dec_node = EvidenceGraphNode(id=f"decision_{decision_id}", node_type="DECISION",
                                     label="Transfer Scenario Assessment (COUNTERFACTUAL)",
                                     value={"net_spend": net, "feasibility": financial_impact["financial_feasibility"]},
                                     created_at=as_of)
        edges = [EvidenceGraphEdge(from_node=squad_node.id, to_node=dec_node.id, relationship="COUNTERFACTUAL"),
                 EvidenceGraphEdge(from_node=fin_node.id, to_node=dec_node.id, relationship="COUNTERFACTUAL")]
        nodes = [squad_node, fin_node, dec_node]
        graph = EvidenceGraphResponse(decision_id=decision_id, nodes=nodes, edges=edges,
                                      evidence_hash=compute_evidence_hash(nodes, edges))

        spend_txt = f"€{net:,.0f}" if net is not None else "UNKNOWN (fees not supplied)"
        cov_txt = (f"Role coverage {squad_summary['role_coverage_before']:.2f} → {squad_summary['role_coverage_after']:.2f}."
                   if "role_coverage_before" in squad_summary else "Squad impact NOT_ASSESSED.")
        decision = DecisionAssessment(
            decision_id=decision_id, decision_type="TRANSFER_SCENARIO", subject_type="SQUAD",
            subject_id=request.club_id, as_of=as_of,
            summary=(f"COUNTERFACTUAL: {len(ins)} in / {len(outs)} out for {club_name or request.club_id}. "
                     f"Net spend: {spend_txt} ({financial_impact['financial_feasibility']}). {cov_txt}"),
            total_candidates_analyzed=len(request.roster_changes),
            passed_candidates_count=0, excluded_candidates_count=0, candidates=[],
            confidence=conf, evidence_graph=graph, evidence_hash=graph.evidence_hash,
            provenance={"club_id": str(request.club_id), "formation": request.formation, "modality": "COUNTERFACTUAL",
                        "target_match_id": str(request.target_match_id) if request.target_match_id else None,
                        "match_prediction_impact": PREDICTION_NOT_MODELLED},
        )
        return TransferScenarioDecisionResponse(
            decision=decision, financial_impact=financial_impact, squad_impact_summary=squad_summary,
            risk_profile_before=risk_before, risk_profile_after=risk_after, match_prediction_impact=None,
        )
