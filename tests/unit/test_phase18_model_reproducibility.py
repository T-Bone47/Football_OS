"""Phase 18 — the match model is reproducible and its evaluation is honest.

Runs in CI from a clean checkout: the committed dataset file and manifests
are enough to retrain the artifact bit for bit.
"""
from __future__ import annotations

import copy
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.ml import match_outcome as mo

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "data" / "models" / "match_outcome" / f"{mo.MODEL_ID}-{mo.MODEL_VERSION}"


def _dataset():
    return mo.dataset_from_jsonl((MODEL_DIR / "dataset.jsonl").read_bytes())


def test_committed_model_reproduces_bit_for_bit():
    sys.path.insert(0, str(ROOT / "scripts"))
    from reproduce_match_model import reproduce

    result = reproduce(from_database=False)
    assert result["status"] == "REPRODUCED", result.get("mismatches")
    manifest = json.loads((MODEL_DIR / "model_manifest.json").read_text())
    assert mo.artifact_sha256(json.loads((MODEL_DIR / "model.json").read_bytes())) == manifest["artifact_sha256"]


def test_test_window_never_influences_the_artifact():
    ds = _dataset()
    artifact, evaluation = mo.train(ds, mo.Windows())
    tampered = copy.deepcopy(ds)
    flip = {"H": "A", "A": "H", "D": "H"}
    for r in tampered.rows:
        if r.kickoff[:10] >= mo.Windows().validation_end:
            r.label = flip[r.label]
    artifact2, evaluation2 = mo.train(tampered, mo.Windows())
    assert mo.artifact_sha256(artifact2) == mo.artifact_sha256(artifact)  # weights and temperature unchanged
    assert evaluation2["test"]["model"] != evaluation["test"]["model"]  # only the measured performance moves


def test_validation_requires_a_confidence_interval_below_zero():
    ev = json.loads((MODEL_DIR / "evaluation_manifest.json").read_text())
    ci = ev["test"]["log_loss_difference_vs_baseline"]
    assert ev["verdict"] == "VALIDATED" and ci["ci95_high"] < 0
    for comp, v in ev["per_competition"].items():
        assert v["supported"] == (v["model"]["n"] >= mo.MIN_COMPETITION_TEST_ROWS
                                  and v["log_loss_difference_vs_baseline"]["ci95_high"] < 0), comp
    assert sorted(ev["supported_competitions"]) == sorted(c for c, v in ev["per_competition"].items() if v["supported"])


def _match(home, away, day, hs, as_, cs):
    return SimpleNamespace(id=uuid.uuid4(), provider="test-fixture", provider_fixture_id=f"{home}-{away}-{day}",
                           home_club_id=home, away_club_id=away, date=datetime(2016, 1, 1, tzinfo=timezone.utc) + timedelta(days=day),
                           status="FINISHED", home_score=hs, away_score=as_, competition_season_id=cs)


def test_features_never_see_the_future():
    cs = uuid.uuid4()
    teams = [uuid.uuid4() for _ in range(4)]
    past = []
    day = 0
    for rnd in range(8):
        for i in range(0, 4, 2):
            a, b = teams[(i + rnd) % 4], teams[(i + rnd + 1) % 4]
            past.append(_match(a, b, day, rnd % 3, (rnd + i) % 2, cs))
            day += 1
    base = mo.build_dataset(past, {cs: "Test"}).rows
    future = past + [_match(teams[0], teams[1], day + 5, 9, 0, cs), _match(teams[2], teams[3], day + 6, 0, 7, cs)]
    extended = mo.build_dataset(future, {cs: "Test"}).rows
    assert base and [r.features for r in extended[:len(base)]] == [r.features for r in base]
