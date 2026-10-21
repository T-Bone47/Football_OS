"""A health answer is the worst of its measured components; unmeasured is UNKNOWN, never OK."""
from __future__ import annotations

import pytest

from app.observability.status import DEGRADED, OK, UNAVAILABLE, UNKNOWN, aggregate_status


@pytest.mark.parametrize(
    "components,expected",
    [
        ({"db": OK, "storage": OK}, OK),
        ({"db": OK, "storage": UNKNOWN}, UNKNOWN),
        ({"db": OK, "model": DEGRADED, "storage": UNKNOWN}, DEGRADED),
        ({"db": UNAVAILABLE, "model": DEGRADED}, UNAVAILABLE),
        ({}, UNKNOWN),
    ],
)
def test_worst_of(components, expected):
    assert aggregate_status(components) == expected
