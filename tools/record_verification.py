#!/usr/bin/env python3
"""Record a verification run (environment probe + step results + junit summary) as markdown.

Pure standard library so it runs before any dependency is installed. Rules:
  * a step is PASSED only if it ran and exited 0; BLOCKED/FAILED steps must say why;
  * the run is VERIFIED only if every step PASSED and the junit report shows tests that ran clean.

CLI (used by tools/verify_environment.sh):
  record_verification.py add-step --file steps.jsonl --name N --status S --command C --detail D
  record_verification.py render   --steps steps.jsonl [--junit report.xml] --out record.md
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

NOT_FOUND = "NOT_FOUND"
STATUSES = ("PASSED", "FAILED", "BLOCKED", "NOT_RUN")
PROBES = (
    ("python3", ("--version",)), ("pip", ("--version",)), ("git", ("--version",)), ("node", ("--version",)),
    ("npm", ("--version",)), ("yarn", ("--version",)), ("docker", ("--version",)), ("psql", ("--version",)),
    ("pg_ctl", ("--version",)), ("pytest", ("--version",)), ("alembic", ("--version",)),
)


@dataclass
class StepResult:
    name: str
    command: str
    status: str
    detail: str = ""


@dataclass
class JunitSummary:
    tests: int
    failures: int
    errors: int
    skipped: int
    failed_tests: list[str] = field(default_factory=list)
    skipped_tests: list[str] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return self.tests - self.failures - self.errors - self.skipped


def probe_tool(name: str, version_args=("--version",), *, runner=subprocess.run, which=shutil.which) -> str:
    """Version line of an installed tool, NOT_FOUND if absent, UNREADABLE if it will not answer. Never a guess."""
    path = which(name)
    if path is None:
        return NOT_FOUND
    try:
        out = runner([path, *version_args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return f"UNREADABLE ({path})"
    lines = ((out.stdout or "") or (out.stderr or "")).strip().splitlines()
    return lines[0] if lines else f"UNREADABLE ({path})"


def parse_junit(xml_text: str) -> JunitSummary:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"not a junit report: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise ValueError("not a junit report: no <testsuite> element")
    summary = JunitSummary(0, 0, 0, 0)
    for suite in suites:
        summary.tests += int(suite.get("tests", 0))
        summary.failures += int(suite.get("failures", 0))
        summary.errors += int(suite.get("errors", 0))
        summary.skipped += int(suite.get("skipped", 0))
        for case in suite.iter("testcase"):
            ident = f"{case.get('classname', '')}::{case.get('name', '')}"
            if case.find("failure") is not None or case.find("error") is not None:
                summary.failed_tests.append(ident)
            skip = case.find("skipped")
            if skip is not None:
                reason = skip.get("message")
                summary.skipped_tests.append(f"{ident} ({reason})" if reason else ident)
    return summary


def render_record(*, date: str, environment: dict[str, str], steps: list[StepResult], junit: JunitSummary | None, limitations: list[str]) -> str:
    for step in steps:
        if step.status not in STATUSES:
            raise ValueError(f"unknown status {step.status!r} for step {step.name}")
        if step.status in ("BLOCKED", "FAILED") and not step.detail.strip():
            raise ValueError(f"step {step.name} is {step.status} but gives no reason")
    clean = junit is not None and junit.tests > 0 and junit.failures == 0 and junit.errors == 0
    verified = bool(steps) and all(s.status == "PASSED" for s in steps) and clean

    lines = [f"# Verification record {date}", "", f"Overall: {'VERIFIED' if verified else 'NOT VERIFIED'}", "", "## Environment", ""]
    lines += [f"- {k}: {v}" for k, v in environment.items()]
    lines += ["", "## Steps", "", "| Step | Status | Command | Detail |", "|---|---|---|---|"]
    for s in steps:
        cell = lambda t: t.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {s.name} | {s.status} | `{cell(s.command)}` | {cell(s.detail)} |")
    lines += ["", "## Tests", ""]
    if junit is None:
        lines.append("No junit report: the test suite did not run in this record.")
    else:
        lines.append(f"passed={junit.passed} failed={junit.failures} errors={junit.errors} skipped={junit.skipped} total={junit.tests}")
        lines += [f"- FAILED {t}" for t in junit.failed_tests] + [f"- SKIPPED {t}" for t in junit.skipped_tests]
    if limitations:
        lines += ["", "## Limitations", ""] + [f"- {x}" for x in limitations]
    return "\n".join(lines) + "\n"


def probe_environment() -> dict[str, str]:
    env = {"platform": platform.platform(), "python": sys.version.split()[0]}
    env.update({name: probe_tool(name, args) for name, args in PROBES})
    return env


def _main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-step")
    for opt in ("file", "name", "status", "command", "detail"):
        add.add_argument(f"--{opt}", required=True)
    ren = sub.add_parser("render")
    ren.add_argument("--steps", required=True)
    ren.add_argument("--junit")
    ren.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "add-step":
        with open(args.file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(StepResult(args.name, args.command, args.status, args.detail))) + "\n")
        return 0
    steps = [StepResult(**json.loads(line)) for line in Path(args.steps).read_text(encoding="utf-8").splitlines() if line.strip()]
    junit = parse_junit(Path(args.junit).read_text(encoding="utf-8")) if args.junit and Path(args.junit).exists() else None
    blocked = [s.name for s in steps if s.status == "BLOCKED"]
    limits = [f"Blocked steps: {', '.join(blocked)} (environment, not code)."] if blocked else []
    text = render_record(date=datetime.now(timezone.utc).strftime("%Y-%m-%d"), environment=probe_environment(), steps=steps, junit=junit, limitations=limits)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
