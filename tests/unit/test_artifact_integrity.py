"""Artifact hash pinning + strict feature schema (R8/R20). The hash check runs before any pickle load."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.market.ml.artifact_integrity import (
    ArtifactIntegrityError,
    sha256_file,
    validate_feature_mapping,
    verify_artifact,
)

VALUATION_DIR = Path(__file__).resolve().parents[2] / "data" / "models" / "valuation"


def test_verify_artifact_accepts_matching_pin(tmp_path):
    f = tmp_path / "m.joblib"
    f.write_bytes(b"model-bytes")
    assert verify_artifact(f, sha256_file(f).upper()) == sha256_file(f)


def test_verify_artifact_fails_closed(tmp_path):
    f = tmp_path / "m.joblib"
    f.write_bytes(b"model-bytes")
    good = sha256_file(f)
    f.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError) as mismatch:
        verify_artifact(f, good)
    assert mismatch.value.code == "ARTIFACT_HASH_MISMATCH"
    with pytest.raises(ArtifactIntegrityError) as unpinned:
        verify_artifact(f, None)
    assert unpinned.value.code == "ARTIFACT_HASH_NOT_PINNED"
    with pytest.raises(ArtifactIntegrityError) as missing:
        verify_artifact(tmp_path / "nope.joblib", good)
    assert missing.value.code == "ARTIFACT_MISSING"


NAMES = ["age", "minutes", "rating"]


def test_feature_mapping_returns_model_order_and_flags_missing():
    values, missing = validate_feature_mapping({"rating": 7, "age": 24.0, "minutes": None}, NAMES)
    assert values[0] == 24.0 and values[2] == 7.0 and math.isnan(values[1])
    assert missing == ["minutes"]


def test_non_finite_values_are_missing_not_zero():
    values, missing = validate_feature_mapping({"age": float("inf"), "minutes": float("nan"), "rating": 1}, NAMES)
    assert missing == ["age", "minutes"] and all(math.isnan(v) for v in values[:2])


@pytest.mark.parametrize(
    "features",
    [{"age": 1, "minutes": 2}, {"age": 1, "minutes": 2, "rating": 3, "extra": 4}, {"age": True, "minutes": 2, "rating": 3}, {"age": "24", "minutes": 2, "rating": 3}],
)
def test_schema_violations_rejected(features):
    with pytest.raises(ArtifactIntegrityError) as exc:
        validate_feature_mapping(features, NAMES)
    assert exc.value.code == "FEATURE_SCHEMA_MISMATCH"


def test_repo_valuation_artifact_matches_its_pinned_hash():
    """The committed manifest must pin the committed artifact's real SHA-256."""
    manifest = json.loads((VALUATION_DIR / "registry_manifest.json").read_text())
    entry = manifest["models"][manifest["active_model_id"]]
    artifact = VALUATION_DIR / f"{entry['model_id']}.joblib"
    assert verify_artifact(artifact, entry.get("artifact_sha256")) == sha256_file(artifact)
    assert not (entry["artifact_location"].startswith("C:") or "\\" in entry["artifact_location"]), "non-portable artifact path"
