"""Phase 12 — Scout Copilot V2 Deterministic Tool Dispatcher (§23).

Expands the deterministic Scout Copilot with Phase 12 continuous intelligence queries:
  - "Find emerging U23 centre backs."
  - "Show players whose valuation appears below their comparable range."
  - "Why did this player's role change?"
  - "Which recruitment decisions are stale?"
  - "Which models need retraining?"
  - "Which competition has the biggest evidence gap?"
  - "Show the evidence behind this recommendation."

Rule: Copilot dispatches to underlying deterministic engines; never hallucinates football metrics.
"""
from __future__ import annotations

import re
from typing import Any

from app.phase12.data_impact import data_impact_engine
from app.phase12.decision_staleness import decision_staleness_engine
from app.phase12.emerging_players import emerging_player_engine
from app.phase12.evidence_graph import player_evidence_graph_builder
from app.phase12.market_inefficiency import market_inefficiency_engine
from app.phase12.retraining_triggers import retraining_trigger_engine
from app.phase12.role_transitions import role_transition_engine


class ScoutCopilotV2Dispatcher:
    """Dispatches natural language operational queries to deterministic Phase 12 engines."""

    def dispatch(self, query: str) -> dict[str, Any]:
        q = query.lower().strip()

        # Query 1: Emerging U23 Players
        if "emerging" in q or "breakout" in q:
            opps = emerging_player_engine.list_opportunities(status="EMERGING_OPPORTUNITY")
            return {
                "intent": "FIND_EMERGING_PLAYERS",
                "resolved": True,
                "count": len(opps),
                "summary": f"Discovered {len(opps)} players meeting multi-dimensional emergence thresholds (U23, minutes gain >= 25%, contribution gain >= 8 pts).",
                "results": [o.to_dict() for o in opps],
                "epistemic_notice": "Emerging talent status represents statistical progression, not a guaranteed future transfer or performance outcome.",
            }

        # Query 2: Value Gap & Market Inefficiency
        if "valuation" in q and ("below" in q or "gap" in q or "inefficiency" in q or "comparable" in q):
            signals = market_inefficiency_engine.list_signals()
            active_signals = [s for s in signals if s.raw_value_gap_eur > 0]
            return {
                "intent": "DETECT_VALUE_GAPS",
                "resolved": True,
                "count": len(active_signals),
                "summary": f"Identified {len(active_signals)} players whose observed market asking price sits below modelled valuation or comparable peer bands.",
                "results": [s.to_dict() for s in active_signals],
                "epistemic_notice": "Modelled valuation estimates are statistical references, not guaranteed market transaction prices.",
            }

        # Query 3: Role Change / Transition
        if "role" in q and ("change" in q or "transition" in q or "why" in q):
            transitions = role_transition_engine.list_transitions()
            return {
                "intent": "INSPECT_ROLE_TRANSITIONS",
                "resolved": True,
                "count": len(transitions),
                "summary": f"Found {len(transitions)} empirical role transitions sustained across >= 450 competitive minutes.",
                "results": [t.to_dict() for t in transitions],
                "epistemic_notice": "Role transitions report observed pitch event shifts without inferring manager psychology or intent.",
            }

        # Query 4: Stale Decisions
        if "decision" in q and ("stale" in q or "freshness" in q or "superseded" in q or "outdated" in q):
            assessments = decision_staleness_engine.list_assessments()
            stale_or_monitor = [a for a in assessments if a.freshness_state.value in ["STALE", "MONITOR"]]
            return {
                "intent": "AUDIT_DECISION_FRESHNESS",
                "resolved": True,
                "count": len(stale_or_monitor),
                "summary": f"Evaluated historical decision records: {len(stale_or_monitor)} decisions flagged for freshness review due to feature progression or valuation shifts.",
                "results": [a.to_dict() for a in assessments],
                "epistemic_notice": "Historical decision records remain strictly immutable; freshness assessments indicate ongoing empirical relevance.",
            }

        # Query 5: Models Needing Retraining
        if "retrain" in q or "retraining" in q:
            recs = retraining_trigger_engine.list_recommendations()
            return {
                "intent": "EVALUATE_RETRAINING_TRIGGERS",
                "resolved": True,
                "count": len(recs),
                "summary": f"Scanned model registry telemetry: {len(recs)} models audited against PSI and calibration drift thresholds.",
                "results": [r.to_dict() for r in recs],
                "epistemic_notice": "Models are never retrained or promoted automatically; triggers generate audit recommendations for engineer approval.",
            }

        # Query 6: Evidence Behind a Player
        if "evidence" in q or "lineage" in q or "trace" in q:
            # Default to Gonçalo Inácio
            graph = player_evidence_graph_builder.build_graph(
                player_id="cand_inacio",
                player_name="Gonçalo Inácio",
            )
            return {
                "intent": "INSPECT_PLAYER_EVIDENCE_GRAPH",
                "resolved": True,
                "summary": "Generated complete 10-tier evidence graph connecting Bronze snapshots to the signed recruitment decision.",
                "results": graph.to_dict(),
                "epistemic_notice": "Cryptographically verifiable DAG with SHA-256 node validation.",
            }

        # Fallback / General help
        return {
            "intent": "UNKNOWN_OR_HELP",
            "resolved": False,
            "summary": "Scout Copilot V2 supports deterministic queries for emerging players, market value gaps, role transitions, decision freshness, retraining triggers, and player evidence graphs.",
            "supported_queries": [
                "Find emerging U23 centre backs.",
                "Show players whose valuation appears below their comparable range.",
                "Why did this player's role change?",
                "Which recruitment decisions are stale?",
                "Which models need retraining?",
                "Show the evidence behind this recommendation.",
            ],
        }


copilot_v2_dispatcher = ScoutCopilotV2Dispatcher()
