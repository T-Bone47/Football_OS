"""Deterministic fallback tool planning.

The model is the primary planner, but a reasoning model sometimes answers a data
question without calling a tool (observed live: five of twelve golden cases). The
answer would then be an ungrounded statement about the platform's own data.

This module provides a **fallback**: a small, explicit keyword router that executes the
argument-free tools for the common question shapes, so the answer is always produced
from retrieved records. It never overrides the model - the model's own tool calls are
executed first and this only runs when the model chose no tool at all.

The router is intentionally small and inspectable. It is not a second intelligence:
it maps question shapes to the tools that answer them, with arguments the tools can
run without further input.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FallbackCall:
    """One tool the fallback wants to run."""

    tool: str
    arguments: dict[str, Any]


def _contains(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def plan_fallback_tools(query: str, *, limit: int = 3) -> list[FallbackCall]:
    """Return the tools to run when the model did not choose any."""
    text = (query or "").lower()
    calls: list[FallbackCall] = []

    def add(tool: str, arguments: dict[str, Any] | None = None) -> None:
        if len(calls) >= limit:
            return
        if any(call.tool == tool for call in calls):
            return
        calls.append(FallbackCall(tool=tool, arguments=arguments or {}))

    # Platform questions.
    if _contains(text, "coverage", "how complete", "how many players", "data quality", "fresh"):
        add("get_data_coverage")
    if _contains(text, "provider", "ingestion", "source", "freshness", "stale"):
        add("get_provider_health")
        add("get_data_freshness")
    if _contains(text, "model status", "model registry", "release", "blocker"):
        add("get_model_status")
    if _contains(text, "methodolog", "how does", "how is", "formula", "method"):
        add("get_analytics_methodology", {"query": query[:200]})

    # Squad and tactics.
    if _contains(text, "squad", "balance", "formation", "line-up", "lineup", "depth", "gap"):
        add("analyze_squad_balance")
    if _contains(text, "tactical", "fit", "system", "role"):
        add("find_recruitment_candidates")

    # Matches.
    if _contains(text, "match", "fixture", "last game", "lost", "won", "kick-off", "score"):
        add("search_matches", {"page": 1, "page_size": 5})
    if _contains(text, "prediction", "probability", "xg", "expected goals"):
        add("search_matches", {"page": 1, "page_size": 5})

    # Players and recruitment.
    if _contains(text, "player", "midfielder", "striker", "defender", "goalkeeper", "winger",
                 "valuation", "value", "worth", "price", "fee", "risk", "replacement", "candidate",
                 "recruit", "who plays", "find"):
        add("search_players", {"page": 1, "page_size": 10})
    # NOTE: only tools whose arguments are all optional are used here: the fallback
    # runs without the model, so it cannot supply a player id. Tools that need an
    # id (get_player_valuation, analyze_transfer_risk, find_replacements,
    # find_similar_players, compare_players, analyze_player_role) stay available to
    # the model, which can supply the id.
    if _contains(text, "valuation", "value", "worth", "price", "risk", "transfer",
                 "replacement", "replace", "similar", "comparable", "compare",
                 "versus", " vs ", "role", "archetype"):
        add("search_players", {"page": 1, "page_size": 10})

    return calls[:limit]
