"""Shared retry/backoff for provider adapters (architecture doc §36/§37).
One place for timeout/retry policy instead of each adapter reinventing it —
but no framework: this is a thin wrapper around tenacity + httpx.
"""
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        # Retry on rate limiting and server errors. Never retry 4xx auth/client
        # errors (401/403/404/etc) — retrying a bad key forever just burns quota.
        return status == 429 or status >= 500
    return False


def _wait_for_retry_after(retry_state):
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, httpx.HTTPStatusError):
        retry_after = exc.response.headers.get("retry-after")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return wait_exponential(multiplier=0.5, min=0.5, max=8)(retry_state)


def request_with_retry_config(max_attempts: int = 3):
    """Returns a tenacity @retry decorator with the shared policy. A factory
    (not a bare decorator) so tests can pass max_attempts=1 or 2 without
    waiting through real backoff.
    """
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_attempts),
        retry=retry_if_exception(_is_retryable),
        wait=_wait_for_retry_after,
    )
