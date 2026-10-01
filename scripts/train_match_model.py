"""Train, evaluate and register the match outcome model from Silver data.

    DATABASE_URL=postgresql+asyncpg://.../fios_p17_live python scripts/train_match_model.py

Writes data/models/match_outcome/<model_id>-<version>/ with the artifact and
five manifests (dataset, feature, training, evaluation, model), each carrying
SHA-256 links, then upserts the model into ops_model_registry. The registry
state follows the evidence: VALIDATED only when the test window beats the
class-prior baseline; otherwise BLOCKED with the reason.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

SCOPE_SEASON = "2015"  # Silver stores the season by its start year (2015/16)
SCOPE_COMPETITIONS = ["Premier League", "La Liga", "1. Bundesliga", "Serie A", "Ligue 1"]
OUT_ROOT = ROOT / "data" / "models" / "match_outcome"


def write_json(path: Path, obj) -> str:
    from app.ml.match_outcome import canonical, sha256_hex

    data = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    path.write_text(data)
    return sha256_hex(canonical(obj))


async def load(url: str):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from app.db.models.canonical import Competition, CompetitionSeason, Match, Season
    from app.db.models.provenance import DataSnapshot

    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        matches = list((await s.execute(select(Match))).scalars().all())
        scope_rows = (await s.execute(
            select(CompetitionSeason.id, Competition.name, Competition.country, Season.name)
            .join(Competition, Competition.id == CompetitionSeason.competition_id)
            .join(Season, Season.id == CompetitionSeason.season_id)
            .where(Season.name == SCOPE_SEASON, Competition.name.in_(SCOPE_COMPETITIONS)))).all()
        competition_of = {cs_id: f"{name} ({country})" for cs_id, name, country, _ in scope_rows}
        snaps = (await s.execute(
            select(DataSnapshot.sha256).join(Match, Match.snapshot_id == DataSnapshot.id)
            .where(Match.competition_season_id.in_(list(competition_of))).distinct())).scalars().all()
        unlinked = sum(1 for m in matches if m.competition_season_id in competition_of and m.snapshot_id is None)
    await engine.dispose()
    return matches, competition_of, sorted(snaps), unlinked


async def register(url: str, artifact: dict, sha: str, uri: str, dataset_sha: str, evaluation: dict, lineage: str) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from app.db.models.operations import ModelRegistryEntry

    validated = evaluation["verdict"] == "VALIDATED" and lineage == "VERIFIED"
    state = "VALIDATED" if validated else "BLOCKED"
    reason = ("test window beats the class-prior baseline; dataset lineage verified" if validated else
              f"verdict {evaluation['verdict']}; lineage {lineage}")
    engine = create_async_engine(url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        row = (await s.execute(select(ModelRegistryEntry).where(
            ModelRegistryEntry.model_id == artifact["model_id"],
            ModelRegistryEntry.model_version == artifact["model_version"]))).scalar_one_or_none()
        fields = dict(domain=artifact["domain"], feature_version=artifact["feature_set_version"],
                      dataset_version=f"statsbomb-2015-16-top5@{dataset_sha[:12]}", artifact_sha256=sha,
                      artifact_uri=uri, dataset_sha256=dataset_sha, windows=evaluation["windows"],
                      supported_competitions=evaluation["supported_competitions"] if validated else [],
                      supported_horizons=["PRE_MATCH"], validation_metrics=evaluation, lineage_status=lineage,
                      min_history_matches=artifact["min_history_matches"], max_feature_age_hours=72.0,
                      status_reason=reason)
        if row is None:
            row = ModelRegistryEntry(model_id=artifact["model_id"], model_version=artifact["model_version"],
                                     deployment_state=state, **fields)
            s.add(row)
        else:
            if row.deployment_state in ("SHADOW", "CANARY", "PRODUCTION") and not validated:
                state = "BLOCKED"  # new evidence withdraws serving
            elif row.deployment_state in ("SHADOW", "CANARY", "PRODUCTION"):
                state = row.deployment_state  # retraining never promotes or demotes by itself
            for k, v in fields.items():
                setattr(row, k, v)
            row.deployment_state = state
        await s.commit()
        out = {"registry_id": str(row.id), "deployment_state": row.deployment_state, "status_reason": reason}
    await engine.dispose()
    return out


async def main() -> int:
    from app.ml import match_outcome as mo

    url = os.environ["DATABASE_URL"]
    matches, competition_of, snapshot_shas, unlinked = await load(url)
    if not competition_of:
        print("REPRODUCTION_BLOCKED: no 2015/16 top-five-league Silver data in this database")
        return 2
    ds = mo.build_dataset(matches, competition_of)
    windows = mo.Windows()
    artifact, evaluation = mo.train(ds, windows)
    sha = mo.artifact_sha256(artifact)
    lineage = "VERIFIED" if unlinked == 0 and snapshot_shas else "UNVERIFIED"

    out = OUT_ROOT / f"{mo.MODEL_ID}-{mo.MODEL_VERSION}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_bytes(mo.artifact_bytes(artifact))
    (out / "dataset.jsonl").write_bytes(b"".join(line + b"\n" for line in ds.canonical_lines()))
    dataset_manifest = {
        "dataset_id": "statsbomb-2015-16-top5-match-outcomes", "dataset_sha256": ds.sha256,
        "rows": len(ds.rows), "excluded": ds.excluded, "provider": "statsbomb (open data)",
        "scope": {"season": SCOPE_SEASON, "competitions": sorted(set(competition_of.values()))},
        "source_snapshot_sha256": snapshot_shas, "silver_rows_without_snapshot": unlinked,
        "lineage_status": lineage,
        "row_format": "canonical JSON per line: provider, fixture (provider match id), kickoff (UTC), competition, "
                      "features (rounded to %d dp), label (H/D/A)" % mo.DECIMALS,
        "as_of_rule": "features use only finished matches strictly before kickoff",
        "first_kickoff": ds.rows[0].kickoff if ds.rows else None,
        "last_kickoff": ds.rows[-1].kickoff if ds.rows else None,
    }
    feature_manifest = {
        "feature_set_version": artifact["feature_set_version"], "features": mo.FEATURES,
        "builder": "app.prediction.features.PreMatchFeatureBuilder", "min_history_matches": mo.MIN_HISTORY,
        "missing_value_policy": "row excluded (never imputed)",
    }
    training_manifest = {
        "algorithm": "multinomial logistic regression (scikit-learn, lbfgs) on standardised features",
        "C": mo.C_REGULARISATION, "random_seed": mo.RANDOM_SEED, "classes": mo.CLASSES,
        "windows": evaluation["windows"], "rows": evaluation["rows"],
        "temperature": {"fitted_on": "validation window", "grid": [mo.TEMPERATURE_GRID[0], mo.TEMPERATURE_GRID[-1], 0.01],
                        "value": artifact["temperature"]},
        "dataset_sha256": ds.sha256,
    }
    hashes = {
        "dataset_manifest.json": write_json(out / "dataset_manifest.json", dataset_manifest),
        "feature_manifest.json": write_json(out / "feature_manifest.json", feature_manifest),
        "training_manifest.json": write_json(out / "training_manifest.json", training_manifest),
        "evaluation_manifest.json": write_json(out / "evaluation_manifest.json", evaluation),
    }
    uri = f"match_outcome/{mo.MODEL_ID}-{mo.MODEL_VERSION}/model.json"
    model_manifest = {"model_id": mo.MODEL_ID, "model_version": mo.MODEL_VERSION, "artifact_uri": uri,
                      "artifact_sha256": sha, "dataset_sha256": ds.sha256, "manifests_sha256": hashes,
                      "verdict": evaluation["verdict"], "lineage_status": lineage}
    write_json(out / "model_manifest.json", model_manifest)
    reg = await register(url, artifact, sha, uri, ds.sha256, evaluation, lineage)
    print(json.dumps({"artifact_sha256": sha, "dataset_sha256": ds.sha256, "rows": evaluation["rows"],
                      "excluded": ds.excluded, "test": evaluation["test"], "verdict": evaluation["verdict"],
                      "supported": evaluation["supported_competitions"], "registry": reg}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
