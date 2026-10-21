"""Phase 16 serving must serve a real verified artifact or refuse - never emit a formula (R8).

Uses an injected fake registry/bundle so the control flow is exercised without the ML stack.
Regression for: seeded fictional models + `predicted_value = base_metric * 1.05`.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from app.market.ml.artifact_integrity import ArtifactIntegrityError
from app.phase16.model_serving import ModelServingEngine, ModelUnavailableError

NAMES = ["age_at_transfer", "observed_minutes_as_of", "x"]
VALID_ENTRY = {"model_id": "m1", "status": "MODEL_VALIDATED", "supported_competitions": ["EPL"], "artifact_sha256": "ab" * 32}


class FakeBundle:
    feature_names = NAMES
    metadata = SimpleNamespace(model_id="m1", model_version="V1", feature_set_version="1.0.0", dataset_version="DS1")

    def __init__(self, can_predict=True, value=12_345_678.0):
        self.can_predict, self.value, self.calls = can_predict, value, []

    def predict_player(self, **kw):
        self.calls.append(kw)
        gate = SimpleNamespace(can_predict=self.can_predict, reasons=["Missing feature rate 73.3% exceeds threshold (25.0%)."])
        status = SimpleNamespace(value="VALUATION_AVAILABLE" if self.can_predict else "INSUFFICIENT_DATA")
        return SimpleNamespace(gate_decision=gate, data_status=status, estimated_value_eur=self.value if self.can_predict else 0.0,
                               lower_bound_eur=self.value * 0.8, upper_bound_eur=self.value * 1.2)


class FakeRegistry:
    def __init__(self, entry=None, bundle=None, load_error=None, manifest=None):
        self.entry, self.bundle, self.load_error = entry, bundle, load_error
        self.manifest = manifest if manifest is not None else {"active_model_id": None, "models": {}}
        self.base_dir = "/nonexistent"

    def _load_manifest(self): return self.manifest

    def active_manifest_entry(self):
        if self.entry is None:
            raise ArtifactIntegrityError("NO_ACTIVE_MODEL", "none")
        return self.entry

    def load_active_or_raise(self):
        if self.load_error:
            raise ArtifactIntegrityError(self.load_error, "boom")
        return self.bundle

    def set_active_model(self, model_id):
        raise ArtifactIntegrityError("MODEL_NOT_VALIDATED", "status is MODEL_RELEASE_BLOCKED")


GOOD_FEATURES = {"age_at_transfer": 24.0, "observed_minutes_as_of": 2000.0, "x": 1.0}


def _refusal(engine, **kw):
    args = dict(domain="valuation", features=GOOD_FEATURES, competition="EPL", position="MID")
    args.update(kw)
    with pytest.raises(ModelUnavailableError) as exc:
        engine.serve_inference(**args)
    return exc.value


def test_no_models_are_seeded():
    assert ModelServingEngine(registry=FakeRegistry()).list_models() == []


def test_unknown_domain_refused():
    err = _refusal(ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, FakeBundle())), domain="match_prediction")
    assert (err.code, err.http_status) == ("NO_MODEL_FOR_DOMAIN", 404)


def test_no_active_model_refused():
    err = _refusal(ModelServingEngine(registry=FakeRegistry(entry=None)))
    assert (err.code, err.http_status) == ("NO_ACTIVE_MODEL", 503)


def test_unvalidated_model_is_refused_with_its_blocking_reasons():
    entry = {**VALID_ENTRY, "status": "MODEL_RELEASE_BLOCKED", "blocking_reasons": ["test R2 is -0.0904"]}
    err = _refusal(ModelServingEngine(registry=FakeRegistry(entry, FakeBundle())))
    assert (err.code, err.http_status) == ("MODEL_NOT_VALIDATED", 409) and "-0.0904" in err.detail


@pytest.mark.parametrize("supported,competition", [(None, "EPL"), ([], "EPL"), (["EPL"], "Eredivisie")])
def test_undeclared_or_unsupported_competition_is_refused_not_flagged(supported, competition):
    entry = {**VALID_ENTRY, "supported_competitions": supported}
    err = _refusal(ModelServingEngine(registry=FakeRegistry(entry, FakeBundle())), competition=competition)
    assert (err.code, err.http_status) == ("COMPETITION_NOT_SUPPORTED", 422)


def test_tampered_artifact_is_refused():
    err = _refusal(ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, load_error="ARTIFACT_HASH_MISMATCH")))
    assert (err.code, err.http_status) == ("ARTIFACT_HASH_MISMATCH", 503)


def test_old_toy_input_contract_cannot_produce_a_number():
    err = _refusal(ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, FakeBundle())), features={"base_metric": 60.0})
    assert (err.code, err.http_status) == ("FEATURE_SCHEMA_MISMATCH", 422)


def test_insufficient_data_is_a_refusal_not_a_zero_prediction():
    err = _refusal(ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, FakeBundle(can_predict=False))))
    assert (err.code, err.http_status) == ("INSUFFICIENT_DATA", 422) and "Missing feature rate" in err.detail


def test_served_value_comes_from_the_model_and_carries_provenance():
    bundle = FakeBundle(value=12_345_678.0)
    engine = ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, bundle))
    resp = engine.serve_inference("valuation", {**GOOD_FEATURES, "x": 999.0}, "EPL", "MID")
    assert resp.predicted_value == 12_345_678.0 and resp.confidence_interval[0] < resp.predicted_value < resp.confidence_interval[1]
    assert resp.artifact_sha256 == "ab" * 32 and resp.model_release_status == "MODEL_VALIDATED" and resp.missing_feature_count == 0
    assert len(resp.input_digest) == 64


def test_missing_values_are_counted_and_passed_to_the_gate_not_zero_filled():
    bundle = FakeBundle()
    engine = ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, bundle))
    resp = engine.serve_inference("valuation", {**GOOD_FEATURES, "x": None}, "EPL", "MID")
    call = bundle.calls[0]
    assert call["null_count"] == 1 and math.isnan(call["features"][2]) and resp.missing_feature_count == 1


def test_telemetry_is_measured_and_labelled_process_local():
    engine = ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, FakeBundle()))
    assert engine.telemetry.snapshot()["latency_ms_p50"] is None and engine.telemetry.snapshot()["failure_rate"] is None
    engine.serve_inference("valuation", GOOD_FEATURES, "EPL", "MID")
    _refusal(engine, domain="match_prediction")
    snap = engine.telemetry.snapshot()
    assert (snap["served"], snap["refused"], snap["failure_rate"]) == (1, 1, 0.5)
    assert snap["refusals_by_reason"] == {"NO_MODEL_FOR_DOMAIN": 1} and snap["scope"] == "PROCESS_LOCAL_SINCE_START"


def test_promotion_of_unvalidated_model_is_refused():
    engine = ModelServingEngine(registry=FakeRegistry(VALID_ENTRY, FakeBundle()))
    with pytest.raises(ModelUnavailableError) as exc:
        engine.promote("valuation", "m_blocked")
    assert (exc.value.code, exc.value.http_status) == ("MODEL_NOT_VALIDATED", 409)
