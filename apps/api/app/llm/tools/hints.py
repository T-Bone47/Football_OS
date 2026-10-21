"""Attach usage hints to the FIO tools.

The live evaluation showed the model calling `get_player_profile` with a name that
does not resolve, three times in a row, before it found the right argument. A one-line
hint in the tool schema removes most of that waste and makes the tool sequence
predictable for the reviewer.
"""
from __future__ import annotations

from app.llm.tools.base import ToolRegistry

TOOL_HINTS: dict[str, str] = {
    "search_players": "Start here for any player question: it returns canonical ids.",
    "get_player_profile": "Use a canonical id; if you only have a name, call search_players first.",
    "get_player_season_statistics": "Needs a canonical id from search_players or get_player_profile.",
    "compare_players": "Needs 2-5 canonical ids; resolve them with search_players first.",
    "find_similar_players": "Needs a canonical id and a qualified role profile.",
    "analyze_player_role": "Needs a canonical id; shows the archetype and its sample depth.",
    "get_player_career_history": "Needs a canonical id; returns club registrations and transfers.",
    "get_player_valuation": "Needs a canonical id; reports INSUFFICIENT_DATA when comparables are missing.",
    "analyze_transfer_risk": "Needs a canonical id.",
    "evaluate_tactical_fit": "Needs a canonical id and optionally a tactical context id.",
    "find_recruitment_candidates": "Ranks the canonical universe against explicit hard constraints.",
    "find_replacements": "Needs the canonical id of the player to replace.",
    "compare_candidate_tradeoffs": "Needs 2-10 canonical ids.",
    "search_teams": "Returns canonical club ids.",
    "get_team_profile": "Needs a canonical club id from search_teams.",
    "get_team_squad": "Optional club id; the squad engine selects from the canonical universe.",
    "analyze_squad_balance": "Optional club id; reports role coverage and depth risk.",
    "get_competition_overview": "Use before claiming that a league or season is covered.",
    "get_league_standings": "Not available in FIO: there is no normalised league table.",
    "search_matches": "Returns canonical match ids; use them with the match tools.",
    "get_match_details": "Needs a canonical match id from search_matches.",
    "get_match_statistics": "Needs a canonical match id; many fixtures store no statistics.",
    "get_match_event_summary": "Needs a canonical match id.",
    "get_match_prediction": "Needs a canonical match id; returns the model's data_status.",
    "analyze_matchup": "Needs a canonical match id; combines fixture, statistics and prediction.",
    "get_data_coverage": "Use this before any claim about how complete the database is.",
    "get_data_freshness": "Use this before claiming a figure is current.",
    "get_model_status": "Use this before claiming what a model can do.",
    "get_provider_health": "Use this before claiming which sources are enabled.",
    "get_analytics_methodology": "Use this before explaining how a metric is computed.",
}


def apply_tool_hints(registry: ToolRegistry) -> ToolRegistry:
    """Attach the hints to the registered tools (in place)."""
    for spec in registry.specs():
        hint = TOOL_HINTS.get(spec.name)
        if hint:
            spec.hint = hint
    return registry
