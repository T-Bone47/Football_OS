"""Phase 10 ingestion reports only what a real run did (R4). Replaces the tests that asserted a fabricated cycle."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.phase10 import operational_ingestion as view
from app.phase10.operational_ingestion import cycle_view, sha256_from_location, stage_results, validate_provider_params

APP = Path(__file__).resolve().parents[2] / "apps" / "api" / "app"
SNAP_VALID = {"sha256": "ab" * 32, "size_bytes": 10, "validation_status": "VALID", "validation_errors": None}


def _view(run_status="SUCCESS", error=None, snapshot=SNAP_VALID, record_count=None):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return cycle_view(run_id="r1", provider="statsbomb", resource="matches", run_status=run_status, error=error,
                      started_at=now, finished_at=now, record_count=record_count, snapshot=snapshot)


def test_the_fabricating_pipeline_no_longer_exists():
    tree = ast.parse((APP / "phase10" / "operational_ingestion.py").read_text())
    docstring = ast.get_docstring(tree, clean=False)
    code_tokens = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != docstring}
    code_tokens |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not hasattr(view, "operational_pipeline") and not hasattr(view, "OperationalIngestionPipeline")
    for forbidden in ("Arsenal", "Chelsea", "write_bytes", "write_text", "uuid4", "random", "open"):
        assert not any(forbidden in token for token in code_tokens), f"module must not fabricate or persist data: {forbidden!r}"


def test_trigger_request_cannot_inject_bronze_payload_or_default_a_provider():
    tree = ast.parse((APP / "api" / "routes_phase10.py").read_text())
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "IngestionTriggerRequest")
    fields = {n.target.id: n for n in cls.body if isinstance(n, ast.AnnAssign)}
    assert "payload" not in fields and "dry_run" not in fields
    assert fields["provider"].value is None and fields["resource"].value is None  # required, no default


def test_capability_failure_runs_nothing_downstream():
    stages = _view("FAILED", "capability registry: 'x' does not support resource 'y'", snapshot=None)["stage_results"]
    assert stages["capability_check"] == "FAILED"
    assert {v for k, v in stages.items() if k != "capability_check"} == {"NOT_EXECUTED"}


def test_provider_failure_is_a_failed_fetch_not_a_completed_cycle():
    v = _view("FAILED", "HTTPError: 503", snapshot=None)
    assert v["status"] == "FAILED" and v["stage_results"]["provider_fetch"] == "FAILED"
    assert v["stage_results"]["bronze_snapshot_persisted"] == "NOT_EXECUTED" and v["snapshot"] is None


def test_successful_capture_is_partial_and_downstream_stages_are_not_executed():
    v = _view()
    assert v["status"] == "PARTIAL"  # never SUCCESS: silver/identity/features/model/decision stages did not run
    assert v["stages_completed"] == ["capability_check", "provider_fetch", "bronze_snapshot_persisted", "schema_validation"]
    assert set(view.DOWNSTREAM_STAGES) == set(v["stages_not_executed"])
    assert v["record_count"] is None  # not measured, so not invented


def test_invalid_snapshot_fails_schema_validation_stage():
    v = _view("PARTIAL", "snapshot failed schema validation", snapshot={**SNAP_VALID, "validation_status": "INVALID"})
    assert v["stage_results"]["schema_validation"] == "FAILED" and v["status"] == "PARTIAL"


def test_pending_validation_is_not_reported_as_validated():
    v = _view(snapshot={**SNAP_VALID, "validation_status": "PENDING"})
    assert v["stage_results"]["schema_validation"] == "NOT_EXECUTED"


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING"])
def test_in_flight_runs_have_executed_nothing(status):
    v = _view(status, snapshot=None)
    assert v["status"] == status and set(v["stage_results"].values()) == {"NOT_EXECUTED"}


def test_every_stage_is_reported_exactly_once():
    assert list(stage_results(run_status="SUCCESS", error=None, has_snapshot=True, validation_status="VALID")) == list(view.ALL_STAGES)


@pytest.mark.parametrize("params", [{"match_id": 3788741}, {"competition_id": "43", "season_id": "3"}, {}])
def test_scalar_provider_params_accepted(params):
    assert validate_provider_params(params) == params


@pytest.mark.parametrize("params", [{"match_id": "../../etc/passwd"}, {"a b": 1}, {"x": {"nested": 1}}, {"x": [1]}, {"x": "a/b"}])
def test_unsafe_provider_params_rejected(params):
    with pytest.raises(ValueError):
        validate_provider_params(params)


SHA = "ab" * 32


@pytest.mark.parametrize(
    "location",
    [f"/srv/data/bronze/statsbomb/matches/{SHA}.json", f"s3://bucket/statsbomb/matches/{SHA}.json", f"C:\\data\\bronze\\x\\{SHA}.json"],
)
def test_snapshot_hash_is_read_back_from_the_content_addressed_location(location):
    assert sha256_from_location(location) == SHA


@pytest.mark.parametrize("location", [None, "", "/srv/x/not-a-hash.json", f"/srv/x/{SHA[:-1]}.json"])
def test_unparseable_locations_yield_no_hash_rather_than_a_guess(location):
    assert sha256_from_location(location) is None
