import pytest

from app.config import Settings
from app.providers.verify_live_endpoints import ENDPOINTS, classify, run_verification


@pytest.mark.parametrize(
    "status_value,error,expected_outcome",
    [
        ("SUCCESS", None, "SUCCESS"),
        ("FAILED", "ProviderRateLimitError: rate limited (429): boom", "QUOTA FAILURE"),
        ("FAILED", "ProviderAuthorizationError: authorization failed (403): boom", "AUTHORIZATION FAILURE"),
        ("FAILED", "ProviderAuthenticationError: authentication failed (401): boom", "AUTHORIZATION FAILURE"),
        ("FAILED", "ProviderBadRequestError: API-Football returned errors in a 200 response: [...]", "API-LEVEL FAILURE"),
        ("FAILED", "ProviderUnavailableError: sandbox egress policy blocked this host...", "NOT RUN"),
        ("FAILED", "capability registry: 'api-football' does not support resource 'x'", "ENDPOINT/COVERAGE LIMITATION"),
        ("FAILED", "ValueError: something unrelated", "ERROR"),
    ],
)
def test_classify(status_value, error, expected_outcome):
    outcome, _ = classify(status_value, error)
    assert outcome == expected_outcome


async def test_run_verification_without_key_reports_not_run_for_all_four(monkeypatch):
    from app.providers import verify_live_endpoints as mod

    class _NoKeySettings:
        api_football_key = None

    monkeypatch.setattr(mod, "get_settings", lambda: _NoKeySettings())
    results = await run_verification()

    assert [r.endpoint for r in results] == [e for e, _ in ENDPOINTS]
    assert all(r.outcome == "NOT RUN" for r in results)
    assert all(r.capability_marked_verified is False for r in results)


def test_endpoints_cover_exactly_the_four_requested():
    assert [e for e, _ in ENDPOINTS] == ["leagues", "teams", "players", "fixtures"]
