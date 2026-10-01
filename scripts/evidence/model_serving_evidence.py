"""Model serving evidence on real Silver data.

    DATABASE_URL=postgresql+asyncpg://.../fios_p17_live python scripts/evidence/model_serving_evidence.py

1. Validation backtest over the model's held-out test window (real 2015/16
   matches): every SERVED probability must equal the artifact applied to the
   training dataset's features for that fixture (no train/serve skew).
2. A LIVE request: the model is VALIDATED, not promoted, so it is refused.
3. Integrity drills (rolled back): wrong registry SHA-256 and a foreign
   feature schema must be refused with their own statuses.
4. The valuation model: refused by the registry (UNVERIFIED).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

from common import ROOT, write_evidence

MODEL_DIR = ROOT / "data" / "models" / "match_outcome" / "match_outcome_logit-2.0.0"


async def main() -> int:
    import numpy as np
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.models.canonical import Match
    from app.ml import match_outcome as mo
    from app.ml.serving import load_registered_artifact
    from app.ml.valuation_registry import ModelNotServable, register_valuation_model, valuation_gate
    from app.phase17.feature_refresh import refresh_competition_season
    from app.phase17.model_ops import MODE_LIVE, MODE_VALIDATION, ensure_match_model_registered, infer_match

    dataset = {(r.provider, r.provider_fixture_id): r for r in
               mo.dataset_from_jsonl((MODEL_DIR / "dataset.jsonl").read_bytes()).rows}
    test_rows = [r for r in dataset.values() if r.kickoff[:10] >= mo.Windows().validation_end]
    engine = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    out: dict = {}
    async with Session() as s:
        model = await ensure_match_model_registered(s)
        artifact = load_registered_artifact(model)
        out["model"] = {"model_id": model.model_id, "version": model.model_version, "state": model.deployment_state,
                        "artifact_sha256": model.artifact_sha256, "reproduction": model.reproduction}
        fixtures = {r.provider_fixture_id for r in test_rows}
        matches = (await s.execute(select(Match).where(Match.provider == "statsbomb",
                                                       Match.provider_fixture_id.in_(fixtures)))).scalars().all()
        for cs in {m.competition_season_id for m in matches}:
            await refresh_competition_season(s, cs)
        await s.commit()

        statuses, skew = Counter(), []
        for m in matches:
            inf = await infer_match(s, m.id, as_of=m.date - timedelta(seconds=1), mode=MODE_VALIDATION)
            statuses[inf.status] += 1
            if inf.status == "SERVED":
                row = dataset[(m.provider, m.provider_fixture_id)]
                expected = mo.predict_proba(artifact, np.array([[row.features[f] for f in mo.FEATURES]]))[0]
                got = np.array([inf.output["home_win"], inf.output["draw"], inf.output["away_win"]])
                if float(np.abs(expected - got).max()) > 1e-5:
                    skew.append({"fixture": m.provider_fixture_id, "expected": expected.round(6).tolist(),
                                 "served": got.tolist()})
        await s.commit()
        out["validation_backtest"] = {"test_window_fixtures": len(test_rows), "silver_matches_found": len(matches),
                                      "statuses": dict(statuses), "train_serve_skew": skew}

        sample = matches[0]
        sample_id, cutoff = sample.id, sample.date - timedelta(seconds=1)  # plain values survive rollbacks
        live = await infer_match(s, sample_id, mode=MODE_LIVE)
        out["live_request"] = {"status": live.status, "reasons": live.reasons}
        await s.commit()

        drills = {}
        original = model.artifact_sha256
        model.artifact_sha256 = "0" * 64
        r = await infer_match(s, sample_id, as_of=cutoff, mode=MODE_VALIDATION)
        drills["wrong_registry_sha256"] = {"status": r.status, "reasons": list(r.reasons)}
        await s.rollback()
        model = await ensure_match_model_registered(s)
        model.feature_version = "match_prediction_v0"
        r = await infer_match(s, sample_id, as_of=cutoff, mode=MODE_VALIDATION)
        drills["foreign_feature_schema"] = {"status": r.status, "reasons": list(r.reasons)}
        await s.rollback()
        model = await ensure_match_model_registered(s)
        drills["registry_restored"] = model.artifact_sha256 == original
        out["integrity_drills"] = drills

        val = await register_valuation_model(s)
        await s.commit()
        try:
            await valuation_gate(s, val.model_id if val else None)
            out["valuation"] = {"status": "SERVABLE"}
        except ModelNotServable as e:
            out["valuation"] = e.body()
    await engine.dispose()

    ok = (out["validation_backtest"]["statuses"].get("SERVED", 0) > 0 and not skew
          and out["live_request"]["status"] == "MODEL_UNAVAILABLE"
          and drills["wrong_registry_sha256"]["status"] == "MODEL_ARTIFACT_MISMATCH"
          and drills["foreign_feature_schema"]["status"] == "FEATURE_SCHEMA_MISMATCH"
          and drills["registry_restored"] and out["valuation"]["status"] == "MODEL_UNVERIFIED")
    write_evidence("model_serving_evidence", " ".join(sys.argv), inputs={"database": os.environ["DATABASE_URL"].rsplit("/", 1)[-1],
                   "model_dir": str(MODEL_DIR.relative_to(ROOT))}, outputs=out, status="VERIFIED" if ok else "FAILED")
    print(json.dumps({k: v for k, v in out.items() if k != "integrity_drills"}, indent=1, default=str)[:2500])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(asyncio.run(main()))
