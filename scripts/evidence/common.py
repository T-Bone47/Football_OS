"""Shared plumbing for the Phase 18 evidence harness.

Every script writes evidence/<name>.json with: timestamp, git_commit,
environment, command, inputs, outputs, status and sha256 (of the canonical
JSON of everything else). Scripts never write a value they did not measure;
anything unavailable is recorded with an explicit status.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "evidence"
sys.path.insert(0, str(ROOT / "apps" / "api"))


def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("+uncommitted-changes" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN"


def environment() -> dict[str, Any]:
    return {
        "host": platform.node(), "platform": platform.platform(), "python": platform.python_version(),
        "app_environment": os.environ.get("ENVIRONMENT", "development"),
        "execution_context": os.environ.get("EVIDENCE_CONTEXT", "claude-code-cloud-sandbox"),
    }


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_evidence(name: str, command: str, inputs: dict[str, Any], outputs: dict[str, Any], status: str) -> Path:
    body = {
        "evidence": name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "environment": environment(),
        "command": command,
        "inputs": inputs,
        "outputs": outputs,
        "status": status,
    }
    body["sha256"] = sha256_bytes(canonical(body))
    EVIDENCE_DIR.mkdir(exist_ok=True)
    path = EVIDENCE_DIR / f"{name}.json"
    path.write_text(json.dumps(body, indent=2, sort_keys=True, default=str) + "\n")
    print(f"{name}: {status} -> {path.relative_to(ROOT)}")
    return path


def verify_evidence(path: Path) -> bool:
    body = json.loads(path.read_text())
    claimed = body.pop("sha256", None)
    return claimed == sha256_bytes(canonical(body))
