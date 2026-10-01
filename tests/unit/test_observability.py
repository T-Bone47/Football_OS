"""Unit tests for Phase 8 Observability, Governance & System Health."""
from __future__ import annotations

import json
import logging
import uuid
import pytest

from app.observability.correlation import (
    current_decision_id,
    current_request_id,
    get_decision_id,
    get_request_id,
)
from app.observability.data_quality import (
    DataQualityMonitor,
    DataQualityState,
    enforce_decision_confidence_invariants,
)
from app.observability.logging import (
    StructuredJsonFormatter,
    redact_sensitive_str,
)
from app.observability.model_governance import (
    ModelGovernanceRecord,
    ModelGovernanceRegistry,
    ModelReleaseBlockedError,
    UnknownModelVersionError,
    _compute_spec_hash,
)
from app.observability.model_monitoring import (
    MatchPredictionMonitor,
    RiskMonitor,
    TacticalFitMonitor,
    ValuationMonitor,
    compute_distribution_metrics,
    compute_psi,
)
from app.observability.system_health import (
    check_application_health,
    check_data_health,
    check_model_health,
    check_readiness,
)


class TestCorrelationAndLogging:
    def test_context_correlation(self):
        token_req = current_request_id.set("req-test-123")
        token_dec = current_decision_id.set("dec-test-456")
        try:
            assert get_request_id() == "req-test-123"
            assert get_decision_id() == "dec-test-456"
        finally:
            current_request_id.reset(token_req)
            current_decision_id.reset(token_dec)

        # Default fallback
        assert get_request_id() == "system_internal"
        assert get_decision_id() == ""

    def test_sensitive_information_redaction(self):
        msg = "Connecting to api with api_key=secret_12345 and password='super_secret_pwd'"
        redacted = redact_sensitive_str(msg)
        assert "secret_12345" not in redacted
        assert "super_secret_pwd" not in redacted
        assert "[REDACTED]" in redacted

    def test_structured_json_formatter(self):
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="User evaluated candidate with token: secret_token_xyz",
            args=(),
            exc_info=None,
        )
        record.model_version = "v1.0"
        record.calculation_version = "v1.0.0"

        formatted = formatter.format(record)
        data = json.loads(formatted)

        assert data["level"] == "INFO"
        assert data["logger"] == "test_logger"
        assert "secret_token_xyz" not in data["message"]
        assert data["model_version"] == "v1.0"
        assert data["calculation_version"] == "v1.0.0"
        assert "timestamp" in data
        assert "request_id" in data


class TestModelGovernance:
    def test_authoritative_models_bootstrapped(self):
        registry = ModelGovernanceRegistry()
        models = registry.list_all_models()
        assert len(models) >= 5

        # Check required analytical models exist
        val_model = registry.get_model("valuation_model", "GBR_ValuationEngine_v1.0")
        assert val_model.status == "MODEL_VALIDATED"
        assert val_model.feature_set == "fset_v2"
        assert "mae" in val_model.metrics

        match_model = registry.get_model("match_prediction_engine", "BivariatePoisson_v1")
        assert match_model.status == "MODEL_VALIDATED"

        tactical_model = registry.get_model("tactical_fit_engine", "TacticalFitCalculator_v1.0")
        assert tactical_model.status == "MODEL_VALIDATED"

    def test_unknown_model_version_rejected(self):
        registry = ModelGovernanceRegistry()
        with pytest.raises(UnknownModelVersionError) as exc:
            registry.verify_inference_eligibility("valuation_model", "NON_EXISTENT_MODEL_v99")
        assert "Silent use of unknown model versions is prohibited" in str(exc.value)

    def test_blocked_model_rejected_for_inference(self):
        registry = ModelGovernanceRegistry()
        blocked_rec = ModelGovernanceRecord(
            name="candidate_model",
            version="Experimental_v0.1",
            feature_set="experimental_features",
            training_cutoff="2026-09-01",
            validation_period="2026-09-01 to 2026-09-15",
            metrics={"mae": 999999.0},
            calibration={},
            artifact_hash=_compute_spec_hash("Experimental_v0.1"),
            status="MODEL_RELEASE_BLOCKED",
            provenance="experimental_pipeline",
            description="Failed model candidate",
            created_at="2026-09-20T00:00:00Z",
        )
        registry.register(blocked_rec)

        with pytest.raises(ModelReleaseBlockedError) as exc:
            registry.verify_inference_eligibility("candidate_model", "Experimental_v0.1")
        assert "blocked from production inference" in str(exc.value)


