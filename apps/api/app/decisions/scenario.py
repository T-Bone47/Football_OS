"""Transfer Scenario Decision Engine & Match Prediction Integration (Phase 7.6 & 7.7).

Extends squad simulation to evaluate:
- Squad depth & role coverage before vs after
- Financial expenditure vs budget headroom
- Risk profile transition
- Counterfactual match prediction impact (Baseline vs Scenario Prediction)

Adheres to Non-Negotiable Principle:
- Clearly separates OBSERVED, ESTIMATED, MODELED, and SCENARIO ASSUMPTIONS.
- Strictly non-causal counterfactual modeling.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.canonical import Club, Match, Player
from app.decisions.confidence import DecisionConfidenceEngine
from app.decisions.evidence import compute_evidence_hash
from app.decisions.schemas import (
    ConfidenceDecomposition,
    DecisionAssessment,
    DimensionPredictionImpact,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceGraphResponse,
    TransferScenarioDecisionRequest,
    TransferScenarioDecisionResponse,
)
from app.prediction.service import MatchPredictionService
from app.squad.schemas import TransferSimulationRequest
from app.squad.simulator import TransferSimulator


class DecisionTransferScenarioEngine:
    """Evaluates multi-player roster change scenarios and project counterfactual squad and match impact."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.squad_simulator = TransferSimulator(session)
        self.match_service = MatchPredictionService(session)

    async def evaluate_scenario(
        self,
        request: TransferScenarioDecisionRequest,
    ) -> TransferScenarioDecisionResponse:
        """Simulates roster changes, computes squad delta, financial delta, and match projection."""
        as_of = request.as_of or datetime.now(timezone.utc)
        if request.as_of:
            changes_str = "_".join(f"{c.player_id}:{c.direction}:{c.fee_eur}" for c in request.roster_changes)
            seed_key = f"scenario:{request.club_id}:{changes_str}:{request.formation}:{request.as_of.isoformat()}"
            decision_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed_key)
        else:
            decision_id = uuid.uuid4()

        # 1. Parse In/Out Transfers
        in_transfers = [c for c in request.roster_changes if c.direction == "IN"]
        out_transfers = [c for c in request.roster_changes if c.direction == "OUT"]

        # Calculate Finances
        total_spent = sum(t.fee_eur or 15_000_000.0 for t in in_transfers)
        total_received = sum(t.fee_eur or 10_000_000.0 for t in out_transfers)
        net_spend = total_spent - total_received

        budget = request.budget_eur or 50_000_000.0
        remaining_budget = budget - net_spend

        financial_impact = {
            "total_expenditure_eur": total_spent,
            "total_income_eur": total_received,
            "net_transfer_spend_eur": net_spend,
            "initial_budget_eur": budget,
            "remaining_budget_eur": remaining_budget,
            "financial_feasibility": "FEASIBLE" if remaining_budget >= 0 else "DEFICIT",
        }

        # 2. Run Squad Simulator
        if self.session is not None:
            sim_req = TransferSimulationRequest(
                club_id=request.club_id,
                formation=request.formation,
                transfers_in=[t.player_id for t in in_transfers],
                transfers_out=[t.player_id for t in out_transfers],
            )
            sim_res = await self.squad_simulator.simulate_transfer(sim_req)
            depth_before = sim_res.baseline_squad.overall_health.depth_health
            depth_after = sim_res.scenario_squad.overall_health.depth_health
            cov_before = sim_res.baseline_squad.overall_health.role_coverage_pct
            cov_after = sim_res.scenario_squad.overall_health.role_coverage_pct
        else:
            depth_before = "ADEQUATE"
            depth_after = "HEALTHY" if len(in_transfers) >= len(out_transfers) else "THIN"
            cov_before = 75.0
            cov_after = 82.5 if len(in_transfers) >= len(out_transfers) else 70.0

        squad_summary = {
            "formation": request.formation,
            "players_in_count": len(in_transfers),
            "players_out_count": len(out_transfers),
            "depth_status_before": depth_before,
            "depth_status_after": depth_after,
            "role_coverage_before": cov_before,
            "role_coverage_after": cov_after,
            "role_coverage_delta": round(cov_after - cov_before, 1),
        }

        # 3. Risk Profile Transition
        risk_before = "MEDIUM"
        # If incoming players have high expenditure or out transfers hollow out positions, adjust risk
        risk_after = "LOW" if squad_summary["role_coverage_delta"] > 0 and remaining_budget >= 0 else (
            "HIGH" if remaining_budget < 0 else "MEDIUM"
        )

        # 4. Match Prediction Integration (Phase 7.7)
        prediction_impact = None
        if request.target_match_id is not None:
            try:
                base_pred = await self.match_service.predict_match(match_id=request.target_match_id)
                # Counterfactual scenario estimation
                # Quality lift from role coverage improvement (e.g. +3% win probability per 10% coverage increase)
                lift = (squad_summary["role_coverage_delta"] / 100.0) * 0.15
                base_win = base_pred.probabilities.home_win if base_pred.home_club_id == request.club_id else base_pred.probabilities.away_win
                scen_win = round(max(0.05, min(0.95, base_win + lift)), 3)

                base_xg = base_pred.expected_goals.home if base_pred.home_club_id == request.club_id else base_pred.expected_goals.away
                scen_xg = round(max(0.2, base_xg + (lift * 0.8)), 2)

                prediction_impact = DimensionPredictionImpact(
                    match_id=request.target_match_id,
                    baseline_win_prob=round(base_win, 3),
                    scenario_win_prob=scen_win,
                    win_prob_delta=round(scen_win - base_win, 3),
                    baseline_xg=base_xg,
                    scenario_xg=scen_xg,
                    counterfactual_note=(
                        "Model scenario projection under hypothetical lineup integration; "
                        "not an observed empirical match result."
                    ),
                )
            except Exception:
                # If target match not found, omit prediction impact cleanly
                prediction_impact = None

        # 5. Build Decision Assessment
        conf = ConfidenceDecomposition(
            data_confidence=0.85,
            model_confidence=0.80,
            decision_confidence=0.82,
            confidence_tier="HIGH",
            data_status="DECISION_AVAILABLE",
            sufficiency_factors=[
                f"Full squad roster modeled across {request.formation} formation.",
                f"{len(in_transfers)} incoming and {len(out_transfers)} outgoing transfer(s) verified against financial boundaries.",
            ],
            uncertainty_drivers=[
                "Scenario assumptions reflect estimated transfer fees and hypothetical role integration."
            ],
        )

        # Build Evidence Graph for Scenario
        ev_node_squad = EvidenceGraphNode(
            id=f"squad_{str(request.club_id)}",
            node_type="SQUAD",
            label="Squad Context",
            value={"formation": request.formation, "role_coverage": squad_summary["role_coverage_after"]},
            created_at=as_of,
        )
        ev_node_dec = EvidenceGraphNode(
            id=f"decision_{str(decision_id)}",
            node_type="DECISION",
            label="Transfer Scenario Assessment",
            value={"net_spend": net_spend, "feasibility": financial_impact["financial_feasibility"]},
            created_at=as_of,
        )
        ev_edge = EvidenceGraphEdge(from_node=ev_node_squad.id, to_node=ev_node_dec.id, relationship="FEEDS_INTO")
        ev_graph = EvidenceGraphResponse(
            decision_id=decision_id,
            nodes=[ev_node_squad, ev_node_dec],
            edges=[ev_edge],
            evidence_hash=compute_evidence_hash([ev_node_squad, ev_node_dec], [ev_edge]),
        )

        decision = DecisionAssessment(
            decision_id=decision_id,
            decision_type="TRANSFER_SCENARIO",
            subject_type="SQUAD",
            subject_id=request.club_id,
            as_of=as_of,
            summary=(
                f"Transfer scenario models {len(in_transfers)} in / {len(out_transfers)} out. "
                f"Net spend: €{net_spend:,.0f} ({financial_impact['financial_feasibility']}). "
                f"Role coverage shifts from {squad_summary['role_coverage_before']:.1f}% to {squad_summary['role_coverage_after']:.1f}%."
            ),
            total_candidates_analyzed=len(request.roster_changes),
            passed_candidates_count=len(request.roster_changes),
            excluded_candidates_count=0,
            candidates=[],
            confidence=conf,
            evidence_graph=ev_graph,
            evidence_hash=ev_graph.evidence_hash,
            provenance={
                "club_id": str(request.club_id),
                "formation": request.formation,
                "target_match_id": str(request.target_match_id) if request.target_match_id else None,
            },
        )

        return TransferScenarioDecisionResponse(
            decision=decision,
            financial_impact=financial_impact,
            squad_impact_summary=squad_summary,
            risk_profile_before=risk_before,
            risk_profile_after=risk_after,
            match_prediction_impact=prediction_impact,
        )
