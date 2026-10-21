"""Paginated ingestion contract tests using a deterministic fake provider.

No live network calls: these tests prove the page-following state machine,
Bronze snapshot per page, record counts, resumability and partial reporting.
"""
import json
from datetime import datetime, timezone

import pytest

from app.db.models.provenance import IngestionStatus
from app.ingestion.service import IngestionService
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.providers.base import RawResponse
from app.providers.errors import ProviderPlanLimitError
from app.providers.registry import ProviderRegistry


class FakePagedProvider:
    name = "fake-paged"

    def __init__(self, total_pages=3, page_size=20, final_page_size=5):
        self.total_pages = total_pages
        self.page_size = page_size
        self.final_page_size = final_page_size
        self.calls = []
        self.fail_on_page = None
        self.empty_pages = set()
        self.plan_limit_page = None

    async def fetch(self, resource, **params):
        page = int(params["page"])
        self.calls.append(page)
        if self.plan_limit_page == page:
            raise ProviderPlanLimitError(
                "API-Football returned errors in a 200 response: {'plan': "
                "'Free plans are limited to a maximum value of 3 for the Page parameter'}",
                page_max=3,
            )
        if self.fail_on_page == page:
            raise RuntimeError("simulated provider failure")
        if page > self.total_pages or page in self.empty_pages:
            count = 0
        elif page == self.total_pages:
            count = self.final_page_size
        else:
            count = self.page_size
        body = {
            "get": resource,
            "results": count,
            "paging": {"current": page, "total": self.total_pages},
            "response": [{"id": i} for i in range(count)],
        }
        return RawResponse(
            content=json.dumps(body).encode(),
            content_type="application/json",
            source_url=f"fake://{resource}?page={page}",
            retrieved_at=datetime.now(timezone.utc),
            status_code=200,
        )

    async def close(self):
        return None


class UnknownTotalProvider(FakePagedProvider):
    async def fetch(self, resource, **params):
        page = int(params["page"])
        self.calls.append(page)
        body = {
            "get": resource,
            "results": 3,
            "response": [{"id": i} for i in range(3)],
        }
        return RawResponse(
            content=json.dumps(body).encode(),
            content_type="application/json",
            source_url=f"fake://{resource}?page={page}",
            retrieved_at=datetime.now(timezone.utc),
            status_code=200,
        )


def _service(session, tmp_path, provider):
    registry = ProviderRegistry()
    registry.register("fake-paged", lambda: provider)
    return IngestionService(
        session=session,
        provider_registry=registry,
        snapshot_store=LocalFilesystemSnapshotStore(tmp_path),
        capability_registry=None,
    )


@pytest.mark.asyncio
async def test_follows_provider_paging_until_declared_last_page(
    integration_session, tmp_path
):
    provider = FakePagedProvider()
    service = _service(integration_session, tmp_path, provider)

    result = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0
    )

    assert provider.calls == [1, 2, 3]
    assert result.status == "COMPLETE"
    assert result.stop_reason == "PROVIDER_REPORTED_LAST_PAGE"
    assert result.total_pages == 3
    assert result.pages_requested == 3
    assert result.pages_succeeded == 3
    assert result.records_fetched == 45
    assert [run.record_count for run in result.runs] == [20, 20, 5]
    assert all(run.status == IngestionStatus.SUCCESS for run in result.runs)


@pytest.mark.asyncio
async def test_resume_does_not_refetch_completed_pages(integration_session, tmp_path):
    provider = FakePagedProvider()
    service = _service(integration_session, tmp_path, provider)
    first = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0
    )
    assert first.status == "COMPLETE"

    second = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0, resume=True
    )

    assert provider.calls == [1, 2, 3]
    assert second.status == "COMPLETE"
    assert second.stop_reason == "ALREADY_COMPLETE"
    assert second.pages_requested == 0


@pytest.mark.asyncio
async def test_max_pages_stops_with_partial_status(integration_session, tmp_path):
    provider = FakePagedProvider()
    service = _service(integration_session, tmp_path, provider)

    result = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0, max_pages=2
    )

    assert provider.calls == [1, 2]
    assert result.status == "PARTIAL"
    assert result.stop_reason == "MAX_PAGES_REACHED"
    assert result.last_page == 2
    assert result.total_pages == 3


@pytest.mark.asyncio
async def test_provider_failure_preserves_completed_pages(integration_session, tmp_path):
    provider = FakePagedProvider()
    provider.fail_on_page = 2
    service = _service(integration_session, tmp_path, provider)

    result = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0
    )

    assert provider.calls == [1, 2]
    assert result.status == "PARTIAL"
    assert result.stop_reason == "PROVIDER_FAILURE"
    assert result.pages_succeeded == 1
    assert result.records_fetched == 20
    assert result.errors and "simulated provider failure" in result.errors[0]
    assert result.runs[-1].status == IngestionStatus.FAILED


@pytest.mark.asyncio
async def test_provider_plan_limit_is_reported_not_bypassed(integration_session, tmp_path):
    provider = FakePagedProvider()
    provider.plan_limit_page = 2
    service = _service(integration_session, tmp_path, provider)

    result = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0
    )

    assert provider.calls == [1, 2]
    assert result.stop_reason == "PROVIDER_PLAN_LIMIT"
    assert result.status == "BLOCKED_BY_PLAN"
    assert result.plan_page_max == 3
    assert result.pages_succeeded == 1
    assert result.records_fetched == 20


@pytest.mark.asyncio
async def test_resume_plan_limit_preserves_prior_pages(integration_session, tmp_path):
    provider = FakePagedProvider()
    service = _service(integration_session, tmp_path, provider)
    first = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0, max_pages=1
    )
    assert first.status == "PARTIAL"

    provider.plan_limit_page = 2
    second = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0, resume=True
    )

    assert provider.calls == [1, 2]
    assert second.resumed_from_page == 1
    assert second.status == "BLOCKED_BY_PLAN"
    assert second.stop_reason == "PROVIDER_PLAN_LIMIT"
    assert second.plan_page_max == 3


@pytest.mark.asyncio
async def test_missing_paging_total_is_not_treated_as_complete(
    integration_session, tmp_path
):
    provider = UnknownTotalProvider()
    service = _service(integration_session, tmp_path, provider)

    result = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0
    )

    assert provider.calls == [1]
    assert result.status == "UNKNOWN"
    assert result.stop_reason == "PAGING_TOTAL_UNKNOWN"
    assert result.total_pages is None


@pytest.mark.asyncio
async def test_empty_final_page_stops_safely(integration_session, tmp_path):
    provider = FakePagedProvider(total_pages=3, page_size=20, final_page_size=20)
    # Page 2 is empty while the provider still claims 3 pages: stop, do not
    # invent records for page 3.
    provider.empty_pages = {2}
    service = _service(integration_session, tmp_path, provider)

    result = await service.run_paginated(
        "fake-paged", "players", request_interval_seconds=0, start_page=1
    )

    assert provider.calls == [1, 2]
    assert result.stop_reason == "EMPTY_PAGE"
    assert result.status == "PARTIAL"
    assert result.records_fetched == 20
    assert result.total_pages == 3
