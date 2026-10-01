"""Reproduce the registered match outcome model and compare it bit for bit.

    python scripts/reproduce_match_model.py                 # from the committed dataset file
    DATABASE_URL=... python scripts/reproduce_match_model.py --from-database   # rebuild the dataset from Silver

Status:
  REPRODUCED            dataset SHA-256, artifact SHA-256 and test metrics all equal the manifests
  MISMATCH              something differs (the differences are listed)
  REPRODUCTION_BLOCKED  the inputs are not available (no dataset file / no Silver data)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))


def reproduce(from_database: bool = False) -> dict:
    from app.ml import match_outcome as mo

    model_dir = ROOT / "data" / "models" / "match_outcome" / f"{mo.MODEL_ID}-{mo.MODEL_VERSION}"
    manifest_path = model_dir / "model_manifest.json"
    if not manifest_path.exists():
        return {"status": "REPRODUCTION_BLOCKED", "reason": f"{manifest_path.relative_to(ROOT)} not found"}
    manifest = json.loads(manifest_path.read_text())
    evaluation_ref = json.loads((model_dir / "evaluation_manifest.json").read_text())
    if from_database:
        import os

        import train_match_model as tm

        matches, competition_of, _, _ = asyncio.run(tm.load(os.environ["DATABASE_URL"]))
        if not competition_of:
            return {"status": "REPRODUCTION_BLOCKED", "reason": "no 2015/16 top-five Silver data in the database"}
        ds = mo.build_dataset(matches, competition_of)
        source = "silver_database"
    else:
        data_path = model_dir / "dataset.jsonl"
        if not data_path.exists():
            return {"status": "REPRODUCTION_BLOCKED", "reason": "dataset.jsonl not present"}
        ds = mo.dataset_from_jsonl(data_path.read_bytes())
        source = "committed_dataset_file"
    artifact, evaluation = mo.train(ds, mo.Windows())
    checks = {
        "dataset_sha256": (ds.sha256, manifest["dataset_sha256"]),
        "artifact_sha256": (mo.artifact_sha256(artifact), manifest["artifact_sha256"]),
        "test_metrics": (evaluation["test"], evaluation_ref["test"]),
        "supported_competitions": (evaluation["supported_competitions"], evaluation_ref["supported_competitions"]),
        "verdict": (evaluation["verdict"], evaluation_ref["verdict"]),
    }
    mismatches = {k: {"reproduced": a, "registered": b} for k, (a, b) in checks.items() if a != b}
    return {"status": "MISMATCH" if mismatches else "REPRODUCED", "source": source,
            "dataset_rows": len(ds.rows), "artifact_sha256": checks["artifact_sha256"][0],
            "dataset_sha256": checks["dataset_sha256"][0], "verdict": evaluation["verdict"],
            "test_log_loss": evaluation["test"]["model"]["log_loss"],
            "baseline_log_loss": evaluation["test"]["baseline_class_prior"]["log_loss"],
            "mismatches": mismatches}


async def record(result: dict) -> None:
    """Writes the reproduction outcome onto the registry row (the
    VALIDATED -> SHADOW promotion requires a REPRODUCED record)."""
    import os
    from datetime import datetime, timezone

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.models.operations import ModelRegistryEntry
    from app.ml import match_outcome as mo

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        row = (await s.execute(select(ModelRegistryEntry).where(
            ModelRegistryEntry.model_id == mo.MODEL_ID, ModelRegistryEntry.model_version == mo.MODEL_VERSION))).scalar_one_or_none()
        if row is not None and row.artifact_sha256 == result.get("artifact_sha256"):
            row.reproduction = {"status": result["status"], "source": result.get("source"),
                                "at": datetime.now(timezone.utc).isoformat(), "evidence": "evidence/reproducibility_evidence*.json"}
            await s.commit()
    await engine.dispose()


def main() -> int:
    from common import write_evidence

    from_db = "--from-database" in sys.argv
    result = reproduce(from_db)
    import os

    if os.environ.get("DATABASE_URL") and "--record" in sys.argv:
        asyncio.run(record(result))
    write_evidence("reproducibility_evidence" + ("_database" if from_db else ""), " ".join(sys.argv),
                   inputs={"model": "match_outcome_logit 2.0.0", "source": result.get("source")},
                   outputs=result, status=result["status"])
    print(json.dumps({k: v for k, v in result.items() if k != "mismatches"}, indent=1))
    if result.get("mismatches"):
        print("MISMATCHES:", json.dumps(result["mismatches"], indent=1)[:2000])
    return 0 if result["status"] == "REPRODUCED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
