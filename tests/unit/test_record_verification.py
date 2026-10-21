"""Stage 1 verification recorder: a step is PASSED only if it ran and exited 0; blocked work is never reported as done."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).resolve().parents[2] / "tools" / "record_verification.py"
_spec = importlib.util.spec_from_file_location("record_verification", _PATH)
rv = importlib.util.module_from_spec(_spec)
sys.modules["record_verification"] = rv  # dataclasses resolve string annotations through sys.modules
_spec.loader.exec_module(rv)

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="1" skipped="1" tests="5" time="2.5">
<testcase classname="tests.unit.test_a" name="test_ok" time="0.01"/>
<testcase classname="tests.unit.test_a" name="test_bad" time="0.01"><failure message="assert 1 == 2">trace</failure></testcase>
<testcase classname="tests.unit.test_b" name="test_boom" time="0.01"><error message="fixture failed">trace</error></testcase>
<testcase classname="tests.unit.test_b" name="test_skipped" time="0.00"><skipped type="pytest.skip" message="requires data/bronze"/></testcase>
<testcase classname="tests.unit.test_c" name="test_fine" time="0.01"/>
</testsuite></testsuites>"""
CLEAN = '<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="0" tests="2" time="1"><testcase classname="t" name="a"/><testcase classname="t" name="b"/></testsuite></testsuites>'


def _steps(*specs):
    return [rv.StepResult(name=n, command=c, status=s, detail=d) for n, c, s, d in specs]


def test_parse_junit_counts_failures_errors_and_skips_by_name():
    j = rv.parse_junit(JUNIT)
    assert (j.tests, j.failures, j.errors, j.skipped, j.passed) == (5, 1, 1, 1, 2)
    assert j.failed_tests == ["tests.unit.test_a::test_bad", "tests.unit.test_b::test_boom"]
    assert j.skipped_tests == ["tests.unit.test_b::test_skipped (requires data/bronze)"]


@pytest.mark.parametrize("text", ["", "<html/>", "not xml at all"])
def test_parse_junit_rejects_anything_that_is_not_a_junit_report(text):
    with pytest.raises(ValueError):
        rv.parse_junit(text)


def test_probe_tool_reports_not_found_instead_of_guessing():
    assert rv.probe_tool("pytest", which=lambda _: None) == rv.NOT_FOUND


def test_probe_tool_returns_the_first_line_of_the_version_output():
    runner = lambda cmd, **kw: SimpleNamespace(stdout="pytest 8.2.0\nplugins: x", stderr="")
    assert rv.probe_tool("pytest", which=lambda _: "/usr/bin/pytest", runner=runner) == "pytest 8.2.0"


def test_probe_tool_marks_an_unreadable_version_rather_than_inventing_one():
    def runner(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 20)

    assert rv.probe_tool("x", which=lambda _: "/bin/x", runner=runner).startswith("UNREADABLE")


def test_a_blocked_step_carries_its_command_and_error_and_the_run_is_not_verified():
    steps = _steps(("install", "pip install -r requirements-dev.txt", "BLOCKED", "no network: Name or service not known"))
    text = rv.render_record(date="2026-10-11", environment={"python": "3.12.3", "pytest": rv.NOT_FOUND}, steps=steps, junit=None, limitations=[])
    assert "pip install -r requirements-dev.txt" in text and "Name or service not known" in text
    assert "Overall: NOT VERIFIED" in text and "Overall: VERIFIED" not in text
    assert "pytest: NOT_FOUND" in text


@pytest.mark.parametrize("status", ["BLOCKED", "FAILED"])
def test_blocked_or_failed_steps_must_say_why(status):
    with pytest.raises(ValueError):
        rv.render_record(date="d", environment={}, steps=_steps(("s", "cmd", status, "")), junit=None, limitations=[])


def test_verified_requires_every_step_passed_and_a_clean_nonempty_test_run():
    ok = _steps(("install", "pip install", "PASSED", ""), ("pytest", "pytest -v", "PASSED", ""))
    assert "Overall: VERIFIED" in rv.render_record(date="d", environment={}, steps=ok, junit=rv.parse_junit(CLEAN), limitations=[])
    for junit in (None, rv.parse_junit(JUNIT), rv.parse_junit('<testsuites><testsuite tests="0" failures="0" errors="0" skipped="0"/></testsuites>')):
        text = rv.render_record(date="d", environment={}, steps=ok, junit=junit, limitations=[])
        assert "Overall: NOT VERIFIED" in text, "no test evidence, failures, or zero collected tests must never read as verified"


def test_failed_test_names_are_listed_in_the_record():
    steps = _steps(("pytest", "pytest -v", "FAILED", "exit 1"))
    text = rv.render_record(date="d", environment={}, steps=steps, junit=rv.parse_junit(JUNIT), limitations=[])
    assert "tests.unit.test_a::test_bad" in text and "passed=2 failed=1 errors=1 skipped=1" in text
