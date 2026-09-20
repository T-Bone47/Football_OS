"""Player Role Discovery and Multi-Dimensional Similarity module (Phase 2 Slice 2)."""
from app.roles.registry import ROLE_FEATURE_REGISTRY, RoleFeatureDefinition, PositionGroup
from app.roles.profiler import RoleProfiler
from app.roles.clustering import RoleDiscoveryEngine
from app.roles.similarity import PlayerSimilarityEngine
from app.roles.service import RoleService

__all__ = [
    "ROLE_FEATURE_REGISTRY",
    "RoleFeatureDefinition",
    "PositionGroup",
    "RoleProfiler",
    "RoleDiscoveryEngine",
    "PlayerSimilarityEngine",
    "RoleService",
]
