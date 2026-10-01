"""Unit tests for Market & Valuation API Endpoints (Phase 4.1R).
Tests the FastAPI HTTP routes using httpx AsyncClient with session mocks.
"""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
import httpx
import pytest

from app.db.session import get_session
from app.main import app
from app.market.taxonomy import TransferFeeStatus


@pytest.fixture
def mock_session():
    mock_s = AsyncMock()
    return mock_s


@pytest.mark.asyncio
async def test_get_market_coverage_endpoint(mock_session):
    """GET /api/v1/market/coverage returns coverage metrics and readiness status."""
    # Mock get_temporal_transfers query inside compute_market_coverage_audit
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/market/coverage")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_transfers" in data
            assert "fee_coverage_pct" in data
            assert data["readiness_status"] == "INSUFFICIENT_TRANSFER_DATA"
            assert len(data["limitations"]) > 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_market_benchmarks_insufficient(mock_session):
    """GET /api/v1/market/benchmarks returns INSUFFICIENT_DATA when sample < 3."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/market/benchmarks?position_group=MID")
            assert resp.status_code == 200
            data = resp.json()
            assert data["position_group"] == "MID"
            assert data["data_status"] == "INSUFFICIENT_DATA"
            assert data["median_fee_eur"] is None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_market_transfers_empty(mock_session):
    """GET /api/v1/market/transfers returns empty list when no transfers match."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/market/transfers")
            assert resp.status_code == 200
            assert resp.json() == []
    finally:
        app.dependency_overrides.clear()
