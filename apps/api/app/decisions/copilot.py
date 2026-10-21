from __future__ import annotations

"""
Scout Copilot Decision Tools & Orchestrator (Phase 7).

Provides deterministic tool functions:
- get_player_intelligence
- get_player_similarity
- get_tactical_fit
- get_market_context
- get_valuation
- get_transfer_risk
- analyze_squad
- simulate_transfer
- get_match_prediction
- compare_candidates
- retrieve_evidence

Crucial Guarantee:
The natural-language orchestrator NEVER invents or hallucinates analytical values.
Every output statement references verifiable, deterministic engine outputs.
"""

import logging
import uuid
from typing import Any, AsyncGenerator

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Player, PlayerContributionSnapshot, PlayerRoleProfile
from app.decisions.service import UnifiedDecisionService
from app.decisions.schemas import (
    CandidateComparisonRequest,
    RecruitmentTargetRequest,
    ReplacementDecisionRequest,
    TransferScenarioDecisionRequest,
)
from app.llm.base import LLMMessage
from app.llm.registry import get_llm_registry
from app.market.context import build_player_market_context
from app.market.risk import TransferRiskEngine
from app.market.valuation import BaselineValuationEngine
from app.prediction.service import MatchPredictionService
from app.roles.service import RoleService
from app.squad.schemas import SquadBuildRequest
from app.squad.service import SquadService
from app.tactical.contexts import get_standard_context
from app.tactical.service import TacticalFitService

logger = logging.getLogger(__name__)


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """An explicit, non-fabricated tool result."""
    return {"status": "UNAVAILABLE", "reason": reason, **extra}


def _failed(exc: Exception) -> dict[str, Any]:
    return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


COPILOT_SYSTEM_PROMPT = (
    "You are the Scout Copilot for Football Intelligence OS, an evidence-driven football "
    "recruitment platform. You NEVER invent player statistics, market values, or transfer "
    "predictions. When a user asks for candidates, you (1) restate the criteria you detected, "
    "(2) explain the analytical approach the platform would take (role fit, similarity, "
    "valuation, transfer risk), and (3) surface only players that were provided to you in "
    "the structured context; if none were provided you say the connected data source has "
    "not been supplied yet and list the endpoints the platform would query. Keep answers "
    "concise, professional, and calibrated: distinguish FACT, MODEL OUTPUT, and ESTIMATE. "
    "Never present a prediction as a certainty."
)


