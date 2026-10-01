"""Taxonomy and constants for the Player Intelligence Engine (Phase 3.2)."""
from enum import Enum


class SimilarityMode(str, Enum):
    """Supported multi-dimensional similarity modes (Phase 3.2H)."""
    COMPOSITE = "composite"        # Default: 0.50 stat + 0.35 role + 0.15 context
    CONTRIBUTION = "contribution"  # Strict similarity across 7 contribution dimensions
    ROLE = "role"                  # Strict similarity across 9 functional role dimensions
    TACTICAL = "tactical"          # Similarity across tactical system fit requirements
    REPLACEMENT = "replacement"    # Practical replacement: functional similarity penalized by age/contract/exposure gap


class ConfidenceTier(str, Enum):
    """Measurable sample evidence confidence tiers."""
    HIGH = "HIGH"                  # >= 900 minutes (10+ full matches)
    MEDIUM = "MEDIUM"              # 600 - 899 minutes
    LOW = "LOW"                    # 270 - 599 minutes
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"  # < 270 minutes (hard gate)
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"      # 0 minutes or missing records


class DataStatus(str, Enum):
    """Data sufficiency states."""
    EVALUATED = "EVALUATED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class BenchmarkGroup(str, Enum):
    """Position family peer groups for contextual benchmarking."""
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    ATT = "ATT"


MIN_MINUTES_EVALUATED = 270
MIN_PEER_SAMPLE_FOR_RANK = 5
INTELLIGENCE_CALCULATION_VERSION = "1.0"
INTELLIGENCE_FEATURE_SET_VERSION = "intelligence_v1"
