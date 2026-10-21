"""Match-prediction registry: status and metrics come from verifiable evidence, never from typed constants (audit R18).

The previous registry hand-typed "MODEL_VALIDATED", log-loss 0.9418, ECE 0.0385, 1,520/388/400 match counts, "2026-08..2026-09"
periods and temporal/leakage flags that defaulted to True, for a hand-weighted formula that has no fitted artifact.
"""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "apps" / "api" / "app"


def _load():
    try:
        from app.prediction.registry import ModelMetadata, PredictionModelRegistry
    except ImportError:  # web/DB stack absent (audit sandbox): import the submodules without the package __init__
        pkg = types.ModuleType("app.prediction")
        pkg.__path__ = [str(APP / "prediction")]
        sys.modules["app.prediction"] = pkg
        from app.prediction.registry import ModelMetadata, PredictionModelRegistry
    return ModelMetadata, PredictionModelRegistry


ModelMetadata, PredictionModelRegistry = _load()


def _validated(evidence_ref=None, sha=None, **over):
    kw = dict(
        model_id="m", model_version="1", feature_version="f", dataset_version="d", algorithm="a",
        training_matches_count=10, validation_matches_count=5, test_matches_count=5,
        training_period="p1", validation_period="p2", test_period="p3",
        metrics={"log_loss": 0.9}, status="MODEL_VALIDATED", temporal_validation_passed=True, leakage_tests_passed=True,
        evidence_ref=evidence_ref, evidence_sha256=sha,
    )
    kw.update(over)
    return ModelMetadata(**kw)


def test_default_records_carry_no_typed_validation_evidence():
    registry = PredictionModelRegistry()
    models = registry.list_models()
    assert {m.model_id for m in models} >= {"baseline_class_frequency_v1", "baseline_elo_deterministic_v1", "calibrated_multinomial_logit_v1"}
    for m in models:
        assert m.status != "MODEL_VALIDATED", f"{m.model_id} claims validation without evidence"
        assert m.metrics == {} and m.calibration_method == "NONE"
        assert m.temporal_validation_passed is None and m.leakage_tests_passed is None
        assert (m.training_matches_count, m.validation_matches_count, m.test_matches_count) == (None, None, None)
        assert (m.training_period, m.validation_period, m.test_period, m.dataset_version) == (None, None, None, None)
    assert registry.get_active_model().status == "MODEL_UNVALIDATED"


def test_status_response_reports_missing_evidence_as_none_not_zero():
    resp = PredictionModelRegistry().get_status_response()
    assert resp.status == "MODEL_UNVALIDATED"
    assert (resp.log_loss, resp.brier_score, resp.accuracy, resp.macro_f1, resp.expected_calibration_error) == (None,) * 5
    assert (resp.training_matches_count, resp.validation_matches_count) == (None, None)
    assert resp.temporal_validation_passed is None and resp.leakage_tests_passed is None


def test_validated_status_requires_verifiable_evidence(tmp_path):
    registry = PredictionModelRegistry(evidence_root=tmp_path)
    report = tmp_path / "report.json"
    report.write_text('{"log_loss": 0.9}')
    good = hashlib.sha256(report.read_bytes()).hexdigest()

    for bad in (
        _validated(),                                                          # no evidence at all
        _validated("report.json", "0" * 64),                                   # hash does not match the file
        _validated("missing.json", "a" * 64),                                  # file absent
        _validated("../outside.json", "a" * 64),                               # escapes the evidence root
        _validated("report.json", good, temporal_validation_passed=None),      # validation not established
        _validated("report.json", good, leakage_tests_passed=False),
        _validated("report.json", good, metrics={}),                           # nothing measured
    ):
        with pytest.raises(ValueError):
            registry.register(bad)

    registry.register(_validated("report.json", good))
    assert registry.verify_evidence("m") is True
    report.write_text('{"log_loss": 0.1}')  # evidence rewritten after registration
    assert registry.verify_evidence("m") is False


def test_unvalidated_candidates_register_without_evidence():
    registry = PredictionModelRegistry()
    registry.register(_validated(status="MODEL_CANDIDATE", metrics={}, temporal_validation_passed=None, leakage_tests_passed=None))
    assert registry.get_model("m").status == "MODEL_CANDIDATE"


def test_prediction_service_calls_probabilities_calibrated_only_for_validated_models():
    source = (APP / "prediction" / "service.py").read_text(encoding="utf-8")
    assert 'status="CALIBRATED",' not in source, "calibration status must depend on the registry's validated status"
