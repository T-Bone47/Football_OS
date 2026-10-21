"""Shared reading of `player_contribution_snapshots.dimension_scores`.

The snapshot column stores one record per dimension:

    {"duels": {"score": 0.62, "summary": "...", "key_metrics": {...}}, ...}

Every consumer that needs a single number per dimension must use this helper,
and an absent score must stay unknown (None). A missing dimension is never
coerced to 0.0, because 0.0 would be read as a measured zero performance.
"""
from __future__ import annotations


def dimension_scores_by_dimension(raw: dict | None) -> dict[str, float | None]:
    """Flatten persisted dimension records into one score per dimension."""
    scores: dict[str, float | None] = {}
    for key, value in (raw or {}).items():
        score = value.get("score") if isinstance(value, dict) else value
        scores[key] = float(score) if isinstance(score, (int, float)) else None
    return scores
