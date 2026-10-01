"""Phase 14 — Decision Freshness V2 & Versioned Benchmark Evolution (§15, §16).

Maintains decision currency and historical benchmark integrity:
  - Benchmark Evolution (§15):
    - Strictly isolates:
      - DECISION_TIME_BENCHMARK (frozen at decision timestamp)
      - HISTORICAL_BENCHMARK (frozen at intermediate validation checkpoints)
      - CURRENT_BENCHMARK (active rolling baseline)
    - Prevents retroactive mutation of historical percentiles when benchmarks advance.
  - Decision Freshness V2 (§16):
    - Tracks material changes that degrade decision currency:
      PLAYER_PERFORMANCE_CHANGED, PLAYER_ROLE_CHANGED, TEAM_CONTEXT_CHANGED,
      MARKET_CHANGED, TACTICAL_SYSTEM_CHANGED, INJURY_AVAILABILITY_CHANGED,
      MODEL_VERSION_CHANGED, DATA_COVERAGE_CHANGED, COMPETITION_STATUS_CHANGED,
      ASSUMPTION_EXPIRED.
    - Classifications: FRESH, AGING, STALE, REQUIRES_REVIEW.
    - Explicit non-causal reasonings for status changes.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase14 import BenchmarkScope, FreshnessState
from app.dev_fixtures import dev_seed_enabled


@dataclass
class VersionedBenchmarkMetric:
    """A benchmark metric snapshot frozen under a specific temporal scope (§15)."""
    metric_name: str
    scope: BenchmarkScope
    benchmark_version: str
    p25: float
    p50: float
    p75: float
    p90: float
    sample_size: int
    frozen_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["scope"] = self.scope.value
        return data


@dataclass
class DecisionFreshnessAssessment:
    """Comprehensive freshness and currency audit for an existing decision record (§16)."""
    assessment_id: str = field(default_factory=lambda: f"fresh_{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    decision_timestamp: str = ""
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Currency State
    freshness_state: FreshnessState = FreshnessState.FRESH
    staleness_score: float = 0.0  # 0.0 = completely fresh, 1.0 = completely stale

    # Triggering reasons for aging or staleness
    staleness_reasons: list[str] = field(default_factory=list)
    material_changes: list[dict[str, Any]] = field(default_factory=list)
    action_required: str = "NO_ACTION_REQUIRED"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["freshness_state"] = self.freshness_state.value
        return data


class DecisionFreshnessV2Engine:
    """Evaluates decision staleness and maintains versioned benchmark isolation."""

    def __init__(self) -> None:
        self._benchmarks: dict[str, list[VersionedBenchmarkMetric]] = {}
        self._assessments: dict[str, DecisionFreshnessAssessment] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_benchmarks_and_freshness()

    def register_benchmark(
        self,
        metric_name: str,
        scope: BenchmarkScope,
        benchmark_version: str,
        p25: float,
        p50: float,
        p75: float,
        p90: float,
        sample_size: int,
        frozen_at: str | None = None,
    ) -> VersionedBenchmarkMetric:
        """Registers a frozen benchmark snapshot."""
        bm = VersionedBenchmarkMetric(
            metric_name=metric_name,
            scope=scope,
            benchmark_version=benchmark_version,
            p25=float(p25),
            p50=float(p50),
            p75=float(p75),
            p90=float(p90),
            sample_size=int(sample_size),
            frozen_at=frozen_at or datetime.now(timezone.utc).isoformat(),
        )
        if metric_name not in self._benchmarks:
            self._benchmarks[metric_name] = []
        self._benchmarks[metric_name].append(bm)
        return bm

    def get_benchmarks(self, metric_name: str) -> list[VersionedBenchmarkMetric]:
        return self._benchmarks.get(metric_name, [])

    def evaluate_decision_freshness(
        self,
        decision_id: str,
        decision_timestamp: str,
        days_since_decision: int,
        performance_drift_detected: bool = False,
        role_changed: bool = False,
        market_valuation_changed_pct: float = 0.0,
        model_version_superseded: bool = False,
        assumption_expired: bool = False,
        injury_sustained: bool = False,
    ) -> DecisionFreshnessAssessment:
        """Determines if a historical decision requires review due to contextual shift."""
        reasons: list[str] = []
        changes: list[dict[str, Any]] = []
        staleness_points = 0.0

        if days_since_decision > 180:
            reasons.append("TIME_ELAPSED_OVER_180_DAYS")
            staleness_points += 0.30
            changes.append({"type": "TEMPORAL_AGING", "detail": f"{days_since_decision} days since finalization"})

        if performance_drift_detected:
            reasons.append("PLAYER_PERFORMANCE_CHANGED")
            staleness_points += 0.35
            changes.append({"type": "PERFORMANCE_DRIFT", "detail": "Observed match contribution percentile shifted materially"})

        if role_changed:
            reasons.append("PLAYER_ROLE_CHANGED")
            staleness_points += 0.25
            changes.append({"type": "ROLE_EVOLUTION", "detail": "Player tactically redeployed into alternate role"})

        if abs(market_valuation_changed_pct) >= 20.0:
            reasons.append("MARKET_CHANGED")
            staleness_points += 0.25
            changes.append({"type": "VALUATION_MOVEMENT", "detail": f"Market valuation shifted by {market_valuation_changed_pct:+.1f}%"})

        if model_version_superseded:
            reasons.append("MODEL_VERSION_CHANGED")
            staleness_points += 0.20
            changes.append({"type": "MODEL_RETRAINED", "detail": "Champion model version upgraded since decision"})

        if assumption_expired:
            reasons.append("ASSUMPTION_EXPIRED")
            staleness_points += 0.30
            changes.append({"type": "ASSUMPTION_EXPIRED", "detail": "Explicit window assumptions exceeded validity horizon"})

        if injury_sustained:
            reasons.append("INJURY_AVAILABILITY_CHANGED")
            staleness_points += 0.35
            changes.append({"type": "AVAILABILITY_SHOCK", "detail": "Major physical trauma altered immediate squad availability"})

        score = min(1.0, staleness_points)

        if score >= 0.70 or injury_sustained:
            state = FreshnessState.REQUIRES_REVIEW
            action = "TRIGGER_RECANDIDACY_REVIEW"
        elif score >= 0.45:
            state = FreshnessState.STALE
            action = "SCHEDULE_QUARTERLY_REEVALUATION"
        elif score >= 0.20:
            state = FreshnessState.AGING
            action = "MONITOR_UPCOMING_MATCHES"
        else:
            state = FreshnessState.FRESH
            action = "NO_ACTION_REQUIRED"

        assessment = DecisionFreshnessAssessment(
            decision_id=decision_id,
            decision_timestamp=decision_timestamp,
            freshness_state=state,
            staleness_score=round(score, 2),
            staleness_reasons=reasons,
            material_changes=changes,
            action_required=action,
        )

        self._assessments[decision_id] = assessment
        return assessment

    def get_assessment(self, decision_id: str) -> DecisionFreshnessAssessment | None:
        return self._assessments.get(decision_id)

    def list_assessments(self) -> list[DecisionFreshnessAssessment]:
        return list(self._assessments.values())

    def _seed_default_benchmarks_and_freshness(self) -> None:
        """Seeds versioned benchmarks and freshness evaluations for Arsenal decisions."""
        # Ball-Playing CB Progressive Passes Benchmark
        self.register_benchmark(
            metric_name="progressive_passes_per_90",
            scope=BenchmarkScope.DECISION_TIME_BENCHMARK,
            benchmark_version="benchmark_cb_2023_v1",
            p25=3.8,
            p50=5.1,
            p75=6.4,
            p90=7.8,
            sample_size=120,
            frozen_at="2023-07-01T00:00:00Z",
        )
        self.register_benchmark(
            metric_name="progressive_passes_per_90",
            scope=BenchmarkScope.CURRENT_BENCHMARK,
            benchmark_version="benchmark_cb_2024_v2",
            p25=4.1,
            p50=5.4,
            p75=6.8,
            p90=8.2,
            sample_size=145,
            frozen_at="2024-06-01T00:00:00Z",
        )

        # Timber 2023 Freshness Evaluation
        self.evaluate_decision_freshness(
            decision_id="dec_rec_timber_2023",
            decision_timestamp="2023-07-14T18:00:00Z",
            days_since_decision=365,
            performance_drift_detected=False,
            role_changed=False,
            market_valuation_changed_pct=+20.0,
            model_version_superseded=True,
            assumption_expired=True,
            injury_sustained=True,
        )

        # Rice 2023 Freshness Evaluation
        self.evaluate_decision_freshness(
            decision_id="dec_rice_arsenal_2023",
            decision_timestamp="2023-07-15T12:00:00Z",
            days_since_decision=365,
            performance_drift_detected=False,
            role_changed=False,
            market_valuation_changed_pct=+15.0,
            model_version_superseded=False,
            assumption_expired=False,
            injury_sustained=False,
        )


decision_freshness_v2_engine = DecisionFreshnessV2Engine()
