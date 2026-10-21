import httpx
import pytest

from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderAuthorizationError,
    ProviderBadRequestError,
    ProviderNetworkError,
    ProviderPlanLimitError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderUnavailableError,
    classify_http_status_error,
    classify_transport_error,
)
from app.providers.api_football import ApiFootballProvider


def _status_error(status: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test")
    response = httpx.Response(status, request=request, headers=headers or {})
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_api_football_page_limit_is_classified_as_a_plan_limit():
    provider = ApiFootballProvider(client=httpx.AsyncClient())
    response = httpx.Response(
        200,
        json={
            "errors": {
                "plan": (
                    "Free plans are limited to a maximum value of 3 for the "
                    "Page parameter"
                )
            }
        },
    )
    with pytest.raises(ProviderPlanLimitError) as exc_info:
        provider._raise_if_envelope_has_errors(response)
    assert exc_info.value.page_max == 3


@pytest.mark.parametrize(
    "status,expected_type",
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthorizationError),
        (429, ProviderRateLimitError),
        (400, ProviderBadRequestError),
        (422, ProviderBadRequestError),
        (500, ProviderServerError),
        (503, ProviderServerError),
    ],
)
def test_classifies_ordinary_status_codes(status, expected_type):
    result = classify_http_status_error(_status_error(status))
    assert isinstance(result, expected_type)


def test_403_with_sandbox_deny_reason_is_unavailable_not_authorization():
    result = classify_http_status_error(_status_error(403, headers={"x-deny-reason": "host_not_allowed"}))
    assert isinstance(result, ProviderUnavailableError)
    assert not isinstance(result, ProviderAuthorizationError)


def test_transport_error_becomes_network_error():
    result = classify_transport_error(httpx.ConnectError("dns failed"))
    assert isinstance(result, ProviderNetworkError)
    assert "ConnectError" in str(result)
