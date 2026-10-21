"""Question → family routing.

The relevance score alone is a bag of words: it does not know that "who is our next
midfielder" is a *recruitment* question or that "why did we lose" is a *match*
question. The router classifies the question first, so the model is offered the
tools of the families that can actually answer it, plus the small always-available
core.

The classifier is a keyword map, not a model: it must be inspectable, deterministic
and cheap (it runs on every request and its output decides what the model sees).
"""
from __future__ import annotations

from typing import Iterable

FAMILY_PLAYER = "player"
FAMILY_TEAM = "team"
FAMILY_MATCH = "match"
FAMILY_RECRUITMENT = "recruitment"
FAMILY_FINANCIAL = "financial"
FAMILY_SQUAD = "squad"
FAMILY_PLATFORM = "platform"

#: Every family and the words that select it.
FAMILY_KEYWORDS: dict[str, tuple[str, ...]] = {
    FAMILY_PLATFORM: (
        "coverage", "complete", "completeness", "how many players", "database",
        "data quality", "freshness", "stale", "provider", "providers", "ingestion",
        "model status", "model registry", "release", "blocker", "methodology",
        "method", "how does", "capabilit", "document",
    ),
    FAMILY_MATCH: (
        "match", "matches", "fixture", "fixtures", "last game", "last match",
        "kick-off", "kickoff", "score", "goals", "xg", "expected goals",
        "probability", "prediction", "lost", "won", "draw", "opponent", "stadium",
    ),
    FAMILY_SQUAD: (
        "squad", "line-up", "lineup", "starting xi", "bench", "balance",
        "formation", "depth", "gap", "gaps", "position coverage", "rotation",
    ),
    FAMILY_RECRUITMENT: (
        "recruit", "recruitment", "target", "signing", "candidate",
        "candidates", "shortlist", "shortlist", "replace", "replacement",
        "succession", "tactical fit", "role fit", "similar", "comparable",
        "who should", "alternatives", "trade-off", "tradeoff",
    ),
    FAMILY_FINANCIAL: (
        "valuation", "value", "worth", "price", "fee", "market value",
        "transfer risk", "risk", "affordable", "budget", "cost",
    ),
    FAMILY_TEAM: (
        "club", "clubs", "team", "teams", "table", "standing", "standings",
        "league table", "roster",
    ),
    FAMILY_PLAYER: (
        "player", "players", "midfielder", "striker", "defender", "goalkeeper",
        "winger", "profile", "statistics", "stats", "minutes", "appearances",
        "assists", "goals", "dob", "age", "nationality", "position", "role",
        "archetype", "compare", "versus", " vs ",
    ),
}

#: The core that is always offered: the model must always be able to resolve a
#: player, and the platform must always be able to describe itself.
CORE_TOOLS = ("search_players", "get_player_profile", "get_data_coverage")


def classify_question(query: str) -> list[str]:
    """Return the families a question most likely belongs to (most specific first)."""
    text = (query or "").lower()
    if not text.strip():
        return []
    scores: dict[str, int] = {}
    for family, keywords in FAMILY_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits:
            scores[family] = hits
    if not scores:
        return []
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [family for family, _ in ordered]


def families_for_tools(tool_families: dict[str, str]) -> dict[str, list[str]]:
    """Invert a tool → family map into family → tools."""
    inverted: dict[str, list[str]] = {}
    for tool, family in tool_families.items():
        inverted.setdefault(family, []).append(tool)
    return inverted


def select_families(query: str, *, max_families: int = 2) -> list[str]:
    """The families to offer, always including the player family for referents."""
    families = classify_question(query)
    if not families:
        return [FAMILY_PLAYER, FAMILY_PLATFORM]
    selected = families[:max_families]
    if FAMILY_PLAYER not in selected and any(
        family in selected for family in (FAMILY_MATCH, FAMILY_RECRUITMENT, FAMILY_FINANCIAL, FAMILY_SQUAD)
    ):
        selected.append(FAMILY_PLAYER)
    return selected


def contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)
