"""Phase 12 — Versioned Benchmark Player Profiles Engine (§14).

Allows recruitment analysts and scouts to define immutable, versioned target benchmarks:
  Example: "2026/27 Elite Ball Playing CB"
  Dimensions: progression, passing, defending, carrying, aerial, retention, tactical fit.

Rule: Benchmark profiles are versioned and immutable once published; changes spawn a new version.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from app.dev_fixtures import dev_seed_enabled


@dataclass
class BenchmarkProfile:
    """Versioned specification of a target recruitment benchmark profile."""
    benchmark_id: str = field(default_factory=lambda: f"bench_{uuid.uuid4().hex[:12]}")
    name: str = "2026/27 Elite Ball Playing CB"
    version: str = "1.0.0"
    position: str = "CB"
    target_role: str = "Ball Playing Defender"
    formation: str = "4-3-3"
    season_scope: str = "2026/2027"
    competition_scope: list[str] = field(default_factory=lambda: ["GB-PL", "ES-L1", "IT-SA", "DE-BL", "FR-L1"])

    # Multi-Dimensional Weights (Sum = 1.0)
    dimension_weights: dict[str, float] = field(
        default_factory=lambda: {
            "progression": 0.25,
            "passing": 0.20,
            "defending": 0.20,
            "carrying": 0.15,
            "aerial": 0.10,
            "retention": 0.10,
        }
    )

    # Archetype Source Reference Players
    source_reference_players: list[str] = field(
        default_factory=lambda: ["William Saliba", "John Stones", "Gonçalo Inácio"]
    )

    # Immutability & Audit
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "Chief Scout"
    is_published: bool = True
    profile_digest: str = ""

    def __post_init__(self) -> None:
        if not self.profile_digest:
            self.profile_digest = self.compute_digest()

    def compute_digest(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version,
            "position": self.position,
            "target_role": self.target_role,
            "weights": sorted(self.dimension_weights.items()),
            "sources": sorted(self.source_reference_players),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BenchmarkProfileRegistry:
    """Registry maintaining versioned benchmark profiles."""

    def __init__(self) -> None:
        self._profiles: dict[str, BenchmarkProfile] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_benchmarks()

    def _seed_default_benchmarks(self) -> None:
        seed = BenchmarkProfile(
            benchmark_id="bench_cb_ballplaying_v1",
            name="2026/27 Elite Ball Playing CB",
            version="1.0.0",
            position="CB",
            target_role="Ball Playing Defender",
            formation="4-3-3",
            season_scope="2026/2027",
            competition_scope=["GB-PL", "ES-L1", "IT-SA", "DE-BL", "FR-L1"],
            dimension_weights={
                "progression": 0.25,
                "passing": 0.20,
                "defending": 0.20,
                "carrying": 0.15,
                "aerial": 0.10,
                "retention": 0.10,
            },
            source_reference_players=["William Saliba", "John Stones", "Gonçalo Inácio"],
            created_by="Head of Recruitment",
        )
        self._profiles[seed.benchmark_id] = seed

    def create_benchmark(
        self,
        name: str,
        position: str,
        target_role: str,
        formation: str,
        dimension_weights: dict[str, float],
        source_reference_players: list[str],
        competition_scope: list[str],
        version: str = "1.0.0",
        created_by: str = "Scout",
    ) -> BenchmarkProfile:
        """Creates an immutable, versioned benchmark profile."""
        # Normalize weights to 1.0
        total_weight = sum(dimension_weights.values())
        norm_weights = {k: round(v / total_weight, 4) for k, v in dimension_weights.items()}

        profile = BenchmarkProfile(
            name=name,
            version=version,
            position=position,
            target_role=target_role,
            formation=formation,
            dimension_weights=norm_weights,
            source_reference_players=source_reference_players,
            competition_scope=competition_scope,
            created_by=created_by,
        )

        self._profiles[profile.benchmark_id] = profile
        return profile

    def get_benchmark(self, benchmark_id: str) -> BenchmarkProfile | None:
        return self._profiles.get(benchmark_id)

    def list_benchmarks(self) -> list[BenchmarkProfile]:
        return list(self._profiles.values())


benchmark_registry = BenchmarkProfileRegistry()
