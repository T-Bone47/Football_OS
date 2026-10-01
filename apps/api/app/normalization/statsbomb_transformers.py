"""StatsBomb Open Data -> canonical Silver transformers (Phase 17).

Until Phase 17 the Silver layer only understood API-Football payloads, so
StatsBomb data — the one provider reachable without a key — stopped at
Bronze. These pure functions emit the same Normalized* schemas the
API-Football transformers do, so NormalizationService's existing identity
resolution and upsert logic is reused unchanged.

Provider facts these functions rely on (observed in real payloads):
- matches/<comp>/<season>.json is a list; scores are full-time scores
  including extra time and EXCLUDING penalty shootouts.
- events/<match>.json uses period 5 for penalty shootouts. Those kicks are
  not match goals and are dropped.
- kick_off has no timezone in the payload; it is interpreted as UTC and the
  ambiguity is recorded by the caller, not hidden.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.normalization.schemas import (
    NormalizedFixture,
    NormalizedMatchEvent,
    NormalizedMatchLineup,
    NormalizedScore,
    NormalizedScoreDetail,
)

SHOOTOUT_PERIOD = 5


def _position_code(position_name: str | None) -> str | None:
    if not position_name:
        return None
    name = position_name.lower()
    if "goalkeeper" in name:
        return "G"
    if "back" in name:
        return "D"
    if "forward" in name or "striker" in name:
        return "F"
    if "midfield" in name or "wing" in name:
        return "M"
    return None


def _season_start_year(season_name: str) -> int:
    # "2022" or "2015/2016"
    return int(str(season_name).split("/")[0])


def _kickoff(match_date: str, kick_off: str | None) -> datetime:
    time_part = (kick_off or "00:00:00.000").split(".")[0]
    return datetime.fromisoformat(f"{match_date}T{time_part}").replace(tzinfo=timezone.utc)


def transform_statsbomb_matches(payload: list[dict[str, Any]]) -> list[NormalizedFixture]:
    fixtures: list[NormalizedFixture] = []
    for m in payload:
        home = m["home_team"]
        away = m["away_team"]
        comp = m["competition"]
        hs, as_ = m.get("home_score"), m.get("away_score")
        finished = hs is not None and as_ is not None
        fixtures.append(
            NormalizedFixture(
                provider_fixture_id=str(m["match_id"]),
                date=_kickoff(m["match_date"], m.get("kick_off")),
                status="FINISHED" if finished else "SCHEDULED",
                status_detail=m.get("match_status"),
                round=str(m["match_week"]) if m.get("match_week") is not None else None,
                stage=(m.get("competition_stage") or {}).get("name"),
                venue_name=(m.get("stadium") or {}).get("name"),
                referee=(m.get("referee") or {}).get("name"),
                provider_league_id=str(comp["competition_id"]),
                league_name=comp["competition_name"],
                league_country=comp.get("country_name") or "Unknown",
                season_year=_season_start_year(m["season"]["season_name"]),
                home_provider_club_id=str(home["home_team_id"]),
                home_club_name=home["home_team_name"],
                away_provider_club_id=str(away["away_team_id"]),
                away_club_name=away["away_team_name"],
                home_winner=(hs > as_) if finished else None,
                away_winner=(as_ > hs) if finished else None,
                home_score=hs,
                away_score=as_,
                score=NormalizedScore(fulltime=NormalizedScoreDetail(home=hs, away=as_)),
            )
        )
    return fixtures


def is_starter(positions: list[dict[str, Any]]) -> bool:
    """A starter's first position begins at 00:00 in period 1. start_reason
    is usually "Starting XI" but not always: in match 3754047 (Premier League
    2015/16) all 11 Swansea starters carry "Tactical Shift" at 00:00."""
    return any(
        pos.get("start_reason") == "Starting XI"
        or (pos.get("from") in ("00:00", "00:00:00") and pos.get("from_period") == 1)
        for pos in positions
    )


def transform_statsbomb_lineups(payload: list[dict[str, Any]], fixture_id: str) -> list[NormalizedMatchLineup]:
    rows: list[NormalizedMatchLineup] = []
    for team in payload:
        for p in team.get("lineup", []):
            positions = p.get("positions") or []
            starter = is_starter(positions)
            first_position = positions[0].get("position") if positions else None
            # formation_position is VARCHAR(16); StatsBomb's numeric position_id
            # fits and is the stable identifier (the name maps via _position_code).
            position_id = positions[0].get("position_id") if positions else None
            rows.append(
                NormalizedMatchLineup(
                    provider_fixture_id=str(fixture_id),
                    provider_club_id=str(team["team_id"]),
                    club_name=team.get("team_name"),
                    provider_player_id=str(p["player_id"]),
                    player_name=p["player_name"],
                    jersey_number=p.get("jersey_number"),
                    position=_position_code(first_position),
                    grid=str(position_id) if position_id is not None else None,
                    is_starter=starter,
                )
            )
    return rows


def _card(event: dict[str, Any]) -> str | None:
    for key in ("foul_committed", "bad_behaviour"):
        card = (event.get(key) or {}).get("card")
        if card:
            return card.get("name")
    return None


def transform_statsbomb_events(payload: list[dict[str, Any]], fixture_id: str) -> list[NormalizedMatchEvent]:
    """Goals, cards and substitutions only — the same discrete-event scope
    the canonical match_events table has for API-Football. Full StatsBomb
    event streams (passes, carries, pressures) stay in Bronze."""
    out: list[NormalizedMatchEvent] = []
    for e in payload:
        if e.get("period") == SHOOTOUT_PERIOD:
            continue
        type_name = (e.get("type") or {}).get("name")
        team = e.get("team") or {}
        player = e.get("player") or {}
        base = dict(
            provider_fixture_id=str(fixture_id),
            provider_club_id=str(team.get("id")),
            club_name=team.get("name"),
            provider_player_id=str(player["id"]) if player.get("id") is not None else None,
            player_name=player.get("name"),
            minute=int(e.get("minute", 0)),
            event_key=e["id"],
            provider_event_id=e["id"],
        )
        if type_name == "Shot" and ((e.get("shot") or {}).get("outcome") or {}).get("name") == "Goal":
            shot_type = ((e.get("shot") or {}).get("type") or {}).get("name")
            out.append(NormalizedMatchEvent(**base, event_type="GOAL",
                                            event_detail="Penalty" if shot_type == "Penalty" else "Normal Goal"))
        elif type_name == "Own Goal For":
            out.append(NormalizedMatchEvent(**{**base, "provider_player_id": None, "player_name": None},
                                            event_type="GOAL", event_detail="Own Goal"))
        elif type_name in ("Foul Committed", "Bad Behaviour") and _card(e):
            out.append(NormalizedMatchEvent(**base, event_type="CARD", event_detail=_card(e)))
        elif type_name == "Substitution":
            replacement = (e.get("substitution") or {}).get("replacement") or {}
            out.append(
                NormalizedMatchEvent(
                    **base,
                    event_type="SUBSTITUTION",
                    event_detail="Substitution",
                    provider_assist_id=str(replacement["id"]) if replacement.get("id") is not None else None,
                    assist_name=replacement.get("name"),
                )
            )
    return out
