"""Pandera schema for the one StatsBomb resource this repo has real live
data for (architecture doc §27). Fields taken from the actual response
observed in tests/integration/test_statsbomb_adapter.py, not guessed.
"""
from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series


class StatsBombCompetitionSchema(pa.DataFrameModel):
    competition_id: Series[int]
    season_id: Series[int]
    country_name: Series[str]
    competition_name: Series[str]
    competition_gender: Series[str]

    class Config:
        coerce = True
        strict = False  # StatsBomb adds fields over time; don't break on extras
