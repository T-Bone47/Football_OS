from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class NormalizedCompetition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_id: str
    name: str
    country: str
    code: str | None = None
    type: str = "LEAGUE"


class NormalizedSeason(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    start_year: int
    end_year: int
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False


class NormalizedClub(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_id: str
    name: str
    code: str | None = None
    country: str
    founded: int | None = None
    venue_name: str | None = None
    venue_capacity: int | None = None
    logo_url: str | None = None


class NormalizedPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_id: str
    name: str
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    primary_position: str | None = None
    photo_url: str | None = None


class NormalizedPlayerStats(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_player_id: str
    provider_club_id: str | None = None
    provider_league_id: str
    season_year: int
    appearances: int = 0
    lineups: int = 0
    minutes: int = 0
    position: str | None = None
    rating: float | None = None
    goals: int = 0
    assists: int = 0
    conceded: int = 0
    raw_stats: dict[str, Any] = {}
