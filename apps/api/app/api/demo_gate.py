"""Router dependency: Decision Lab (Phase 13) and Outcome Intelligence (Phase 14) run on built-in demonstration
figures only, so outside demo mode they answer 409 DEMO_ONLY instead of returning invented numbers."""
from __future__ import annotations

from fastapi import HTTPException, Response

from app.demo import demo_data_allowed


def require_demo_data(response: Response) -> None:
    if not demo_data_allowed():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_ONLY",
                "detail": (
                    "This module computes from built-in demonstration figures, not from your data. It is disabled "
                    "until it is rebuilt on verified canonical data (set FOOTBALL_OS_DEMO_DATA=1 outside production to demo it)."
                ),
            },
        )
    response.headers["X-Data-Origin"] = "DEMO_FIXTURE"
