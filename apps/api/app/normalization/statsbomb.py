"""StatsBomb Open Data → canonical normalisation.

StatsBomb's open data is the second structured source in the platform. Two facts
shape this module:

* **Player ids are per match.** The same human appears under a different id in every
  match, so a player id can never be treated as an identity. Players are resolved
  through the conservative resolver (normalised name + country + shared club) and
  every mapping keeps its own provider id.
* **Lineups carry position intervals, events carry the actions.** Minutes are
  *derived* from the position intervals, and goals/assists are counted from the
  event stream. Both are labelled as derived in the stored row, never presented as
  a provider statistic.

The source-native event type is always preserved next to the canonical event type.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import (
    Club,
    ClubIdentity,
    Competition,
    CompetitionSeason,
    Match,
    MatchEvent,
    MatchLineup,
    MatchTeam,
    Player,
    PlayerIdentity,
    PlayerMatchStats,
    Season,
)
from app.db.models.expansion import CompetitionIdentity, PlayerAlias
from app.identity.names import name_key, normalize_name

PROVIDER = "statsbomb"

# StatsBomb event type -> canonical event type.
_EVENT_TYPE_MAP = {
    "Starting XI": "OTHER",
    "Goal": "GOAL",
    "Own Goal": "GOAL",
    "Penalty": "OTHER",
    "Missed Penalty": "OTHER",
    "Shot": "OTHER",
    "Shot Saved": "OTHER",
    "Goal Keeper": "OTHER",
    "Pass": "OTHER",
    "Ball Receipt": "OTHER",
    "In Possession": "OTHER",
    "Carry": "OTHER",
    "Duel": "OTHER",
    "Foul": "OTHER",
    "Substitution": "SUBSTITUTION",
    "Card": "CARD",
    "Offside": "OTHER",
    "Miscontrol": "OTHER",
    "Dispossessed": "OTHER",
    "Recovery": "OTHER",
    "Pressure": "OTHER",
    "Block": "OTHER",
    "Ball Receipt*": "OTHER",
    "50/50": "OTHER",
    "Interception": "OTHER",
    "Possession": "OTHER",
    "Possession Adjusted": "OTHER",
    "Post": "OTHER",
    "Play On": "OTHER",
    "Pass Completion": "OTHER",
    "Ball Recovery": "OTHER",
    "Team Set Piece": "OTHER",
    "Player Off": "SUBSTITUTION",
    "Player On": "SUBSTITUTION",
    "Player Off Pitch": "SUBSTITUTION",
    "Temporary Card": "CARD",
    "VAR": "VAR",
}

_POSITION_GROUP = {
    "Goalkeeper": "GK",
    "Right Back": "DEF",
    "Right Center Back": "DEF",
    "Center Back": "DEF",
    "Left Center Back": "DEF",
    "Left Back": "DEF",
    "Right Wing Back": "DEF",
    "Left Wing Back": "DEF",
    "Right Center Midfield": "MID",
    "Center Midfield": "MID",
    "Left Center Midfield": "MID",
    "Right Midfield": "MID",
    "Left Midfield": "MID",
    "Right Attacking Midfield": "MID",
    "Left Attacking Midfield": "MID",
    "Attacking Midfield": "MID",
    "Right Wing": "ATT",
    "Left Wing": "ATT",
    "Right Forward": "ATT",
    "Left Forward": "ATT",
    "Center Forward": "ATT",
    "Second Striker": "ATT",
    "Left Center Forward": "ATT",
    "Right Center Forward": "ATT",
}


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _match_datetime(payload: dict[str, Any]) -> datetime | None:
    """Kick-off as an instant.

    StatsBomb splits the fixture date (`match_date`, an ISO date) from the kick-off
    time (`kick_off`, a wall-clock time). Both are needed; neither alone is a
    timestamp.
    """
    date_part = payload.get("match_date")
    time_part = payload.get("kick_off")
    if date_part and time_part:
        try:
            day = date.fromisoformat(str(date_part))
            clock = datetime.strptime(str(time_part).split(".")[0], "%H:%M:%S")
            return datetime(
                day.year,
                day.month,
                day.day,
                clock.hour,
                clock.minute,
                clock.second,
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass
    return _parse_kickoff(payload.get("kick_off") or date_part)


def _position_code(position: str | None) -> str | None:
    """Short code for a position name ("Left Defensive Midfield" -> "LDM").

    The canonical lineup column is a short code; the source-native name is kept in
    the raw stats so nothing is lost.
    """
    if not position:
        return None
    parts = [part for part in str(position).split() if part]
    if not parts:
        return None
    code = "".join(part[0] for part in parts).upper()
    return code[:6]


def _minutes_from_positions(positions: list[dict[str, Any]]) -> int | None:
    """Derived minutes from the lineup's position intervals.

    Returns None when the lineup has no usable interval — an unknown playing time
    stays unknown.
    """
    if not positions:
        return None
    total = 0
    measured = False
    for entry in positions:
        start = entry.get("from")
        end = entry.get("to")
        if not start:
            continue
        start_parts = [int(part) for part in str(start).split(":")[:2]]
        start_seconds = start_parts[0] * 60 + start_parts[1]
        if end:
            end_parts = [int(part) for part in str(end).split(":")[:2]]
            end_seconds = end_parts[0] * 60 + end_parts[1]
        else:
            end_seconds = 90 * 60
        delta = end_seconds - start_seconds
        if delta > 0:
            total += delta
            measured = True
    if not measured:
        return None
    return int(round(total / 60))


class StatsbombNormalizer:
    """Normalises StatsBomb open-data payloads into the canonical layer."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ helpers
    async def _competition(self, competition_id: int, name: str, country: str) -> Competition:
        identity = (
            await self._session.execute(
                select(CompetitionIdentity).where(
                    CompetitionIdentity.provider == PROVIDER,
                    CompetitionIdentity.provider_competition_id == str(competition_id),
                )
            )
        ).scalar_one_or_none()
        if identity is not None:
            return (
                await self._session.execute(
                    select(Competition).where(Competition.id == identity.competition_id)
                )
            ).scalar_one()
        competition = Competition(name=name, country=country, type="LEAGUE")
        self._session.add(competition)
        await self._session.flush()
        self._session.add(
            CompetitionIdentity(
                competition_id=competition.id,
                provider=PROVIDER,
                provider_competition_id=str(competition_id),
                confidence=1.0,
                resolution_method="DIRECT_PROVIDER_ID",
            )
        )
        await self._session.flush()
        return competition

    async def _season(self, season_id: int, season_name: str) -> Season:
        existing = (
            await self._session.execute(select(Season).where(Season.name == season_name))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        start_year = 0
        for part in str(season_name).replace("/", " ").split():
            if part.isdigit() and len(part) == 4:
                start_year = int(part)
                break
        season = Season(
            name=season_name,
            start_year=start_year or 0,
            end_year=(start_year + 1) if start_year else 0,
        )
        self._session.add(season)
        await self._session.flush()
        return season

    async def _club(self, team: dict[str, Any]) -> Club | None:
        team_id = team.get("home_team_id") or team.get("away_team_id") or team.get("id")
        if team_id is None:
            return None
        provider_id = str(team_id)
        identity = (
            await self._session.execute(
                select(ClubIdentity).where(
                    ClubIdentity.provider == PROVIDER,
                    ClubIdentity.provider_club_id == provider_id,
                )
            )
        ).scalar_one_or_none()
        if identity is not None:
            return (
                await self._session.execute(
                    select(Club).where(Club.id == identity.club_id)
                )
            ).scalar_one()
        country = (team.get("country") or {}).get("name") or "Unknown"
        club = Club(name=team.get("home_team_name") or team.get("away_team_name") or provider_id, country=country)
        self._session.add(club)
        await self._session.flush()
        self._session.add(
            ClubIdentity(
                club_id=club.id,
                provider=PROVIDER,
                provider_club_id=provider_id,
                confidence=1.0,
                resolution_method="DIRECT_PROVIDER_ID",
            )
        )
        await self._session.flush()
        return club

    async def _resolve_player(
        self,
        *,
        provider_player_id: str,
        name: str,
        country: str | None,
        club_ids: set[str],
        position: str | None = None,
    ) -> tuple[Player, str]:
        """Resolve a StatsBomb player onto a canonical player.

        StatsBomb player ids are per match, so the id only ever proves "this record".
        The human is resolved by name + country + a shared club.
        """
        identity = (
            await self._session.execute(
                select(PlayerIdentity).where(
                    PlayerIdentity.provider == PROVIDER,
                    PlayerIdentity.provider_player_id == provider_player_id,
                )
            )
        ).scalar_one_or_none()
        if identity is not None:
            player = (
                await self._session.execute(
                    select(Player).where(Player.id == identity.player_id)
                )
            ).scalar_one()
            await self._record_player_provenance(
                player=player,
                provider_player_id=str(provider_player_id),
                name=name,
                country=country,
                position=position,
            )
            return player, "DIRECT_PROVIDER_ID"

        key = name_key(name)
        candidates = (
            await self._session.execute(select(Player).where(Player.name_normalized == key))
        ).scalars().all()
        if not candidates:
            candidates = (
                await self._session.execute(
                    select(Player).where(Player.name == name)
                )
            ).scalars().all()

        best: tuple[Player, float] | None = None
        for candidate in candidates:
            score = 0.0
            if normalize_name(candidate.name) == normalize_name(name):
                score += 0.6
            if country and candidate.nationality and normalize_name(candidate.nationality) == normalize_name(country):
                score += 0.3
            elif country and candidate.nationality:
                score -= 0.3
            if best is None or score > best[1]:
                best = (candidate, score)

        if best is not None and best[1] >= 0.85:
            player = best[0]
            method = "STRONG_EVIDENCE"
            if position and not player.primary_position:
                player.primary_position = position
        else:
            player = Player(
                name=name,
                nationality=country,
                name_normalized=key,
                display_name=name,
                primary_position=position,
                data_completeness=round(1 / 8, 4),
                last_synced_at=datetime.now(timezone.utc),
            )
            self._session.add(player)
            await self._session.flush()
            method = "NEW"

        await self._record_player_provenance(
            player=player,
            provider_player_id=str(provider_player_id),
            name=name,
            country=country,
            position=position,
        )

        self._session.add(
            PlayerIdentity(
                player_id=player.id,
                provider=PROVIDER,
                provider_player_id=provider_player_id,
                confidence=1.0 if method == "DIRECT_PROVIDER_ID" else 0.9,
                resolution_method=method,
            )
        )
        self._session.add(
            PlayerAlias(
                player_id=player.id,
                alias=name,
                alias_type="SOURCE_NAME",
                provider=PROVIDER,
                provider_entity_id=provider_player_id,
                confidence=0.9,
            )
        )
        await self._session.flush()
        return player, method

    # ------------------------------------------------------------------- match
    async def _record_player_provenance(
        self,
        *,
        player: Player,
        provider_player_id: str,
        name: str,
        country: str | None,
        position: str | None,
    ) -> None:
        """Field-level provenance for a StatsBomb player.

        This is where the two providers meet: when StatsBomb and API-Football describe
        the same human differently, the disagreement is recorded in
        ``source_conflicts`` instead of one value silently replacing the other.
        """
        from app.db.models.expansion import FieldProvenance, SourceConflict

        fields = {
            "name": (name, "PROVIDER_NAME"),
            "nationality": (country, None),
            "primary_position": (position, "PROVIDER_POSITION"),
        }
        for field_name, (value, transformation) in fields.items():
            if value is None:
                continue
            existing = (
                await self._session.execute(
                    select(FieldProvenance).where(
                        FieldProvenance.entity_type == "player",
                        FieldProvenance.entity_id == player.id,
                        FieldProvenance.field_name == field_name,
                        FieldProvenance.provider == PROVIDER,
                    )
                )
            ).scalar_one_or_none()
            payload = {"value": value, "transformation": transformation}
            if existing is None:
                self._session.add(
                    FieldProvenance(
                        entity_type="player",
                        entity_id=player.id,
                        field_name=field_name,
                        provider=PROVIDER,
                        provider_entity_id=provider_player_id,
                        source_value=payload,
                        transformation=transformation,
                        confidence=0.9,
                    )
                )
            else:
                existing.source_value = payload
                existing.retrieved_at = datetime.now(timezone.utc)

            canonical_value = getattr(player, field_name, None)
            if canonical_value is None or str(canonical_value) == str(value):
                continue
            conflict = (
                await self._session.execute(
                    select(SourceConflict).where(
                        SourceConflict.entity_type == "player",
                        SourceConflict.entity_id == player.id,
                        SourceConflict.field_name == field_name,
                    )
                )
            ).scalar_one_or_none()
            candidates = {"canonical": canonical_value, PROVIDER: value}
            if conflict is None:
                self._session.add(
                    SourceConflict(
                        entity_type="player",
                        entity_id=player.id,
                        field_name=field_name,
                        candidates=candidates,
                        status="OPEN",
                        resolution="canonical value retained; conflict recorded for review",
                    )
                )
            else:
                merged = dict(conflict.candidates or {})
                merged.update(candidates)
                conflict.candidates = merged
                conflict.status = "OPEN"

    async def normalize_match(
        self, payload: dict[str, Any]
    ) -> tuple[Match | None, dict[str, int]]:
        counters = {"matches_inserted": 0, "matches_updated": 0, "clubs": 0}
        match_id = payload.get("match_id")
        if match_id is None:
            return None, counters
        competition = payload.get("competition") or {}
        season = payload.get("season") or {}
        home = await self._club(payload.get("home_team") or {})
        away = await self._club(payload.get("away_team") or {})
        if home is None or away is None:
            return None, counters
        counters["clubs"] = 2

        comp = await self._competition(
            int(competition.get("competition_id") or 0),
            competition.get("competition_name") or "StatsBomb competition",
            competition.get("country_name") or "Unknown",
        )
        sea = await self._season(int(season.get("season_id") or 0), season.get("season_name") or "unknown")
        existing_cs = (
            await self._session.execute(
                select(CompetitionSeason).where(
                    CompetitionSeason.competition_id == comp.id,
                    CompetitionSeason.season_id == sea.id,
                )
            )
        ).scalar_one_or_none()
        if existing_cs is None:
            existing_cs = CompetitionSeason(competition_id=comp.id, season_id=sea.id)
            self._session.add(existing_cs)
            await self._session.flush()

        kick_off = _match_datetime(payload)
        if kick_off is None:
            return None, counters

        match = (
            await self._session.execute(
                select(Match).where(
                    Match.provider == PROVIDER,
                    Match.provider_fixture_id == str(match_id),
                )
            )
        ).scalar_one_or_none()
        if match is None:
            match = Match(
                provider=PROVIDER,
                provider_fixture_id=str(match_id),
                competition_season_id=existing_cs.id,
                home_club_id=home.id,
                away_club_id=away.id,
                date=kick_off,
                status="FINISHED",
                status_detail="available",
                round=str(payload.get("match_week") or ""),
                venue_name=(payload.get("stadium") or {}).get("name"),
                venue_city=(payload.get("stadium") or {}).get("name"),
                referee=(payload.get("referee") or {}).get("name"),
                home_score=payload.get("home_score"),
                away_score=payload.get("away_score"),
            )
            self._session.add(match)
            await self._session.flush()
            counters["matches_inserted"] += 1
        else:
            counters["matches_updated"] += 1

        for club, opponent, is_home, goals_for, goals_against in (
            (home, away, True, payload.get("home_score"), payload.get("away_score")),
            (away, home, False, payload.get("away_score"), payload.get("home_score")),
        ):
            existing_team = (
                await self._session.execute(
                    select(MatchTeam).where(
                        MatchTeam.match_id == match.id,
                        MatchTeam.club_id == club.id,
                    )
                )
            ).scalar_one_or_none()
            if existing_team is None:
                self._session.add(
                    MatchTeam(
                        match_id=match.id,
                        club_id=club.id,
                        opponent_club_id=opponent.id,
                        is_home=is_home,
                        result="WIN" if (goals_for or 0) > (goals_against or 0)
                        else "DRAW" if goals_for == goals_against
                        else "LOSE",
                        goals_for=goals_for,
                        goals_against=goals_against,
                    )
                )
        await self._session.flush()
        return match, counters

    # ----------------------------------------------------------------- lineups
    async def normalize_lineups(
        self, payload: list[dict[str, Any]], match: Match
    ) -> dict[str, int]:
        counters = {
            "lineups": 0,
            "players_inserted": 0,
            "players_matched": 0,
            "player_match_stats": 0,
        }
        for entry in payload:
            # The open-data lineup file carries `team_id` / `team_name`; some
            # variants carry a nested `team` object instead.
            team = entry.get("team") or {}
            team_id = str(entry.get("team_id") or team.get("id") or "")
            team_name = entry.get("team_name") or team.get("name") or ""
            club = None
            if team_id:
                identity = (
                    await self._session.execute(
                        select(ClubIdentity).where(
                            ClubIdentity.provider == PROVIDER,
                            ClubIdentity.provider_club_id == team_id,
                        )
                    )
                ).scalar_one_or_none()
                if identity is not None:
                    club = (
                        await self._session.execute(
                            select(Club).where(Club.id == identity.club_id)
                        )
                    ).scalar_one()
            for player_entry in entry.get("lineup") or []:
                provider_player_id = player_entry.get("player_id")
                name = player_entry.get("player_name")
                if provider_player_id is None or not name:
                    continue
                country = (player_entry.get("country") or {}).get("name")

                positions = player_entry.get("positions") or []
                primary_position = positions[0].get("position") if positions else None
                position_group = _POSITION_GROUP.get(primary_position or "", None)
                position_code = _position_code(primary_position)
                minutes = _minutes_from_positions(positions)
                is_starter = bool(
                    positions and (positions[0].get("start_reason") or "").startswith("Starting XI")
                )
                jersey = player_entry.get("jersey_number")

                player, method = await self._resolve_player(
                    provider_player_id=str(provider_player_id),
                    name=name,
                    country=country,
                    club_ids={team_id} if team_id else set(),
                    position=position_group,
                )
                if method == "NEW":
                    counters["players_inserted"] += 1
                else:
                    counters["players_matched"] += 1

                if club is not None:
                    lineup = (
                        await self._session.execute(
                            select(MatchLineup).where(
                                MatchLineup.match_id == match.id,
                                MatchLineup.club_id == club.id,
                                MatchLineup.player_id == player.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if lineup is None:
                        self._session.add(
                            MatchLineup(
                                match_id=match.id,
                                club_id=club.id,
                                player_id=player.id,
                                is_starter=is_starter,
                                jersey_number=jersey,
                                position=position_group,
                                formation_position=position_code,
                            )
                        )
                        counters["lineups"] += 1

                    stats = (
                        await self._session.execute(
                            select(PlayerMatchStats).where(
                                PlayerMatchStats.match_id == match.id,
                                PlayerMatchStats.club_id == club.id,
                                PlayerMatchStats.player_id == player.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if stats is None:
                        self._session.add(
                            PlayerMatchStats(
                                match_id=match.id,
                                club_id=club.id,
                                player_id=player.id,
                                provider=PROVIDER,
                                provider_player_id=str(provider_player_id),
                                provider_fixture_id=match.provider_fixture_id,
                                provider_club_id=team_id or None,
                                is_starter=is_starter,
                                position=position_group,
                                formation_position=position_code,
                                jersey_number=jersey,
                                minutes=minutes,
                                raw_stats={
                                    "source": "statsbomb-lineup",
                                    "minutes_derivation": "sum of the lineup position intervals",
                                    "team_name": team_name,
                                    "country": country,
                                    "position_name": primary_position,
                                    "position_intervals": positions,
                                },
                            )
                        )
                        counters["player_match_stats"] += 1
                    elif minutes is not None and stats.minutes is None:
                        stats.minutes = minutes
        await self._session.flush()
        return counters

    # ------------------------------------------------------------------ events
    async def normalize_events(
        self, payload: list[dict[str, Any]], match: Match
    ) -> dict[str, int]:
        counters = {"events": 0, "goals": 0, "assists": 0}
        team_clubs: dict[str, uuid.UUID] = {}
        for entry in payload:
            team = entry.get("team") or {}
            team_id = str(team.get("id") or "")
            if not team_id:
                continue
            if team_id not in team_clubs:
                identity = (
                    await self._session.execute(
                        select(ClubIdentity).where(
                            ClubIdentity.provider == PROVIDER,
                            ClubIdentity.provider_club_id == team_id,
                        )
                    )
                ).scalar_one_or_none()
                if identity is None:
                    continue
                team_clubs[team_id] = identity.club_id

            event_type_name = (entry.get("type") or {}).get("name") or "OTHER"
            canonical_type = _EVENT_TYPE_MAP.get(event_type_name, "OTHER")
            # StatsBomb does not publish a "Goal" event: a goal is a Shot whose
            # outcome is "Goal", and the assist is recorded on that shot (or on a
            # "Goal Assist" pass). Both are mapped here so the canonical layer can
            # count goals and assists without inventing them.
            shot = entry.get("shot") or {}
            pass_block = entry.get("pass") or {}
            shot_outcome = (shot.get("outcome") or {}).get("name")
            pass_type = (pass_block.get("type") or {}).get("name")
            goal_shooter = False
            if event_type_name == "Shot" and shot_outcome == "Goal":
                canonical_type = "GOAL"
                goal_shooter = True
            if pass_type == "Goal Assist":
                canonical_type = "GOAL"
            assist_ids: list[Any] = []
            if goal_shooter:
                assist_ids = list(shot.get("assists") or [])
            actor = entry.get("player") or {}
            actor_id = actor.get("id")
            player_id = None
            assist_player_id = None
            if actor_id is not None:
                identity = (
                    await self._session.execute(
                        select(PlayerIdentity).where(
                            PlayerIdentity.provider == PROVIDER,
                            PlayerIdentity.provider_player_id == str(actor_id),
                        )
                    )
                ).scalar_one_or_none()
                if identity is not None:
                    player_id = identity.player_id
            if pass_type == "Goal Assist" and player_id is not None:
                assist_player_id = player_id
                player_id = None  # the assister is not the scorer
            assist = entry.get("assist") or {}
            if assist.get("id") is not None:
                identity = (
                    await self._session.execute(
                        select(PlayerIdentity).where(
                            PlayerIdentity.provider == PROVIDER,
                            PlayerIdentity.provider_player_id == str(assist["id"]),
                        )
                    )
                ).scalar_one_or_none()
                if identity is not None:
                    assist_player_id = identity.player_id
            for assist_entry in assist_ids:
                if assist_player_id is not None:
                    break
                assist_id = (assist_entry or {}).get("id")
                if assist_id is None:
                    continue
                identity = (
                    await self._session.execute(
                        select(PlayerIdentity).where(
                            PlayerIdentity.provider == PROVIDER,
                            PlayerIdentity.provider_player_id == str(assist_id),
                        )
                    )
                ).scalar_one_or_none()
                if identity is not None:
                    assist_player_id = identity.player_id

            club_id = team_clubs.get(team_id)
            if club_id is None:
                continue
            event_key = str(entry.get("id") or f"{entry.get('index')}")
            existing = (
                await self._session.execute(
                    select(MatchEvent).where(
                        MatchEvent.match_id == match.id,
                        MatchEvent.event_key == event_key,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                # Re-classification is allowed: the canonical event type and the
                # participants are derived, and a later run may know more (for
                # example that a Shot with a "Goal" outcome is a goal).
                existing.event_type = canonical_type
                existing.event_detail = event_type_name[:64]
                if player_id is not None:
                    existing.player_id = player_id
                if assist_player_id is not None:
                    existing.assist_player_id = assist_player_id
                continue
            self._session.add(
                MatchEvent(
                    match_id=match.id,
                    club_id=club_id,
                    player_id=player_id,
                    assist_player_id=assist_player_id,
                    event_type=canonical_type,
                    event_detail=event_type_name[:64],
                    minute=int(entry.get("minute") or 0),
                    extra_minute=entry.get("second"),
                    event_key=event_key[:255],
                    provider_event_id=str(entry.get("id") or "")[:128] or None,
                )
            )
            counters["events"] += 1
            if canonical_type == "GOAL":
                counters["goals"] += 1
                if player_id is not None:
                    await self._increment_player_stat(match.id, club_id, player_id, "goals")
                if assist_player_id is not None:
                    await self._increment_player_stat(match.id, club_id, assist_player_id, "assists")
        await self._session.flush()
        return counters

    async def _increment_player_stat(
        self, match_id: uuid.UUID, club_id: uuid.UUID, player_id: uuid.UUID, field: str
    ) -> None:
        stats = (
            await self._session.execute(
                select(PlayerMatchStats).where(
                    PlayerMatchStats.match_id == match_id,
                    PlayerMatchStats.club_id == club_id,
                    PlayerMatchStats.player_id == player_id,
                )
            )
        ).scalar_one_or_none()
        if stats is None:
            return
        current = getattr(stats, field) or 0
        setattr(stats, field, current + 1)
