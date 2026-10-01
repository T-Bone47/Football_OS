"""Unit-test scoping for the access gate.

The legacy unit modules listed below call routes through TestClient with no
database, to test engine logic. For those modules only, the gate is replaced
by one that binds a labelled TEST FIXTURE principal. Authentication itself is
tested against real tokens and a real database in tests/integration
(test_phase18_auth.py, test_phase17_*). The Phase 17/18 contract tests in
this directory are NOT in the list: they assert that anonymous calls fail.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import Request

LEGACY_APP_MODULES = {
    "test_decision_api_contracts", "test_market_api", "test_phase10_operations", "test_phase13_decision_simulation",
    "test_phase14_outcome_intelligence", "test_phase15_global_research", "test_phase16_production_platform",
    "test_valuation_ml_engine",
}


@pytest.fixture(autouse=True)
def _legacy_test_principal(request):
    if request.module.__name__.rsplit(".", 1)[-1] not in LEGACY_APP_MODULES:
        yield
        return
    from app.auth_gate import auth_gate
    from app.db.models.operations import OpsUser
    from app.main import app

    principal = OpsUser(id=uuid.uuid4(), organization_id=uuid.uuid4(), email="legacy-unit-tests@test-fixture.invalid",
                        name="TEST FIXTURE principal", role="ADMIN", token_sha256="0" * 64, is_active=True)

    async def _test_gate(req: Request) -> None:
        req.state.principal = principal

    app.dependency_overrides[auth_gate] = _test_gate
    yield
    app.dependency_overrides.pop(auth_gate, None)
