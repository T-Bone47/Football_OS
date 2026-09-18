"""Explicit provider error hierarchy (architecture doc's connectivity-forensics
§16) — every provider failure gets classified, not collapsed into one generic
exception. IngestionService still catches broadly (a provider bug should
never crash the app), but run.error now carries a precise, named reason
instead of a raw httpx traceback string.
"""
from __future__ import annotations

import httpx


class ProviderError(Exception):
    """Base for all provider-layer failures."""


class ProviderNetworkError(ProviderError):
    """DNS, TCP, TLS, timeout, or connection-level failure — the request
    never got a response from anything."""


class ProviderAuthenticationError(ProviderError):
    """401 — the key/token itself is missing or invalid. Never retried."""


class ProviderAuthorizationError(ProviderError):
    """403 with a valid-looking key — IP/domain restriction or plan/scope
    issue, not a missing/wrong key. Never retried."""


class ProviderRateLimitError(ProviderError):
    """429. Retryable, with backoff/Retry-After."""


class ProviderBadRequestError(ProviderError):
    """400/422, or HTTP 200 with a non-empty `errors` envelope field (doc
    §18: HTTP 200 != usable data). Never retried — retrying a malformed
    request doesn't fix it."""


class ProviderServerError(ProviderError):
    """5xx. Retryable."""


class ProviderSchemaError(ProviderError):
    """Response parsed but didn't match the expected envelope/schema."""


class ProviderUnavailableError(ProviderError):
    """Everything reached the provider layer but it's structurally
    unreachable right now for a reason distinct from the above — e.g. this
    sandbox's own egress allowlist rejecting the host before the request
    ever leaves Anthropic's infrastructure. Deliberately distinct from
    ProviderNetworkError: that's "the internet is down between us and them",
    this is "our own environment won't let the request out" — see
    docs/DEVELOPMENT_STATUS.md and ADR-007."""


def classify_http_status_error(exc: httpx.HTTPStatusError) -> ProviderError:
    status = exc.response.status_code
    if status == 401:
        return ProviderAuthenticationError(f"authentication failed (401): {exc}")
    if status == 403:
        if exc.response.headers.get("x-deny-reason") == "host_not_allowed":
            return ProviderUnavailableError(
                f"sandbox egress policy blocked this host before it reached the provider: {exc}"
            )
        return ProviderAuthorizationError(f"authorization failed (403): {exc}")
    if status == 429:
        return ProviderRateLimitError(f"rate limited (429): {exc}")
    if status in (400, 422):
        return ProviderBadRequestError(f"bad request ({status}): {exc}")
    if status >= 500:
        return ProviderServerError(f"provider server error ({status}): {exc}")
    return ProviderError(f"unclassified HTTP error ({status}): {exc}")


def classify_transport_error(exc: httpx.TransportError) -> ProviderNetworkError:
    return ProviderNetworkError(f"{type(exc).__name__}: {exc}")