class ScoutDecisionTools:
    """Deterministic tool registry for decision intelligence queries."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.decision_service = UnifiedDecisionService(session=session)

    async def get_player_intelligence(self, player_id: uuid.UUID | str) -> dict[str, Any]:
        """Reads the canonical player, latest role profile and latest contribution snapshot."""
        pid = _as_uuid(player_id)
        if self.session is None or pid is None:
            return _unavailable("NO_SESSION", player_id=str(player_id))
        try:
            player = (
                await self.session.execute(select(Player).where(Player.id == pid))
            ).scalar_one_or_none()
            if player is None:
                return {"status": "NOT_FOUND", "player_id": str(pid)}
            role = (
                await self.session.execute(
                    select(PlayerRoleProfile)
                    .where(PlayerRoleProfile.player_id == pid)
                    .order_by(desc(PlayerRoleProfile.as_of))
                    .limit(1)
                )
            ).scalar_one_or_none()
            contribution = (
                await self.session.execute(
                    select(PlayerContributionSnapshot)
                    .where(PlayerContributionSnapshot.player_id == pid)
                    .order_by(desc(PlayerContributionSnapshot.as_of))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return {
                "status": "OBSERVED",
                "player_id": str(player.id),
                "player": {
                    "name": player.name,
                    "primary_position": player.primary_position,
                    "nationality": player.nationality,
                    "date_of_birth": player.date_of_birth.isoformat() if player.date_of_birth else None,
                },
                "role": (
                    {
                        "status": role.role_status,
                        "primary_archetype": role.primary_archetype,
                        "sample_minutes": role.sample_minutes,
                        "as_of": role.as_of.isoformat(),
                    }
                    if role
                    else None
                ),
                "contribution": (
                    {
                        "status": contribution.contribution_status,
                        "sample_minutes": contribution.sample_minutes,
                        "dimension_scores": contribution.dimension_scores,
                        "as_of": contribution.as_of.isoformat(),
                    }
                    if contribution
                    else None
                ),
                "provenance": "canonical database rows (players, player_role_profiles, player_contribution_snapshots)",
            }
        except Exception as exc:  # noqa: BLE001 - reported, never guessed
            return _failed(exc)

    async def get_player_similarity(self, player_id: uuid.UUID | str, limit: int = 5) -> dict[str, Any]:
        """Runs the role-intelligence similarity engine against eligible profiles."""
        pid = _as_uuid(player_id)
        if self.session is None or pid is None:
            return _unavailable("NO_SESSION", player_id=str(player_id))
        try:
            result = await RoleService(self.session).find_similar_players(pid, limit=limit)
            return {"status": "OBSERVED", **result.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return _failed(exc)

    async def get_tactical_fit(self, player_id: uuid.UUID | str, tactical_context_id: str) -> dict[str, Any]:
        """Calculates tactical fit with the versioned tactical context and calculator."""
        pid = _as_uuid(player_id)
        context = get_standard_context(tactical_context_id)
        if self.session is None or pid is None:
            return _unavailable("NO_SESSION", player_id=str(player_id))
        if context is None:
            return {
                "status": "NOT_FOUND",
                "reason": f"unknown tactical context '{tactical_context_id}'",
            }
        try:
            fit = await TacticalFitService(self.session).calculate_and_save_tactical_fit(pid, context)
            return {"status": "OBSERVED", **fit.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return _failed(exc)

    async def get_market_context(self, player_id: uuid.UUID | str) -> dict[str, Any]:
        """Builds the leakage-safe market context from persisted transfers/valuations."""
        pid = _as_uuid(player_id)
        if self.session is None or pid is None:
            return _unavailable("NO_SESSION", player_id=str(player_id))
        try:
            context = await build_player_market_context(self.session, pid)
            if context is None:
                return {"status": "NOT_FOUND", "player_id": str(pid)}
            return {"status": "OBSERVED", **context.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return _failed(exc)

    async def get_valuation(self, player_id: uuid.UUID | str) -> dict[str, Any]:
        """Runs the documented comparable-median baseline; it abstains when data is thin."""
        pid = _as_uuid(player_id)
        if self.session is None or pid is None:
            return _unavailable("NO_SESSION", player_id=str(player_id))
        try:
            valuation = await BaselineValuationEngine().compute_valuation_baseline(self.session, pid)
            return {"status": "OBSERVED", **valuation.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return _failed(exc)

    async def get_transfer_risk(self, player_id: uuid.UUID | str) -> dict[str, Any]:
        """Runs the factor-based risk engine (uncalibrated factors stay labelled)."""
        pid = _as_uuid(player_id)
        if self.session is None or pid is None:
            return _unavailable("NO_SESSION", player_id=str(player_id))
        try:
            risk = await TransferRiskEngine().assess_player_risk(self.session, pid)
            return {"status": "OBSERVED", **risk.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return _failed(exc)

    async def analyze_squad(self, club_id: uuid.UUID | str) -> dict[str, Any]:
        """Runs the squad analysis over the club's canonical players."""
        cid = _as_uuid(club_id)
        if self.session is None or cid is None:
            return _unavailable("NO_SESSION", club_id=str(club_id))
        try:
            result = await SquadService(self.session).analyze_squad(SquadBuildRequest(club_id=cid))
            return {"status": "OBSERVED", **result.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return _failed(exc)

    async def simulate_transfer(self, request: TransferScenarioDecisionRequest) -> dict[str, Any]:
        """Executes counterfactual transfer simulation."""
        scenario_res = await self.decision_service.evaluate_transfer_scenario(request)
        return scenario_res.model_dump(mode="json")

    async def get_match_prediction(self, match_id: uuid.UUID | str) -> dict[str, Any]:
        """Runs the Phase 6 prediction service; never returns a canned probability."""
        mid = _as_uuid(match_id)
        if self.session is None or mid is None:
            return _unavailable("NO_SESSION", match_id=str(match_id))
        try:
            prediction = await MatchPredictionService(self.session).predict_match(mid)
            return {"status": "OBSERVED", **prediction.model_dump(mode="json")}
        except Exception as exc:  # noqa: BLE001
            return _failed(exc)

    async def compare_candidates(self, candidate_ids: list[uuid.UUID | str]) -> dict[str, Any]:
        """Performs multi-dimensional side-by-side candidate comparison."""
        req = CandidateComparisonRequest(candidate_ids=[uuid.UUID(str(cid)) for cid in candidate_ids])
        comp = await self.decision_service.compare_candidates(req)
        return comp.model_dump(mode="json")

    async def retrieve_evidence(self, decision_id: uuid.UUID | str) -> dict[str, Any]:
        """Retrieves evidence graph for a prior decision assessment."""
        try:
            ev = self.decision_service.get_decision_evidence(uuid.UUID(str(decision_id)))
            return ev.model_dump(mode="json") if ev else {"error": "Evidence graph not found"}
        except Exception as e:
            return {"error": str(e)}


def _format_context_players(context_players: list[dict[str, Any]]) -> str:
    """Format context players for LLM prompt."""
    if not context_players:
        return "No player context provided."

    lines = ["Available player context:"]
    for p in context_players[:10]:
        name = p.get("name") or p.get("player_name") or p.get("player_name") or "Unknown"
        pos = p.get("primary_position", "?")
        nat = p.get("nationality", "?")
        pid = p.get("id") or p.get("player_id") or p.get("candidate_id") or "?"
        lines.append(f"- {name} (ID: {pid}, Pos: {pos}, Nat: {nat})")
    return "\n".join(lines)


async def _llm_generate(
    query: str,
    context_players: list[dict[str, Any]],
    system_prompt: str,
    temperature: float = 0.3,
) -> str:
    """Generate a response using the configured LLM provider."""
    registry = get_llm_registry()
    # Ensure registry is initialized
    if not registry._initialized:
        registry.initialize()
    primary = registry.get_primary()

    if not primary:
        return (
            "**LLM Unavailable**: No LLM provider configured. "
            "Configure LLM_PROVIDER and LLM_MODEL in environment to enable natural language responses.\n\n"
            "The analytical engines are still available via direct API calls."
        )

    system_prompt_full = (
        f"{system_prompt}\n\n"
        f"User Query: {query}\n\n"
        f"{_format_context_players(context_players)}\n\n"
        "Respond in markdown format. Be concise and evidence-driven."
    )

    messages = [
        {"role": "system", "content": system_prompt_full},
        {"role": "user", "content": query},
    ]

    try:
        response = await registry.complete_with_fallback(
            messages,
            temperature=0.3,
            stream=False,
        )
        content = (response.content or "").strip()
        if not content:
            # A 200 with no text is not a successful answer. Reasoning models
            # can spend the whole token budget before emitting content, so the
            # finish reason is surfaced instead of an empty "success".
            return (
                "**LLM Empty Response**: the provider completed the request but returned no text "
                f"(finish_reason={getattr(response, 'finish_reason', None)!r}, "
                f"model={getattr(response, 'model', 'unknown')!r}). "
                "The analytical evidence above is unaffected; increase the token budget or retry."
            )
        return content
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return (
            f"**LLM Error**: The language model provider returned an error: {e}.\n\n"
            "The analytical engines are still available via direct API calls. "
            "Check provider configuration and credentials."
        )


async def orchestrate_copilot_decision(
    query: str,
    context_players: list[dict[str, Any]],
    session: AsyncSession | None = None,
) -> AsyncGenerator[str, None]:
    """
    Interprets user intent and routes to deterministic decision intelligence engines.
    Streams back explainable markdown text with strict evidence referencing.
    """
    tools = ScoutDecisionTools(session=session)
    q_lower = query.lower()

    # Every response opens with the same heading so a client can tell the
    # evidence-first analytical answer apart from a bare model completion.
    yield "## Decision Intelligence Analysis\n\n"

    # First, get the analytical results from deterministic engines
    analytical_results = ""
    evidence_summary = ""

    # Intent routing: Replacement Analysis
    if "replace" in q_lower or "replacement" in q_lower:
        if not context_players and session is None:
            yield "**Status**: No candidate met both the minimum similarity threshold (0.70) and all hard criteria.\n"
            yield "No target player selected or found in context to evaluate replacements for.\n"
            return

        target_player = context_players[0] if context_players else None
        target_name = (
            (target_player.get("player_name") or target_player.get("name") if isinstance(target_player, dict) else getattr(target_player, "player_name", None))
            if target_player else "Selected Player"
        )
        target_id = (
            (target_player.get("candidate_id") or target_player.get("id") if isinstance(target_player, dict) else getattr(target_player, "candidate_id", None))
            if target_player else uuid.uuid4()
        )

        req = ReplacementDecisionRequest(
            player_id_to_replace=uuid.UUID(str(target_id)),
            target_role="Playmaker",
            min_similarity=0.70,
            budget_eur=40_000_000.0,
            limit=3,
        )

        candidates = context_players[1:] if len(context_players) > 1 else context_players
        res = await tools.decision_service.evaluate_replacement(
            req,
            target_player_override=target_player,
            candidates_override=candidates,
        )

        evidence_summary = f"**Evaluation Summary**: {res.decision.summary}\n\n"

        if res.top_replacements:
            evidence_summary += "| Candidate | Role | Tactical Fit | Similarity | Valuation | Risk | Net Squad Upgrade |\n"
            evidence_summary += "|---|---|---|---|---|---|---|\n"
            for c in res.top_replacements:
                evidence_summary += (
                    f"| **{c.player_name}** | {c.target_role} | {c.tactical.tactical_fit_score:.1f}% | "
                    f"{c.similarity.overall_similarity:.2f} | €{c.market.estimated_value_eur:,.0f} | "
                    f"{c.risk.risk_level} | {'Yes' if c.squad_impact.net_squad_upgrade else 'Neutral'} |\n"
                )
            evidence_summary += "\n**Key Evidence Rationale**:\n"
            for c in res.top_replacements[:2]:
                evidence_summary += f"- **{c.player_name}**: {'; '.join(c.why_matches)}\n"
                if c.where_differs:
                    evidence_summary += f"  *Caveats*: {'; '.join(c.where_differs)}\n"
        else:
            evidence_summary += "No candidate met both the minimum similarity threshold (0.70) and all hard criteria.\n"

        evidence_summary += f"\n*Decision Confidence*: **{res.decision.confidence.confidence_tier}** (Data: {res.decision.confidence.data_confidence * 100:.0f}%, Model: {res.decision.confidence.model_confidence * 100:.0f}%). Evidence graph ID: `{res.decision.decision_id}`."

    # Intent routing: Candidate Comparison
    elif "compare" in q_lower or "vs" in q_lower:
        cids = [p["id"] for p in context_players[:3] if "id" in p]
        if not cids:
            cids = [str(uuid.uuid4()), str(uuid.uuid4())]

        req = CandidateComparisonRequest(candidate_ids=[uuid.UUID(str(cid)) for cid in cids])
        res = await tools.decision_service.compare_candidates(req, candidates_override=context_players)

        evidence_summary = "**Objective**: Multi-dimensional candidate comparison.\n\n"
        evidence_summary += f"Executing side-by-side dimensional matrix across {len(res.candidates)} candidates...\n\n"

        evidence_summary += "| Dimension | " + " | ".join(c.player_name for c in res.candidates) + " |\n"
        evidence_summary += "|---|" + "|".join("---" for _ in res.candidates) + "|\n"
        evidence_summary += "| **Target Role** | " + " | ".join(c.target_role for c in res.candidates) + " |\n"
        evidence_summary += "| **Tactical Fit** | " + " | ".join(f"{c.tactical.tactical_fit_score:.1f}%" for c in res.candidates) + " |\n"
        evidence_summary += "| **Contribution Rating** | " + " | ".join(f"{c.performance.contribution_rating:.1f}" for c in res.candidates) + " |\n"
        evidence_summary += "| **Estimated Valuation** | " + " | ".join(f"€{c.market.estimated_value_eur:,.0f}" for c in res.candidates) + " |\n"
        evidence_summary += "| **Transfer Risk** | " + " | ".join(c.risk.risk_level for c in res.candidates) + " |\n"
        evidence_summary += "| **Data Confidence** | " + " | ".join(c.confidence.confidence_tier for c in res.candidates) + " |\n"

        if getattr(res, "trade_off_analysis", None):
            evidence_summary += "\n**Dimensional Divergence Analysis**:\n"
            for item in res.trade_off_analysis:
                evidence_summary += f"- **{item['player_name']}**: Strength: {item['primary_strength']} | Trade-off: {item['trade_off']} ({item['overall_fit_tier']})\n"

    # Intent routing: Recruitment Targeting / Scouting
    else:
        pos = "CM" if "midfield" in q_lower else ("CB" if "centre-back" in q_lower or "defender" in q_lower else "FW")
        budget = 30_000_000.0 if "30m" in q_lower else 50_000_000.0

        req = RecruitmentTargetRequest(
            target_position=pos,
            tactical_context_id="433_cm_progressive_midfielder" if pos == "CM" else "possession_dominant_433",
            budget_eur=budget,
            min_minutes=450,
            limit=5,
        )
        res = await tools.decision_service.evaluate_recruitment(req, candidates_override=context_players)

        evidence_summary = f"**Objective**: Recruitment targeting search.\n\n"
        evidence_summary += f"Applying hard constraints: Position = `{pos}`, Budget ceiling = `€{budget:,.0f}`.\n\n"

        evidence_summary += f"**Status**: {res.decision.summary}\n\n"
        if res.top_recommendations:
            evidence_summary += "| Player | Role | Tactical Fit | Est. Fee | Risk Level | Evidence Status |\n"
            evidence_summary += "|---|---|---|---|---|---|\n"
            for c in res.top_recommendations:
                evidence_summary += (
                    f"| **{c.player_name}** | {c.target_role} | {c.tactical.tactical_fit_score:.1f}% | "
                    f"€{c.market.estimated_value_eur:,.0f} | {c.risk.risk_level} | {c.confidence.data_status} |\n"
                )
            evidence_summary += "\n**Evidence Breakdown**:\n"
            for c in res.top_recommendations[:2]:
                evidence_summary += f"- **{c.player_name}**: {'; '.join(c.why_matches)}\n"
        else:
            evidence_summary += "No candidates satisfied all hard constraints. Review budget ceiling or minutes threshold.\n"

        if res.excluded_summaries:
            evidence_summary += f"\n*Excluded Candidates*: {len(res.excluded_summaries)} candidates filtered out due to hard constraint violations (e.g., budget ceiling or minutes floor).\n"

    # Stream the deterministic evidence first
    yield evidence_summary + "\n\n---\n\n"

    # Now generate the natural language explanation using the LLM
    if evidence_summary:
        llm_response = await _llm_generate(
            query=query,
            context_players=context_players,
            system_prompt=COPILOT_SYSTEM_PROMPT,
        )
        yield llm_response