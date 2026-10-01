"""Feature Registry and Definitions (Phase 2 Slice 1).
Provides typed, versioned metadata for all leakage-safe analytical features.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    feature_set: str
    entity_type: str  # 'player', 'team', 'match'
    version: str
    dtype: str  # 'float', 'int', 'str', 'bool'
    description: str
    required_inputs: list[str]
    leakage_policy: str  # 'pre-match-strict'
    window: str | None  # 'last_3', 'last_5', 'last_10', 'season_to_date', None
    nullable: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PLAYER_METRICS_CONFIG = [
    # Usage
    ("appearances", "int", "Number of appearances in window", ["minutes"], False),
    ("starts", "int", "Number of matches started in window", ["is_starter"], False),
    ("minutes", "int", "Total minutes played in window", ["minutes"], False),
    ("minutes_per_match", "float", "Average minutes played per appearance", ["minutes"], True),
    ("starter_rate", "float", "Fraction of appearances started", ["is_starter", "minutes"], True),
    ("substitution_rate", "float", "Fraction of appearances as substitute", ["is_substitute", "minutes"], True),

    # Scoring
    ("goals", "int", "Total goals scored in window", ["goals"], True),
    ("assists", "int", "Total assists in window", ["assists"], True),
    ("goals_per_90", "float", "Safe per-90 goals scored (null if minutes <= 0)", ["goals", "minutes"], True),
    ("assists_per_90", "float", "Safe per-90 assists (null if minutes <= 0)", ["assists", "minutes"], True),
    ("shots_total", "int", "Total shots attempted in window", ["shots_total"], True),
    ("shots_per_90", "float", "Safe per-90 shots attempted (null if minutes <= 0)", ["shots_total", "minutes"], True),
    ("shots_on_target_per_90", "float", "Safe per-90 shots on target (null if minutes <= 0)", ["shots_on_target", "minutes"], True),

    # Creation
    ("passes_key", "int", "Total key passes in window", ["passes_key"], True),
    ("passes_key_per_90", "float", "Safe per-90 key passes (null if minutes <= 0)", ["passes_key", "minutes"], True),

    # Passing
    ("passes_total", "int", "Total passes attempted in window", ["passes_total"], True),
    ("passes_per_90", "float", "Safe per-90 passes attempted (null if minutes <= 0)", ["passes_total", "minutes"], True),
    ("pass_accuracy_avg", "float", "Average pass accuracy percentage", ["pass_accuracy"], True),

    # Defending
    ("tackles_total", "int", "Total tackles in window", ["tackles_total"], True),
    ("tackles_per_90", "float", "Safe per-90 tackles (null if minutes <= 0)", ["tackles_total", "minutes"], True),
    ("interceptions", "int", "Total interceptions in window", ["interceptions"], True),
    ("blocks", "int", "Total blocks in window", ["blocks"], True),
    ("defensive_actions_per_90", "float", "Safe per-90 combined defensive actions (tackles+interceptions+blocks)", ["tackles_total", "interceptions", "blocks", "minutes"], True),

    # Duels
    ("duels_total", "int", "Total duels contested in window", ["duels_total"], True),
    ("duels_won", "int", "Total duels won in window", ["duels_won"], True),
    ("duel_win_rate", "float", "Fraction of contested duels won", ["duels_won", "duels_total"], True),

    # Dribbling
    ("dribbles_attempts", "int", "Total dribble attempts in window", ["dribbles_attempts"], True),
    ("dribbles_success", "int", "Total successful dribbles in window", ["dribbles_success"], True),
    ("dribble_success_rate", "float", "Fraction of dribble attempts successful", ["dribbles_success", "dribbles_attempts"], True),

    # Discipline
    ("yellow_cards", "int", "Total yellow cards in window", ["yellow_cards"], True),
    ("red_cards", "int", "Total red cards in window", ["red_cards"], True),
    ("fouls_committed", "int", "Total fouls committed in window", ["fouls_committed"], True),
    ("fouls_drawn", "int", "Total fouls drawn in window", ["fouls_drawn"], True),

    # Goalkeeping (Only applicable to G; None for outfield)
    ("saves", "int", "Total saves in window (goalkeepers only)", ["saves", "position"], True),
    ("goals_conceded", "int", "Total goals conceded in window (goalkeepers only)", ["goals_conceded", "position"], True),
    ("clean_sheets", "int", "Total clean sheets in window (goalkeepers only)", ["clean_sheet", "position"], True),
    ("save_rate", "float", "Save percentage saves / (saves + goals_conceded) (goalkeepers only)", ["saves", "goals_conceded", "position"], True),

    # Rating
    ("rating_avg", "float", "Average match performance rating in window", ["rating"], True),
]

WINDOWS = ["last_3", "last_5", "last_10", "season_to_date"]

FEATURE_REGISTRY: dict[str, FeatureDefinition] = {}

# Register player features
for win in WINDOWS:
    # Context / exposure per window
    FEATURE_REGISTRY[f"sample_matches_{win}"] = FeatureDefinition(
        name=f"sample_matches_{win}",
        feature_set="player_match_v1",
        entity_type="player",
        version="1.0.0",
        dtype="int",
        description=f"Number of historical matches available in {win} window strictly before as_of",
        required_inputs=["match.date"],
        leakage_policy="pre-match-strict",
        window=win,
        nullable=False,
        source="silver.player_match_stats",
    )
    for name, dtype, desc, inputs, nullable in PLAYER_METRICS_CONFIG:
        feat_key = f"{name}_{win}"
        FEATURE_REGISTRY[feat_key] = FeatureDefinition(
            name=feat_key,
            feature_set="player_match_v1",
            entity_type="player",
            version="1.0.0",
            dtype=dtype,
            description=f"{desc} ({win})",
            required_inputs=inputs,
            leakage_policy="pre-match-strict",
            window=win,
            nullable=nullable,
            source="silver.player_match_stats",
        )

# Team metrics config
TEAM_METRICS_CONFIG = [
    ("matches_played", "int", "Matches played in window", ["match.date"], False),
    ("wins", "int", "Matches won in window", ["result"], False),
    ("draws", "int", "Matches drawn in window", ["result"], False),
    ("losses", "int", "Matches lost in window", ["result"], False),
    ("points", "int", "Total league points accumulated in window (W=3, D=1, L=0)", ["result"], False),
    ("points_per_match", "float", "Points per match in window", ["result"], True),
    ("win_rate", "float", "Fraction of matches won in window", ["result"], True),
    ("goals_scored", "int", "Goals scored by team in window", ["goals_for"], False),
    ("goals_conceded", "int", "Goals conceded by team in window", ["goals_against"], False),
    ("goal_difference", "int", "Goal difference in window (goals_scored - goals_conceded)", ["goals_for", "goals_against"], False),
    ("goals_scored_per_match", "float", "Average goals scored per match in window", ["goals_for"], True),
    ("goals_conceded_per_match", "float", "Average goals conceded per match in window", ["goals_against"], True),
    ("clean_sheets", "int", "Clean sheets kept in window", ["goals_against"], False),
    ("clean_sheet_rate", "float", "Fraction of matches with 0 goals conceded", ["goals_against"], True),
    ("possession_avg", "float", "Average possession percentage in window", ["possession"], True),
    ("shots_avg", "float", "Average shots attempted per match in window", ["shots_total"], True),
    ("shots_on_target_avg", "float", "Average shots on target per match in window", ["shots_on_target"], True),
    ("pass_accuracy_avg", "float", "Average team pass accuracy percentage in window", ["pass_accuracy"], True),
    ("fouls_avg", "float", "Average fouls committed per match in window", ["fouls"], True),
    ("corners_avg", "float", "Average corners won per match in window", ["corner_kicks"], True),
]

for win in WINDOWS:
    for name, dtype, desc, inputs, nullable in TEAM_METRICS_CONFIG:
        feat_key = f"{name}_{win}"
        FEATURE_REGISTRY[feat_key] = FeatureDefinition(
            name=feat_key,
            feature_set="team_match_v1",
            entity_type="team",
            version="1.0.0",
            dtype=dtype,
            description=f"{desc} ({win})",
            required_inputs=inputs,
            leakage_policy="pre-match-strict",
            window=win,
            nullable=nullable,
            source="silver.match_teams",
        )

# Home / Away team contextual features
HOME_AWAY_FEATURES = [
    ("home_points_last_5", "float", "Points per match in last 5 home games strictly before as_of", ["result", "is_home"]),
    ("away_points_last_5", "float", "Points per match in last 5 away games strictly before as_of", ["result", "is_home"]),
    ("home_goals_scored_last_5", "float", "Goals scored per match in last 5 home games strictly before as_of", ["goals_for", "is_home"]),
    ("away_goals_scored_last_5", "float", "Goals scored per match in last 5 away games strictly before as_of", ["goals_for", "is_home"]),
    ("home_goals_conceded_last_5", "float", "Goals conceded per match in last 5 home games strictly before as_of", ["goals_against", "is_home"]),
    ("away_goals_conceded_last_5", "float", "Goals conceded per match in last 5 away games strictly before as_of", ["goals_against", "is_home"]),
]

for name, dtype, desc, inputs in HOME_AWAY_FEATURES:
    FEATURE_REGISTRY[name] = FeatureDefinition(
        name=name,
        feature_set="team_match_v1",
        entity_type="team",
        version="1.0.0",
        dtype=dtype,
        description=desc,
        required_inputs=inputs,
        leakage_policy="pre-match-strict",
        window="last_5",
        nullable=True,
        source="silver.match_teams",
    )

# Match context features
MATCH_CONTEXT_FEATURES = [
    ("is_home", "bool", "Whether target entity is home team in match", ["match_teams.is_home"], False),
    ("opponent_club_id", "str", "UUID string of opponent club", ["match_teams.club_id"], False),
    ("days_since_previous_match", "float", "Calendar days since target entity's immediately preceding match strictly before as_of", ["matches.date"], True),
    ("opponent_days_since_previous_match", "float", "Calendar days since opponent's immediately preceding match strictly before as_of", ["matches.date"], True),
    ("team_strength_baseline_points_per_match", "float", "Team rolling points per match over last 5 matches before as_of", ["result"], True),
    ("team_strength_baseline_goal_diff", "float", "Team rolling goal difference per match over last 5 matches before as_of", ["goals_for", "goals_against"], True),
    ("opponent_strength_baseline_points_per_match", "float", "Opponent rolling points per match over last 5 matches before as_of", ["result"], True),
    ("opponent_strength_baseline_goal_diff", "float", "Opponent rolling goal difference per match over last 5 matches before as_of", ["goals_for", "goals_against"], True),
]

for name, dtype, desc, inputs, nullable in MATCH_CONTEXT_FEATURES:
    FEATURE_REGISTRY[name] = FeatureDefinition(
        name=name,
        feature_set="match_context_v1",
        entity_type="match",
        version="1.0.0",
        dtype=dtype,
        description=desc,
        required_inputs=inputs,
        leakage_policy="pre-match-strict",
        window="instant",
        nullable=nullable,
        source="silver.matches",
    )

# Player contribution intelligence features (Phase 3.1)
CONTRIBUTION_METRICS_CONFIG = [
    ("passing_contribution_index", "float", "Normalized passing distribution contribution [0, 1]", ["passes_total", "pass_accuracy"], True),
    ("creation_contribution_index", "float", "Normalized chance creation contribution [0, 1]", ["passes_key", "assists"], True),
    ("finishing_contribution_index", "float", "Normalized goal scoring & shot threat contribution [0, 1]", ["shots_total", "goals"], True),
    ("defending_contribution_index", "float", "Normalized defensive disruption contribution [0, 1]", ["tackles_total", "interceptions", "blocks"], True),
    ("duels_contribution_index", "float", "Normalized duel winning contribution [0, 1]", ["duels_total", "duels_won"], True),
    ("retention_contribution_index", "float", "Normalized dribbling & ball retention contribution [0, 1]", ["dribbles_success", "fouls_drawn"], True),
    ("goalkeeping_contribution_index", "float", "Normalized goalkeeping shot stopping contribution [0, 1]", ["saves", "goals_conceded"], True),
    ("action_volume_per_90", "float", "Total discrete canonical actions per 90 minutes", ["canonical_actions"], True),
    ("net_action_impact_per_90", "float", "Deterministic net action impact score per 90 minutes", ["canonical_actions"], True),
]

for name, dtype, desc, inputs, nullable in CONTRIBUTION_METRICS_CONFIG:
    FEATURE_REGISTRY[name] = FeatureDefinition(
        name=name,
        feature_set="contribution_v1",
        entity_type="player",
        version="1.0.0",
        dtype=dtype,
        description=desc,
        required_inputs=inputs,
        leakage_policy="pre-match-strict",
        window="season_to_date",
        nullable=nullable,
        source="player_contribution_engine",
    )

# Player intelligence composite features (Phase 3.2)
INTELLIGENCE_METRICS_CONFIG = [
    ("context_competition_strength", "float", "Competition strength tier coefficient [0.70, 1.05]", ["competition_name"], True),
    ("context_starter_ratio", "float", "Ratio of appearances made as starter [0, 1]", ["player_match_stats.is_starter"], True),
    ("context_exposure_share", "float", "Ratio of available minutes played [0, 1]", ["player_match_stats.minutes"], True),
    ("context_multiplier", "float", "Composite contextual multiplier based on league tier and starter status", ["competitions", "matches"], True),
    ("peer_benchmark_average_percentile", "float", "Average normal percentile relative to position family peers [0, 100]", ["peer_distributions"], True),
    ("trajectory_volatility_score", "float", "Standard deviation of match ratings across evaluation timeline", ["player_match_stats.rating"], True),
    ("intelligence_composite_score", "float", "Normalized composite intelligence score across active features [0, 1]", ["intelligence_vector"], True),
]

for name, dtype, desc, inputs, nullable in INTELLIGENCE_METRICS_CONFIG:
    FEATURE_REGISTRY[name] = FeatureDefinition(
        name=name,
        feature_set="intelligence_v1",
        entity_type="player",
        version="1.0.0",
        dtype=dtype,
        description=desc,
        required_inputs=inputs,
        leakage_policy="pre-match-strict",
        window="season_to_date",
        nullable=nullable,
        source="player_intelligence_engine",
    )

# Valuation and Market features (Phase 4.1)
VALUATION_METRICS_CONFIG = [
    ("market_comparable_median_fee", "float", "Median fee in EUR across top comparable historical transfers", ["transfers"], True),
    ("market_comparable_count", "int", "Number of qualified comparable transactions within window", ["transfers"], False),
    ("market_fee_iqr", "float", "Interquartile range (Q3 - Q1) of comparable cohort fees in EUR", ["transfers"], True),
    ("market_age_at_evaluation", "float", "Player chronological age at the as_of evaluation timestamp", ["players.date_of_birth"], True),
    ("market_age_curve_factor", "float", "Empirical career trajectory multiplier based on player age", ["players.date_of_birth"], True),
    ("market_valuation_baseline", "float", "Deterministic comparable-median baseline valuation in EUR", ["transfers", "players.date_of_birth"], True),
]

for name, dtype, desc, inputs, nullable in VALUATION_METRICS_CONFIG:
    FEATURE_REGISTRY[name] = FeatureDefinition(
        name=name,
        feature_set="market_valuation_v1",
        entity_type="player",
        version="1.0.0",
        dtype=dtype,
        description=desc,
        required_inputs=inputs,
        leakage_policy="pre-match-strict",
        window="all_historical",
        nullable=nullable,
        source="transfer_market_intelligence",
    )


def get_feature_definition(name: str) -> FeatureDefinition | None:

    return FEATURE_REGISTRY.get(name)


def list_features(feature_set: str | None = None, entity_type: str | None = None) -> list[FeatureDefinition]:
    features = list(FEATURE_REGISTRY.values())
    if feature_set:
        features = [f for f in features if f.feature_set == feature_set]
    if entity_type:
        features = [f for f in features if f.entity_type == entity_type]
    return features
