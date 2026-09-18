import httpx
import pytest

from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderAuthorizationError,
    ProviderBadRequestError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderUnavailableError,
    classify_http_status_error,
    classify_transport_error,
)


def _status_error(status: int, headers: dict | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test")
    response = httpx.Response(status, request=request, headers=headers or {})
    return httpx.HTTPStatusError("boom", request=request, response=response)


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
