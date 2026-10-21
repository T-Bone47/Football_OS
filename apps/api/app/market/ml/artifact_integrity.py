"""Model-artifact integrity and strict feature-schema validation (handoff §7.7, R8/R20).

Pure stdlib on purpose: this runs BEFORE any pickle/joblib load. A pickle executes code on load,
so an artifact whose bytes do not match its pinned SHA-256 must never reach joblib.load().
"""
from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path


class ArtifactIntegrityError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def artifact_path(base_dir: Path | str, model_id: str) -> Path:
    """<base_dir>/<model_id>.joblib, rejecting ids that could escape base_dir (manifests are data)."""
    if not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id) or ".." in model_id:
        raise ArtifactIntegrityError("INVALID_MODEL_ID", "model id must match [A-Za-z0-9_.-]{1,128}")
    return Path(base_dir) / f"{model_id}.joblib"


def sha256_file(path: Path | str, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_artifact(path: Path | str, pinned_sha256: str | None) -> str:
    """Return the verified SHA-256 or raise ArtifactIntegrityError (fail closed)."""
    target = Path(path)
    if not target.is_file():
        raise ArtifactIntegrityError("ARTIFACT_MISSING", f"no artifact file at {target.name}")
    if not pinned_sha256:
        raise ArtifactIntegrityError("ARTIFACT_HASH_NOT_PINNED", "registry entry has no artifact_sha256")
    actual = sha256_file(target)
    if actual != pinned_sha256.lower():
        raise ArtifactIntegrityError(
            "ARTIFACT_HASH_MISMATCH", f"{target.name}: expected {pinned_sha256[:12]}..., got {actual[:12]}..."
        )
    return actual


def validate_feature_mapping(
    features: Mapping[str, object], expected_names: Sequence[str]
) -> tuple[list[float], list[str]]:
    """Strict schema check. Returns (values in model order, names of missing features).

    - keys must equal the model's feature names exactly (no extras, none absent);
    - a value is a finite number, or None/NaN/inf meaning "missing" (reported, never zero-filled);
    - bool and non-numeric values are rejected.
    Missing values come back as NaN so the caller can count them for the sufficiency gate.
    """
    expected = list(expected_names)
    got = set(features)
    absent = [n for n in expected if n not in got]
    extra = sorted(got - set(expected))
    if absent or extra:
        raise ArtifactIntegrityError("FEATURE_SCHEMA_MISMATCH", f"absent={absent[:5]} unexpected={extra[:5]}")
    values: list[float] = []
    missing: list[str] = []
    for name in expected:
        raw = features[name]
        if raw is None:
            values.append(math.nan)
            missing.append(name)
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ArtifactIntegrityError("FEATURE_SCHEMA_MISMATCH", f"{name} must be a number or null")
        number = float(raw)
        if not math.isfinite(number):
            values.append(math.nan)
            missing.append(name)
        else:
            values.append(number)
    return values, missing
