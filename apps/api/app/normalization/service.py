from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import (
    Club,
    ClubIdentity,
    Competition,
    CompetitionSeason,
    Match,
    MatchTeam,
    Player,
    PlayerIdentity,
    PlayerSeasonStats,
    Season,
)
from app.db.models.provenance import DataSnapshot, IngestionRun
from app.normalization.schemas import (
    NormalizedClub,
    NormalizedFixture,
    NormalizedPlayer,
    NormalizedPlayerStats,
)
from app.normalization.transformers import (
    transform_api_football_fixtures,
    transform_api_football_players,
    transform_api_football_teams,
)


class NormalizationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_competition(
        self, name: str, country: str, code: str | None = None, comp_type: str = "LEAGUE"
    ) -> Competition:
        stmt = select(Competition).where(
            Competition.name == name, Competition.country == country
        )
        comp = (await self._session.execute(stmt)).scalar_one_or_none()
        if comp is None:
            comp = Competition(name=name, country=country, code=code, type=comp_type)
            self._session.add(comp)
            await self._session.flush()
        return comp

    async def get_or_create_season(
        self, name: str, start_year: int, end_year: int
    ) -> Season:
        stmt = select(Season).where(Season.name == name)
        season = (await self._session.execute(stmt)).scalar_one_or_none()
        if season is None:
            season = Season(name=name, start_year=start_year, end_year=end_year)
            self._session.add(season)
            await self._session.flush()
        return season

    async def get_or_create_competition_season(
        self, competition_id: uuid.UUID, season_id: uuid.UUID
    ) -> CompetitionSeason:
        stmt = select(CompetitionSeason).where(
            CompetitionSeason.competition_id == competition_id,
            CompetitionSeason.season_id == season_id,
        )
        cs = (await self._session.execute(stmt)).scalar_one_or_none()
        if cs is None:
            cs = CompetitionSeason(
                competition_id=competition_id, season_id=season_id, is_current=True
            )
            self._session.add(cs)
            await self._session.flush()
        return cs

    async def upsert_club(
        self, provider: str, norm_club: NormalizedClub
    ) -> Club:
        # Check identity registry (§21 Identity Resolution)
        id_stmt = select(ClubIdentity).where(
            ClubIdentity.provider == provider,
            ClubIdentity.provider_club_id == norm_club.provider_id,
        )
        identity = (await self._session.execute(id_stmt)).scalar_one_or_none()

        if identity is not None:
            # Club already known — update mutable fields if provided
            club_stmt = select(Club).where(Club.id == identity.club_id)
            club = (await self._session.execute(club_stmt)).scalar_one()
            if norm_club.venue_name and not club.venue_name:
                club.venue_name = norm_club.venue_name
            if norm_club.venue_capacity and not club.venue_capacity:
                club.venue_capacity = norm_club.venue_capacity
            if norm_club.logo_url and not club.logo_url:
                club.logo_url = norm_club.logo_url
            return club

        # Create new canonical Club
        club = Club(
            name=norm_club.name,
            code=norm_club.code,
            country=norm_club.country,
            founded=norm_club.founded,
            venue_name=norm_club.venue_name,
            venue_capacity=norm_club.venue_capacity,
            logo_url=norm_club.logo_url,
        )
        self._session.add(club)
        await self._session.flush()

        identity = ClubIdentity(
            club_id=club.id,
            provider=provider,
            provider_club_id=norm_club.provider_id,
            confidence=1.0,
            resolution_method="DIRECT_PROVIDER_ID",
        )
        self._session.add(identity)
        await self._session.flush()
        return club

    async def upsert_player(
        self, provider: str, norm_player: NormalizedPlayer
    ) -> Player:
        # Check identity registry (§21 Identity Resolution)
        id_stmt = select(PlayerIdentity).where(
            PlayerIdentity.provider == provider,
            PlayerIdentity.provider_player_id == norm_player.provider_id,
        )
        identity = (await self._session.execute(id_stmt)).scalar_one_or_none()

        if identity is not None:
            player_stmt = select(Player).where(Player.id == identity.player_id)
            player = (await self._session.execute(player_stmt)).scalar_one()
            if norm_player.primary_position and not player.primary_position:
                player.primary_position = norm_player.primary_position
            if norm_player.height_cm and not player.height_cm:
                player.height_cm = norm_player.height_cm
            if norm_player.weight_kg and not player.weight_kg:
                player.weight_kg = norm_player.weight_kg
            return player

        player = Player(
            name=norm_player.name,
            first_name=norm_player.first_name,
            last_name=norm_player.last_name,
            date_of_birth=norm_player.date_of_birth,
            nationality=norm_player.nationality,
            height_cm=norm_player.height_cm,
            weight_kg=norm_player.weight_kg,
            primary_position=norm_player.primary_position,
            photo_url=norm_player.photo_url,
        )
        self._session.add(player)
        await self._session.flush()

        identity = PlayerIdentity(
            player_id=player.id,
            provider=provider,
            provider_player_id=norm_player.provider_id,
            confidence=1.0,
            resolution_method="DIRECT_PROVIDER_ID",
        )
        self._session.add(identity)
        await self._session.flush()
        return player

    async def normalize_teams_payload(
        self, provider: str, payload: dict[str, Any]
    ) -> list[Club]:
        normalized_clubs = transform_api_football_teams(payload)
        clubs: list[Club] = []
        for nc in normalized_clubs:
            club = await self.upsert_club(provider, nc)
            clubs.append(club)
        await self._session.commit()
        return clubs

    async def normalize_players_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
    ) -> list[Player]:
        normalized_players, stats_list = transform_api_football_players(payload)
        players: list[Player] = []

        player_map: dict[str, Player] = {}
        for np in normalized_players:
            player = await self.upsert_player(provider, np)
            player_map[np.provider_id] = player
            players.append(player)

        # Cache club lookups
        club_lookup: dict[str, uuid.UUID] = {}
        # Cache competition_season lookups
        comp_season_lookup: dict[tuple[str, int], uuid.UUID] = {}

        for stat in stats_list:
            player = player_map.get(stat.provider_player_id)
            if not player:
                continue

            club_id = None
            if stat.provider_club_id:
                if stat.provider_club_id in club_lookup:
                    club_id = club_lookup[stat.provider_club_id]
                else:
                    id_stmt = select(ClubIdentity).where(
                        ClubIdentity.provider == provider,
                        ClubIdentity.provider_club_id == stat.provider_club_id,
                    )
                    id_row = (await self._session.execute(id_stmt)).scalar_one_or_none()
                    if id_row:
                        club_id = id_row.club_id
                        club_lookup[stat.provider_club_id] = club_id

            comp_key = (stat.provider_league_id, stat.season_year)
            if comp_key in comp_season_lookup:
                comp_season_id = comp_season_lookup[comp_key]
            else:
                comp = await self.get_or_create_competition(
                    name=f"League {stat.provider_league_id}" if stat.provider_league_id != "39" else "Premier League",
                    country="England" if stat.provider_league_id == "39" else "Unknown",
                    code="EPL" if stat.provider_league_id == "39" else None,
                )
                season = await self.get_or_create_season(
                    name=str(stat.season_year),
                    start_year=stat.season_year,
                    end_year=stat.season_year + 1,
                )
                comp_season = await self.get_or_create_competition_season(
                    competition_id=comp.id, season_id=season.id
                )
                comp_season_id = comp_season.id
                comp_season_lookup[comp_key] = comp_season_id

            # Upsert PlayerSeasonStats
            stat_stmt = select(PlayerSeasonStats).where(
                PlayerSeasonStats.player_id == player.id,
                PlayerSeasonStats.club_id == club_id,
                PlayerSeasonStats.competition_season_id == comp_season_id,
            )
            existing_stat = (await self._session.execute(stat_stmt)).scalar_one_or_none()

            if existing_stat is not None:
                existing_stat.appearances = stat.appearances
                existing_stat.lineups = stat.lineups
                existing_stat.minutes = stat.minutes
                existing_stat.position = stat.position
                existing_stat.rating = stat.rating
                existing_stat.goals = stat.goals
                existing_stat.assists = stat.assists
                existing_stat.conceded = stat.conceded
                existing_stat.raw_stats = stat.raw_stats
                existing_stat.snapshot_id = snapshot_id
            else:
                new_stat = PlayerSeasonStats(
                    player_id=player.id,
                    club_id=club_id,
                    competition_season_id=comp_season_id,
                    snapshot_id=snapshot_id,
                    appearances=stat.appearances,
                    lineups=stat.lineups,
                    minutes=stat.minutes,
                    position=stat.position,
                    rating=stat.rating,
                    goals=stat.goals,
                    assists=stat.assists,
                    conceded=stat.conceded,
                    raw_stats=stat.raw_stats,
                )
                self._session.add(new_stat)

        await self._session.commit()
        return players

    async def _resolve_or_create_club(
        self,
        provider: str,
        provider_club_id: str,
        name: str,
        country: str = "Unknown",
        logo_url: str | None = None,
    ) -> uuid.UUID:
        id_stmt = select(ClubIdentity).where(
            ClubIdentity.provider == provider,
            ClubIdentity.provider_club_id == provider_club_id,
        )
        identity = (await self._session.execute(id_stmt)).scalar_one_or_none()
        if identity is not None:
            return identity.club_id

        club = Club(
            name=name,
            country=country,
            logo_url=logo_url,
        )
        self._session.add(club)
        await self._session.flush()

        new_identity = ClubIdentity(
            club_id=club.id,
            provider=provider,
            provider_club_id=provider_club_id,
            confidence=1.0,
            resolution_method="DIRECT_PROVIDER_ID",
        )
        self._session.add(new_identity)
        await self._session.flush()
        return club.id

    async def normalize_fixtures_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
    ) -> list[Match]:
        normalized_fixtures = transform_api_football_fixtures(payload)
        matches: list[Match] = []

        club_cache: dict[str, uuid.UUID] = {}
        comp_season_cache: dict[tuple[str, int], uuid.UUID] = {}

        for f in normalized_fixtures:
            # 1. Resolve Competition and Season
            comp_key = (f.provider_league_id, f.season_year)
            if comp_key in comp_season_cache:
                comp_season_id = comp_season_cache[comp_key]
            else:
                comp = await self.get_or_create_competition(
                    name=f.league_name,
                    country=f.league_country,
                    code="EPL" if f.provider_league_id == "39" else None,
                )
                season = await self.get_or_create_season(
                    name=str(f.season_year),
                    start_year=f.season_year,
                    end_year=f.season_year + 1,
                )
                comp_season = await self.get_or_create_competition_season(
                    competition_id=comp.id, season_id=season.id
                )
                comp_season_id = comp_season.id
                comp_season_cache[comp_key] = comp_season_id

            # 2. Resolve Clubs (home and away) via DIRECT_PROVIDER_ID
            if f.home_provider_club_id in club_cache:
                home_club_id = club_cache[f.home_provider_club_id]
            else:
                home_club_id = await self._resolve_or_create_club(
                    provider=provider,
                    provider_club_id=f.home_provider_club_id,
                    name=f.home_club_name,
                    country=f.league_country,
                    logo_url=f.home_club_logo,
                )
                club_cache[f.home_provider_club_id] = home_club_id

            if f.away_provider_club_id in club_cache:
                away_club_id = club_cache[f.away_provider_club_id]
            else:
                away_club_id = await self._resolve_or_create_club(
                    provider=provider,
                    provider_club_id=f.away_provider_club_id,
                    name=f.away_club_name,
                    country=f.league_country,
                    logo_url=f.away_club_logo,
                )
                club_cache[f.away_provider_club_id] = away_club_id

            # 3. Determine winner club
            winner_club_id: uuid.UUID | None = None
            if f.home_winner is True:
                winner_club_id = home_club_id
            elif f.away_winner is True:
                winner_club_id = away_club_id
            elif f.status == "FINISHED":
                if f.home_score is not None and f.away_score is not None:
                    if f.home_score > f.away_score:
                        winner_club_id = home_club_id
                    elif f.away_score > f.home_score:
                        winner_club_id = away_club_id

            # 4. Upsert Match
            match_stmt = select(Match).where(
                Match.provider == provider,
                Match.provider_fixture_id == f.provider_fixture_id,
            )
            existing_match = (await self._session.execute(match_stmt)).scalar_one_or_none()

            if existing_match is None:
                fixture_stmt = select(Match).where(
                    Match.competition_season_id == comp_season_id,
                    Match.home_club_id == home_club_id,
                    Match.away_club_id == away_club_id,
                    Match.date == f.date,
                )
                existing_match = (await self._session.execute(fixture_stmt)).scalar_one_or_none()

            if existing_match is not None:
                existing_match.status = f.status
                existing_match.status_detail = f.status_detail
                existing_match.round = f.round
                existing_match.stage = f.stage
                existing_match.venue_name = f.venue_name
                existing_match.venue_city = f.venue_city
                existing_match.referee = f.referee
                existing_match.home_score = f.home_score
                existing_match.away_score = f.away_score
                existing_match.halftime_home_score = f.score.halftime.home
                existing_match.halftime_away_score = f.score.halftime.away
                existing_match.fulltime_home_score = f.score.fulltime.home
                existing_match.fulltime_away_score = f.score.fulltime.away
                existing_match.extratime_home_score = f.score.extratime.home
                existing_match.extratime_away_score = f.score.extratime.away
                existing_match.penalty_home_score = f.score.penalty.home
                existing_match.penalty_away_score = f.score.penalty.away
                existing_match.winner_club_id = winner_club_id
                if snapshot_id:
                    existing_match.snapshot_id = snapshot_id
                match = existing_match
            else:
                match = Match(
                    provider=provider,
                    provider_fixture_id=f.provider_fixture_id,
                    competition_season_id=comp_season_id,
                    home_club_id=home_club_id,
                    away_club_id=away_club_id,
                    date=f.date,
                    status=f.status,
                    status_detail=f.status_detail,
                    round=f.round,
                    stage=f.stage,
                    venue_name=f.venue_name,
                    venue_city=f.venue_city,
                    referee=f.referee,
                    home_score=f.home_score,
                    away_score=f.away_score,
                    halftime_home_score=f.score.halftime.home,
                    halftime_away_score=f.score.halftime.away,
                    fulltime_home_score=f.score.fulltime.home,
                    fulltime_away_score=f.score.fulltime.away,
                    extratime_home_score=f.score.extratime.home,
                    extratime_away_score=f.score.extratime.away,
                    penalty_home_score=f.score.penalty.home,
                    penalty_away_score=f.score.penalty.away,
                    winner_club_id=winner_club_id,
                    snapshot_id=snapshot_id,
                )
                self._session.add(match)
                await self._session.flush()

            # 5. Upsert MatchTeams (Home & Away perspectives)
            home_result: str | None = None
            home_points: int | None = None
            if f.status == "FINISHED":
                if winner_club_id == home_club_id:
                    home_result, home_points = "WIN", 3
                elif winner_club_id == away_club_id:
                    home_result, home_points = "LOSS", 0
                elif f.home_score is not None and f.away_score is not None and f.home_score == f.away_score:
                    home_result, home_points = "DRAW", 1

            away_result: str | None = None
            away_points: int | None = None
            if f.status == "FINISHED":
                if winner_club_id == away_club_id:
                    away_result, away_points = "WIN", 3
                elif winner_club_id == home_club_id:
                    away_result, away_points = "LOSS", 0
                elif f.home_score is not None and f.away_score is not None and f.home_score == f.away_score:
                    away_result, away_points = "DRAW", 1

            stmt_home = select(MatchTeam).where(
                MatchTeam.match_id == match.id,
                MatchTeam.club_id == home_club_id,
            )
            mt_home = (await self._session.execute(stmt_home)).scalar_one_or_none()
            if mt_home is not None:
                mt_home.opponent_club_id = away_club_id
                mt_home.is_home = True
                mt_home.result = home_result
                mt_home.goals_for = f.home_score
                mt_home.goals_against = f.away_score
                mt_home.points = home_points
            else:
                mt_home = MatchTeam(
                    match_id=match.id,
                    club_id=home_club_id,
                    opponent_club_id=away_club_id,
                    is_home=True,
                    result=home_result,
                    goals_for=f.home_score,
                    goals_against=f.away_score,
                    points=home_points,
                )
                self._session.add(mt_home)

            stmt_away = select(MatchTeam).where(
                MatchTeam.match_id == match.id,
                MatchTeam.club_id == away_club_id,
            )
            mt_away = (await self._session.execute(stmt_away)).scalar_one_or_none()
            if mt_away is not None:
                mt_away.opponent_club_id = home_club_id
                mt_away.is_home = False
                mt_away.result = away_result
                mt_away.goals_for = f.away_score
                mt_away.goals_against = f.home_score
                mt_away.points = away_points
            else:
                mt_away = MatchTeam(
                    match_id=match.id,
                    club_id=away_club_id,
                    opponent_club_id=home_club_id,
                    is_home=False,
                    result=away_result,
                    goals_for=f.away_score,
                    goals_against=f.home_score,
                    points=away_points,
                )
                self._session.add(mt_away)

            matches.append(match)

        await self._session.commit()
        return matches

    async def normalize_snapshot(self, snapshot_id: uuid.UUID) -> dict[str, Any]:
        """Normalize a single Bronze DataSnapshot by ID into canonical Silver models."""
        stmt = (
            select(DataSnapshot, IngestionRun)
            .join(IngestionRun, DataSnapshot.ingestion_run_id == IngestionRun.id)
            .where(DataSnapshot.id == snapshot_id)
        )
        res = (await self._session.execute(stmt)).one_or_none()
        if res is None:
            raise ValueError(f"DataSnapshot {snapshot_id} not found")

        snapshot, run = res
        payload_bytes = Path(snapshot.storage_location).read_bytes()
        payload = json.loads(payload_bytes)

        provider_name = "api-football"  # default
        if run.data_source_id:
            await self._session.refresh(run, attribute_names=["data_source"])
            if run.data_source:
                provider_name = run.data_source.name

        endpoint = run.endpoint

        if endpoint == "teams":
            clubs = await self.normalize_teams_payload(provider_name, payload)
            return {"entity": "clubs", "count": len(clubs), "snapshot_id": str(snapshot_id)}
        elif endpoint == "players":
            players = await self.normalize_players_payload(
                provider_name, payload, snapshot_id=snapshot.id
            )
            return {"entity": "players", "count": len(players), "snapshot_id": str(snapshot_id)}
        elif endpoint in ("fixtures", "fixtures_round", "fixture"):
            matches = await self.normalize_fixtures_payload(
                provider_name, payload, snapshot_id=snapshot.id
            )
            return {"entity": "matches", "count": len(matches), "snapshot_id": str(snapshot_id)}
        else:
            return {
                "entity": endpoint,
                "count": 0,
                "message": f"no normalizer mapped for endpoint {endpoint}",
            }
