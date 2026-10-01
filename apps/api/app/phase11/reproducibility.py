"""Phase 11 — Pipeline Determinism & Dual Replay Engine (§21).

Executes dual independent runs across:
  - EPL match pipeline
  - La Liga match pipeline
  - Valuation dataset pipeline
  - Player Intelligence feature pipeline
and verifies 100% bit-for-bit equality across all stage SHA-256 digests:
Bronze -> Silver -> Features -> Dataset -> Model -> Calibration -> Prediction -> Decision.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


@dataclass
class StageDigest:
    stage_name: str
    pass_1_hash: str
    pass_2_hash: str
    matches: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DualReplayResult:
    """Deterministic replay audit record (§21)."""
    pipeline_name: str
    competition: str
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    stages: list[StageDigest] = field(default_factory=list)
    total_stages: int = 0
    divergence_count: int = 0
    deterministic: bool = True
    overall_checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stages"] = [s.to_dict() for s in self.stages]
        return d


class PipelineReplayEngine:
    """Executes dual deterministic pipeline replay verification."""

    def __init__(self) -> None:
        self._history: list[DualReplayResult] = []

    def _hash_stage(self, data: Any) -> str:
        payload = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def execute_replay(
        self,
        pipeline_name: str,
        competition: str,
        stage_generator_fn: Any,
    ) -> DualReplayResult:
        """Executes two independent passes of the pipeline and verifies zero divergence."""
        # Pass 1
        pass_1_stages = stage_generator_fn()
        # Pass 2
        pass_2_stages = stage_generator_fn()

        stage_digests: list[StageDigest] = []
        divergences = 0

        for stage_name in pass_1_stages.keys():
            h1 = self._hash_stage(pass_1_stages[stage_name])
            h2 = self._hash_stage(pass_2_stages[stage_name])
            is_match = (h1 == h2)
            if not is_match:
                divergences += 1
            stage_digests.append(StageDigest(
                stage_name=stage_name,
                pass_1_hash=h1,
                pass_2_hash=h2,
                matches=is_match,
            ))

        overall_hash = hashlib.sha256(
            "".join(s.pass_1_hash for s in stage_digests).encode("utf-8")
        ).hexdigest()

        result = DualReplayResult(
            pipeline_name=pipeline_name,
            competition=competition,
            stages=stage_digests,
            total_stages=len(stage_digests),
            divergence_count=divergences,
            deterministic=(divergences == 0),
            overall_checksum=overall_hash,
        )

        self._history.append(result)
        return result

    def list_replays(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._history]


pipeline_replay_engine = PipelineReplayEngine()
