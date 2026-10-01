"""Phase 17 secret scan (§46, adversarial 28).

Looks for (a) the exact credential values configured in the local .env and
(b) generic credential patterns, in: tracked files, untracked files that
would be committed, the full git history, Phase 17 evidence JSON, the
frontend production bundle, and API server logs. Prints locations and
pattern names only — never a matched value.

Usage:  python tools/phase17/secret_scan.py [--bundle DIR]
Writes: docs/evidence/phase17/secret_scan.json
"""
from __future__ import annotations

import argparse
import glob
import re
import subprocess
from pathlib import Path

from common import EVIDENCE, ROOT, now, write_evidence

PATTERNS = {
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key_block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "credential_assignment": re.compile(
        r"(?i)(api[_-]?key|secret|token|password|passwd)[ \t]*[:=][ \t]*['\"]?([A-Za-z0-9_\-]{20,})"),
    "bearer_token": re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{24,}"),
}
# Known, deliberate non-secrets: test fixtures and documented placeholders.
ALLOW = re.compile(r"(?i)(secret_12345|super_secret_pwd|sk-live-0123456789abcdef|s3-secret-ABCDEF123456|"
                   r"af-key-987654321|k-shared-1234567890|\$\{[A-Z_]+\}|stored only as a SHA-256|"
                   r"staging-s3-secret-value|production-s3-secret-value|staging-db-secret-value|production-db-secret-value|"
                   # Emergent template's local test-session fixtures (Football_OS-frontend/backend/tests):
                   r"test_ui_football\w*|"
                   # Library code in the bundle's source map (axios: password = decodeURIComponent(...)):
                   r"decodeURIComponent)")
SKIP_SUFFIXES = (".joblib", ".png", ".jpg", ".ico", ".woff", ".woff2", ".lock")


def configured_secrets() -> dict[str, str]:
    env = ROOT / ".env"
    out: dict[str, str] = {}
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if v.strip() and re.search(r"(?i)key|secret|token|password", k):
                    out[k.strip()] = v.strip()
    return out


def scan_text(label: str, text: str, secrets: dict[str, str], findings: list[dict]) -> None:
    for name, value in secrets.items():
        if len(value) >= 8 and value in text:
            line = text[: text.index(value)].count("\n") + 1
            findings.append({"location": label, "line": line, "kind": f"configured_secret:{name}"})
    for kind, pat in PATTERNS.items():
        for m in pat.finditer(text):
            if ALLOW.search(m.group(0)):
                continue
            findings.append({"location": label, "line": text[: m.start()].count("\n") + 1, "kind": kind})


def main(bundle: str | None) -> None:
    secrets = configured_secrets()
    report: dict = {"configured_secret_names": sorted(secrets), "scopes": {}}
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout  # noqa: E731

    scopes = {
        "tracked_files": git("ls-files").split(),
        "untracked_to_be_committed": git("ls-files", "--others", "--exclude-standard").split(),
    }
    for scope, files in scopes.items():
        findings: list[dict] = []
        for f in files:
            p = ROOT / f
            if not p.is_file() or p.suffix in SKIP_SUFFIXES or p.stat().st_size > 5_000_000:
                continue
            try:
                scan_text(f, p.read_text(errors="ignore"), secrets, findings)
            except OSError:
                continue
        report["scopes"][scope] = {"files_scanned": len(files), "findings": findings}

    history: list[dict] = []
    scan_text("git log -p --all", git("log", "-p", "--all"), secrets, history)
    report["scopes"]["git_history"] = {"findings": history}

    evid: list[dict] = []
    for p in EVIDENCE.glob("*.json"):
        if p.name != "secret_scan.json":
            scan_text(f"docs/evidence/phase17/{p.name}", p.read_text(), secrets, evid)
    report["scopes"]["evidence_json"] = {"findings": evid}

    logs: list[dict] = []
    for p in glob.glob("/tmp/fios-uvicorn-*.log"):
        scan_text(p, Path(p).read_text(errors="ignore"), secrets, logs)
    report["scopes"]["api_server_logs"] = {"files": len(glob.glob('/tmp/fios-uvicorn-*.log')), "findings": logs}

    if bundle:
        b: list[dict] = []
        files = [p for p in Path(bundle).rglob("*") if p.is_file() and p.suffix in (".js", ".html", ".map", ".json")]
        for p in files:
            scan_text(str(p.relative_to(bundle)), p.read_text(errors="ignore"), secrets, b)
        report["scopes"]["frontend_bundle"] = {"files_scanned": len(files), "findings": b}
    else:
        report["scopes"]["frontend_bundle"] = {"status": "NOT_TESTED", "reason": "no bundle path given"}

    report["env_file_ignored_by_git"] = bool(git("check-ignore", ".env").strip())
    report["dockerfile_copies_env"] = ".env" in (ROOT / "apps" / "api" / "Dockerfile").read_text()
    report["dockerignore_excludes_env"] = (ROOT / ".dockerignore").exists() and ".env" in (ROOT / ".dockerignore").read_text()
    total = sum(len(v.get("findings", [])) for v in report["scopes"].values())
    report["total_findings"] = total
    report["finished_at"] = now()
    print("findings:", total)
    for scope, v in report["scopes"].items():
        for f in v.get("findings", [])[:20]:
            print(f"  {scope}: {f['location']}:{f['line']} {f['kind']}")
    print("wrote", write_evidence("secret_scan", report))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle")
    main(ap.parse_args().bundle)
