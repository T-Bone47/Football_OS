"""Register the on-disk models in the authoritative registry (ops_model_registry).

    DATABASE_URL=... python scripts/register_models.py

- match_outcome_logit 2.0.0 from its committed manifests (VALIDATED or
  BLOCKED, per its own evaluation evidence)
- the valuation model as UNVERIFIED (see app/ml/valuation_registry.py)
Idempotent; never promotes anything.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.ml.valuation_registry import register_valuation_model
    from app.phase17.model_ops import ensure_match_model_registered

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        match = await ensure_match_model_registered(s)
        valuation = await register_valuation_model(s)
        # The pre-Phase-18 match model: five hand-typed weights, no artifact,
        # no training data. Kept in the registry for lineage, never servable.
        from sqlalchemy import select

        from app.db.models.operations import ModelRegistryEntry

        legacy = (await s.execute(select(ModelRegistryEntry).where(
            ModelRegistryEntry.model_id == "calibrated_multinomial_logit_v1"))).scalars().all()
        for row in legacy:
            row.deployment_state = "BLOCKED"
            row.status_reason = "hand-typed parameters with no training code, dataset or artifact (Phase 18, N3)"
        await s.commit()
        out = {m.model_id: {"state": m.deployment_state, "lineage": m.lineage_status, "artifact_sha256": m.artifact_sha256}
               for m in (match, valuation) if m is not None}
    await engine.dispose()
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
