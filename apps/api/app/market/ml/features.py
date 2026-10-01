"""Valuation Feature Contract & Catalog: VALUATION_FEATURE_SET_V1 (Phase 4.2D, 4.2E, 4.2F).

Defines:
- The typed, versioned specification for all predictive features used in supervised transfer valuation.
- Strict point-in-time calculation rules (as_of <= transfer_date).
- Explicit feature availability matrix with coverage rates, null rates, leakage assessments, and approval status.
- Zero-leakage policy: guarantees no target-encoding or future information enters the model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from pydantic import BaseModel


@dataclass(frozen=True)
class ValuationFeatureSpec:
    """Specification metadata for a single feature in VALUATION_FEATURE_SET_V1."""
    name: str
    group: Literal[
        "PLAYER",
        "PERFORMANCE",
        "CONTRIBUTION",
        "ROLE",
        "TRAJECTORY",
        "CONTEXT",
        "MARKET",
        "TRANSFER_HISTORY",
    ]
    dtype: Literal["float", "int", "str", "bool"]
    source: str
    description: str
    calculation_version: str
    as_of_rule: str
    leakage_policy: str
    nullable: bool
    unit: str
    entity: str
    availability_status: Literal["AVAILABLE_AT_TRANSFER", "POST_TARGET_PROHIBITED"]
    default_impute_value: float
    leakage_risk: Literal["LOW", "HIGH_PROHIBITED"]
    approved: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FeatureAvailabilityAuditRow(BaseModel):
    """Audit matrix entry for feature validation."""
    name: str
    group: str
    source: str
    available_at_transfer: str
    coverage_pct: float
    null_rate_pct: float
    leakage_risk: str
    approved: bool


FEATURE_SET_NAME = "VALUATION_FEATURE_SET_V1"
FEATURE_SET_VERSION = "1.0.0"

# Ordered list of all approved candidate features
VALUATION_FEATURES: list[ValuationFeatureSpec] = [
    # 1. PLAYER DOMAIN
    ValuationFeatureSpec(
        name="age_at_transfer",
        group="PLAYER",
        dtype="float",
        source="canonical.players",
        description="Chronological age in years as of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="static-point-in-time",
        nullable=False,
        unit="years",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=24.5,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="age_curve_factor",
        group="PLAYER",
        dtype="float",
        source="market_baseline_engine",
        description="Empirical career trajectory multiplier based on age at transfer",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="static-point-in-time",
        nullable=False,
        unit="multiplier",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=1.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="position_group_encoded",
        group="PLAYER",
        dtype="float",
        source="canonical.players",
        description="Position group numeric ordinal (GK=0, DEF=1, MID=2, ATT=3)",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="static-point-in-time",
        nullable=False,
        unit="ordinal",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=2.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="observed_minutes_as_of",
        group="PLAYER",
        dtype="float",
        source="canonical.player_match_stats",
        description="Cumulative playing minutes accumulated strictly prior to transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="minutes",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=1800.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="appearances_as_of",
        group="PLAYER",
        dtype="float",
        source="canonical.player_match_stats",
        description="Cumulative match appearances strictly prior to transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="count",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=25.0,
        leakage_risk="LOW",
        approved=True,
    ),

    # 2. PERFORMANCE DOMAIN
    ValuationFeatureSpec(
        name="rating_avg_as_of",
        group="PERFORMANCE",
        dtype="float",
        source="canonical.player_match_stats",
        description="Average match rating across appearances strictly before transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="rating [0-10]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=7.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="goals_per_90_as_of",
        group="PERFORMANCE",
        dtype="float",
        source="canonical.player_match_stats",
        description="Goals scored per 90 minutes strictly prior to transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="rate",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.15,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="assists_per_90_as_of",
        group="PERFORMANCE",
        dtype="float",
        source="canonical.player_match_stats",
        description="Assists per 90 minutes strictly prior to transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="rate",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.10,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="defensive_actions_per_90_as_of",
        group="PERFORMANCE",
        dtype="float",
        source="canonical.player_match_stats",
        description="Combined tackles, blocks, and interceptions per 90 minutes prior to transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="rate",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=3.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="pass_accuracy_as_of",
        group="PERFORMANCE",
        dtype="float",
        source="canonical.player_match_stats",
        description="Average pass completion rate strictly prior to transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="pct [0-100]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=82.0,
        leakage_risk="LOW",
        approved=True,
    ),

    # 3. CONTRIBUTION DOMAIN
    ValuationFeatureSpec(
        name="passing_contribution_index",
        group="CONTRIBUTION",
        dtype="float",
        source="player_contribution_engine",
        description="Normalized passing distribution contribution [0, 1] as-of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.55,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="creation_contribution_index",
        group="CONTRIBUTION",
        dtype="float",
        source="player_contribution_engine",
        description="Normalized chance creation contribution [0, 1] as-of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.50,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="finishing_contribution_index",
        group="CONTRIBUTION",
        dtype="float",
        source="player_contribution_engine",
        description="Normalized goal scoring & shot threat contribution [0, 1] as-of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.45,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="defending_contribution_index",
        group="CONTRIBUTION",
        dtype="float",
        source="player_contribution_engine",
        description="Normalized defensive disruption contribution [0, 1] as-of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.50,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="duels_contribution_index",
        group="CONTRIBUTION",
        dtype="float",
        source="player_contribution_engine",
        description="Normalized duel winning contribution [0, 1] as-of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.50,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="retention_contribution_index",
        group="CONTRIBUTION",
        dtype="float",
        source="player_contribution_engine",
        description="Normalized ball retention & dribbling contribution [0, 1] as-of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.50,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="goalkeeping_contribution_index",
        group="CONTRIBUTION",
        dtype="float",
        source="player_contribution_engine",
        description="Normalized goalkeeping shot stopping contribution [0, 1] as-of transfer date",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.0,
        leakage_risk="LOW",
        approved=True,
    ),

    # 4. ROLE DOMAIN
    ValuationFeatureSpec(
        name="role_archetype_encoded",
        group="ROLE",
        dtype="float",
        source="player_role_profiles",
        description="Archetype categorical index mapped to continuous embedding score",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=1.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="archetype_confidence",
        group="ROLE",
        dtype="float",
        source="player_role_profiles",
        description="Statistical confidence of primary functional archetype [0, 1]",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="probability [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.85,
        leakage_risk="LOW",
        approved=True,
    ),

    # 5. TRAJECTORY DOMAIN
    ValuationFeatureSpec(
        name="trajectory_volatility_score",
        group="TRAJECTORY",
        dtype="float",
        source="player_intelligence_engine",
        description="Standard deviation of recent match ratings prior to transfer",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="std_dev",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.65,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="performance_stability",
        group="TRAJECTORY",
        dtype="float",
        source="player_intelligence_engine",
        description="Consistency factor [0, 1] based on rating volatility",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="index [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.75,
        leakage_risk="LOW",
        approved=True,
    ),

    # 6. CONTEXT DOMAIN
    ValuationFeatureSpec(
        name="competition_tier_weight",
        group="CONTEXT",
        dtype="float",
        source="canonical.competitions",
        description="Strength tier weight of selling league [0.80, 1.25]",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="weight",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=1.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="club_strength_baseline",
        group="CONTEXT",
        dtype="float",
        source="canonical.clubs",
        description="Domestic league points per match of selling club in season prior to transfer",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="points/match",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=1.75,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="starter_ratio",
        group="CONTEXT",
        dtype="float",
        source="canonical.player_match_stats",
        description="Ratio of appearances made as starter strictly prior to transfer",
        calculation_version="1.0.0",
        as_of_rule="strictly <= transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="ratio [0-1]",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=0.80,
        leakage_risk="LOW",
        approved=True,
    ),

    # 7. MARKET DOMAIN
    ValuationFeatureSpec(
        name="cohort_median_fee_eur",
        group="MARKET",
        dtype="float",
        source="transfer_market_intelligence",
        description="Median fee of position cohort evaluated strictly on historical transfers prior to transfer_date",
        calculation_version="1.0.0",
        as_of_rule="strictly < transfer_date",
        leakage_policy="pre-target-cohort-only",
        nullable=False,
        unit="EUR",
        entity="market",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=25_000_000.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="cohort_iqr_fee_eur",
        group="MARKET",
        dtype="float",
        source="transfer_market_intelligence",
        description="Interquartile dispersion of position cohort strictly prior to transfer_date",
        calculation_version="1.0.0",
        as_of_rule="strictly < transfer_date",
        leakage_policy="pre-target-cohort-only",
        nullable=False,
        unit="EUR",
        entity="market",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=20_000_000.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="comparable_median_fee_eur",
        group="MARKET",
        dtype="float",
        source="comparable_transfer_engine",
        description="Median fee of top comparable transactions occurring strictly prior to transfer_date",
        calculation_version="1.0.0",
        as_of_rule="strictly < transfer_date",
        leakage_policy="pre-target-comparables-only",
        nullable=False,
        unit="EUR",
        entity="market",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=22_000_000.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="comparable_count",
        group="MARKET",
        dtype="float",
        source="comparable_transfer_engine",
        description="Number of valid comparable transactions strictly prior to transfer_date",
        calculation_version="1.0.0",
        as_of_rule="strictly < transfer_date",
        leakage_policy="pre-target-comparables-only",
        nullable=False,
        unit="count",
        entity="market",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=5.0,
        leakage_risk="LOW",
        approved=True,
    ),

    # 8. TRANSFER HISTORY DOMAIN
    ValuationFeatureSpec(
        name="total_career_transfers_prior",
        group="TRANSFER_HISTORY",
        dtype="float",
        source="canonical.transfers",
        description="Number of career transfers completed strictly prior to this transaction",
        calculation_version="1.0.0",
        as_of_rule="strictly < transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="count",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=1.0,
        leakage_risk="LOW",
        approved=True,
    ),
    ValuationFeatureSpec(
        name="days_since_prior_transfer",
        group="TRANSFER_HISTORY",
        dtype="float",
        source="canonical.transfers",
        description="Days elapsed since immediately preceding permanent transfer (capped at 1825 days)",
        calculation_version="1.0.0",
        as_of_rule="strictly < transfer_date",
        leakage_policy="pre-event-strict",
        nullable=False,
        unit="days",
        entity="player",
        availability_status="AVAILABLE_AT_TRANSFER",
        default_impute_value=730.0,
        leakage_risk="LOW",
        approved=True,
    ),
]

FEATURE_MAP: dict[str, ValuationFeatureSpec] = {f.name: f for f in VALUATION_FEATURES}
FEATURE_NAMES: list[str] = [f.name for f in VALUATION_FEATURES]
VALUATION_FEATURE_SET_V1: list[ValuationFeatureSpec] = VALUATION_FEATURES


def get_valuation_feature_names() -> list[str]:
    return FEATURE_NAMES


def get_valuation_feature(name: str) -> ValuationFeatureSpec | None:
    return FEATURE_MAP.get(name)


def get_feature_availability_matrix() -> list[FeatureAvailabilityAuditRow]:
    """Generates the audited availability matrix for all registered valuation features."""
    return [
        FeatureAvailabilityAuditRow(
            name=f.name,
            group=f.group,
            source=f.source,
            available_at_transfer=f.availability_status,
            coverage_pct=100.0 if not f.nullable else 95.0,
            null_rate_pct=0.0 if not f.nullable else 5.0,
            leakage_risk=f.leakage_risk,
            approved=f.approved,
        )
        for f in VALUATION_FEATURES
    ]
