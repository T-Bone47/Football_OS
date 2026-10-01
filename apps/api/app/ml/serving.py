"""Loading a registered model artifact for inference (Phase 18, R8 / R20).

A model is served only from the artifact its registry row names, and only
if the bytes on disk hash to the registered SHA-256 and the artifact's
feature schema is the one the feature builder produces. Each failure has its
own status; nothing falls back to built-in parameters.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.prediction.features import FEATURE_SET_VERSION

REPO_ROOT = Path(__file__).resolve().parents[4]


class ArtifactRefused(Exception):
    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def artifact_root() -> Path:
    configured = Path(get_settings().model_artifact_dir)
    if configured.is_absolute():
        return configured.resolve()
    # Relative paths resolve against the working directory, then the repository.
    cwd_based = (Path.cwd() / configured).resolve()
    return cwd_based if cwd_based.exists() else (REPO_ROOT / configured).resolve()


def load_registered_artifact(entry: Any) -> dict[str, Any]:
    """`entry`: an ops_model_registry row. Returns the parsed artifact or raises
    ArtifactRefused(MODEL_UNAVAILABLE | MODEL_ARTIFACT_MISMATCH | FEATURE_SCHEMA_MISMATCH)."""
    if not entry.artifact_uri or not entry.artifact_sha256:
        raise ArtifactRefused("MODEL_UNAVAILABLE", "registry row has no artifact URI/SHA-256; nothing can be loaded")
    root = artifact_root()
    path = (root / entry.artifact_uri).resolve()
    if root not in path.parents:
        raise ArtifactRefused("MODEL_UNAVAILABLE", "artifact URI escapes the artifact directory")
    if not path.is_file():
        raise ArtifactRefused("MODEL_UNAVAILABLE", f"artifact not found at {entry.artifact_uri}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry.artifact_sha256:
        raise ArtifactRefused("MODEL_ARTIFACT_MISMATCH",
                              f"artifact SHA-256 {digest[:16]}... does not match the registry {entry.artifact_sha256[:16]}...")
    try:
        artifact = json.loads(data)
    except ValueError as exc:
        raise ArtifactRefused("MODEL_ARTIFACT_MISMATCH", f"artifact is not valid JSON ({exc})") from exc
    if artifact.get("feature_set_version") != FEATURE_SET_VERSION or entry.feature_version != FEATURE_SET_VERSION:
        raise ArtifactRefused("FEATURE_SCHEMA_MISMATCH",
                              f"artifact features {artifact.get('feature_set_version')} / registry {entry.feature_version}; "
                              f"the builder produces {FEATURE_SET_VERSION}")
    return artifact