class TestDataQualityMonitoring:
    def test_audit_tabular_data_complete(self):
        records = [
            {"player_id": "p1", "minutes": 900, "age": 24, "provenance": "canonical.players"},
            {"player_id": "p2", "minutes": 1200, "age": 28, "provenance": "canonical.players"},
        ]
        report = DataQualityMonitor.audit_tabular_data(
            records=records,
            dataset_name="test_players",
            required_fields=["player_id", "minutes", "age"],
            identity_fields=["player_id"],
            validation_rules={"minutes": lambda x: x >= 0, "age": lambda x: 14 <= x <= 45},
        )
        assert report.quality_state == DataQualityState.DATA_COMPLETE
        assert report.overall_missingness_rate == 0.0
        assert report.duplicate_entities_count == 0
        assert report.provenance_gaps_count == 0

    def test_audit_tabular_data_with_missingness_and_duplicates(self):
        records = [
            {"player_id": "p1", "minutes": None, "age": 24, "provenance": ""},
            {"player_id": "p1", "minutes": 900, "age": 24, "provenance": None},  # Duplicate ID, prov gap
            {"player_id": "p2", "minutes": None, "age": None, "provenance": "prov"},
        ]
        report = DataQualityMonitor.audit_tabular_data(
            records=records,
            dataset_name="test_players_dirty",
            required_fields=["player_id", "minutes", "age"],
            identity_fields=["player_id"],
        )
        assert report.duplicate_entities_count == 1
        assert report.provenance_gaps_count == 2
        assert report.overall_missingness_rate > 0.15

    def test_enforce_decision_confidence_invariants(self):
        # High confidence cannot stand if evidence is partial or insufficient
        tier, score = enforce_decision_confidence_invariants(
            quality_state=DataQualityState.PARTIAL_EVIDENCE,
            confidence_tier="HIGH",
            decision_confidence=0.92,
        )
        assert tier == "MODERATE"
        assert score <= 0.65

        tier2, score2 = enforce_decision_confidence_invariants(
            quality_state=DataQualityState.INSUFFICIENT_DATA,
            confidence_tier="HIGH",
            decision_confidence=0.95,
        )
        assert tier2 == "LOW"
        assert score2 <= 0.65


class TestModelMonitoringPrimitives:
    def test_distribution_metrics(self):
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        metrics = compute_distribution_metrics(vals)
        assert metrics.count == 5
        assert metrics.mean == 30.0
        assert metrics.median == 30.0
        assert metrics.p5 < metrics.p95

    def test_psi_calculation(self):
        ref = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        # Identical distribution -> PSI should be ~0.0
        psi = compute_psi(ref, ref)
        assert psi == 0.0

        # Divergent distribution
        curr = [10.0, 10.0, 10.0, 10.0, 10.0, 9.0, 9.0, 8.0, 8.0, 7.0]
        psi_drift = compute_psi(ref, curr)
        assert psi_drift > 0.0

    def test_valuation_monitor(self):
        preds = [15e6] * 35
        actuals = [14e6] * 35
        audit = ValuationMonitor.audit_predictions(preds, actuals=actuals, baseline_predictions=preds)
        assert audit["sufficient_sample"] is True
        assert "error_metrics" in audit
        assert audit["error_metrics"]["mae"] == 1_000_000.0
        assert audit["drift"]["status"] == "STABLE"

    def test_match_prediction_monitor(self):
        # 3 matches, perfect predictions
        preds = [(0.9, 0.05, 0.05), (0.05, 0.9, 0.05), (0.05, 0.05, 0.9)]
        actuals = [0, 1, 2]
        metrics = MatchPredictionMonitor.compute_brier_and_log_loss(preds, actuals)
        assert metrics["brier_score"] < 0.10
        assert metrics["log_loss"] < 0.20
        assert "ece" in metrics


@pytest.mark.asyncio
class TestSystemHealthEndpoints:
    async def test_application_health(self):
        res = await check_application_health()
        assert res["status"] == "HEALTHY"
        assert "pid" in res
        assert "memory_rss_mb" in res
        assert "service" in res

    async def test_readiness_no_session(self):
        res = await check_readiness(None)
        assert res["status"] == "READY"
        assert res["database"]["status"] == "UNKNOWN"

    async def test_model_health(self):
        res = await check_model_health()
        assert res["status"] == "HEALTHY"
        assert res["total_models_registered"] >= 5
        assert "valuation" in res["active_engines"]
        assert "match_prediction" in res["active_engines"]

    async def test_data_health(self):
        res = await check_data_health(None)
        assert res["status"] == "HEALTHY"
        assert res["zero_fabrication_policy"] == "ENFORCED"
