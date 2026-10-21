from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import (
    Club,
    ClubIdentity,
    Competition,
    CompetitionSeason,
    Match,
    MatchEvent,
    MatchLineup,
    MatchStatistics,
    MatchTeam,
    Player,
    PlayerIdentity,
    PlayerMatchStats,
    PlayerSeasonStats,
    Season,
    Transfer,
)

from app.db.models.provenance import DataSnapshot, IngestionRun
from app.db.models.expansion import (
    CompetitionIdentity,
    FieldProvenance,
    PlayerAlias,
    PlayerClubMembership,
    SourceConflict,
)
from app.identity.names import name_key
from app.normalization.schemas import (
    NormalizedClub,
    NormalizedFixture,
    NormalizedMatchEvent,
    NormalizedMatchLineup,
    NormalizedMatchStatistics,
    NormalizedPlayer,
    NormalizedPlayerMatchStats,
    NormalizedPlayerStats,
)
from app.normalization.transformers import (
    transform_api_football_events,
    transform_api_football_fixtures,
    transform_api_football_leagues,
    transform_api_football_lineups,
    transform_api_football_players,
    transform_api_football_player_statistics,
    transform_api_football_statistics,
    transform_api_football_teams,
)
from app.market.normalizer import (
    assess_transfer_quality,
    transform_api_football_transfers,
    validate_transfer,
)



class NormalizationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_competition(
        self, name: str, country: str, code: str | None = None, comp_type: str = "LEAGUE"
    ) -> Competition:
        stmt = (
            select(Competition)
            .where(Competition.name == name, Competition.country == country)
            .order_by(Competition.created_at.asc(), Competition.id.asc())
            .limit(1)
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
        player, _ = await self.upsert_player_with_status(provider, norm_player)
        return player

    async def _record_field_provenance(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        field_name: str,
        provider: str,
        provider_entity_id: str | None,
        value: Any,
        transformation: str | None = None,
        confidence: float = 1.0,
    ) -> None:
        """Record which provider supplied a canonical field, and what it supplied.

        This is the field-level provenance the platform previously lacked: the record
        level (``data_snapshots``) said where a payload came from, but not which
        provider supplied *this* value.
        """
        if value is None:
            return
        existing = (
            await self._session.execute(
                select(FieldProvenance).where(
                    FieldProvenance.entity_type == entity_type,
                    FieldProvenance.entity_id == entity_id,
                    FieldProvenance.field_name == field_name,
                    FieldProvenance.provider == provider,
                )
            )
        ).scalar_one_or_none()
        payload = {"value": value, "transformation": transformation}
        if existing is None:
            self._session.add(
                FieldProvenance(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_name=field_name,
                    provider=provider,
                    provider_entity_id=provider_entity_id,
                    source_value=payload,
                    transformation=transformation,
                    confidence=confidence,
                )
            )
            return
        existing.source_value = payload
        existing.transformation = transformation
        existing.confidence = confidence
        if provider_entity_id:
            existing.provider_entity_id = provider_entity_id
        existing.retrieved_at = datetime.now(timezone.utc)

    async def _record_field_conflict(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        field_name: str,
        canonical_value: Any,
        provider: str,
        provider_value: Any,
    ) -> None:
        """Record a provider disagreement instead of silently overwriting the value.

        The canonical value is kept (the first authoritative source wins for that field)
        and the conflict is preserved for review.
        """
        if canonical_value is None or provider_value is None:
            return
        if str(canonical_value) == str(provider_value):
            return
        existing = (
            await self._session.execute(
                select(SourceConflict).where(
                    SourceConflict.entity_type == entity_type,
                    SourceConflict.entity_id == entity_id,
                    SourceConflict.field_name == field_name,
                )
            )
        ).scalar_one_or_none()
        candidates = {
            "canonical": canonical_value,
            provider: provider_value,
        }
        if existing is None:
            self._session.add(
                SourceConflict(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field_name=field_name,
                    candidates=candidates,
                    status="OPEN",
                    resolution="canonical value retained; conflict recorded for review",
                )
            )
            return
        merged = dict(existing.candidates or {})
        merged.update(candidates)
        existing.candidates = merged
        existing.status = "OPEN"

    async def upsert_player_with_status(
        self, provider: str, norm_player: NormalizedPlayer
    ) -> tuple[Player, bool]:
        """Upsert one provider player and report whether a canonical row was created.

        The canonical row keeps the provider spelling; every other observed spelling is
        stored as an alias so a later provider can be matched without rewriting the
        original name.
        """
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
            if norm_player.secondary_position and not player.secondary_position:
                player.secondary_position = norm_player.secondary_position
            if norm_player.height_cm and not player.height_cm:
                player.height_cm = norm_player.height_cm
            if norm_player.weight_kg and not player.weight_kg:
                player.weight_kg = norm_player.weight_kg
            if norm_player.date_of_birth and not player.date_of_birth:
                player.date_of_birth = norm_player.date_of_birth
            if norm_player.nationality and not player.nationality:
                player.nationality = norm_player.nationality
            if norm_player.photo_url and not player.photo_url:
                player.photo_url = norm_player.photo_url
            player.name_normalized = name_key(norm_player.name)
            player.last_synced_at = datetime.now(timezone.utc)
            self._apply_completeness(player)
            await self._record_aliases(player, provider, norm_player)
            await self._record_player_provenance(player, provider, norm_player)
            return player, False

        player = Player(
            name=norm_player.name,
            first_name=norm_player.first_name,
            last_name=norm_player.last_name,
            date_of_birth=norm_player.date_of_birth,
            nationality=norm_player.nationality,
            height_cm=norm_player.height_cm,
            weight_kg=norm_player.weight_kg,
            primary_position=norm_player.primary_position,
            secondary_position=norm_player.secondary_position,
            photo_url=norm_player.photo_url,
            display_name=norm_player.name,
            name_normalized=name_key(norm_player.name),
            active_status=norm_player.active_status or "UNKNOWN",
            country_of_birth=norm_player.country_of_birth,
            preferred_foot=norm_player.preferred_foot,
            identity_confidence=1.0,
            last_synced_at=datetime.now(timezone.utc),
        )
        self._session.add(player)
        await self._session.flush()
        self._apply_completeness(player)

        identity = PlayerIdentity(
            player_id=player.id,
            provider=provider,
            provider_player_id=norm_player.provider_id,
            confidence=1.0,
            resolution_method="DIRECT_PROVIDER_ID",
        )
        self._session.add(identity)
        await self._session.flush()
        await self._record_aliases(player, provider, norm_player)
        await self._record_player_provenance(player, provider, norm_player)
        return player, True

    async def _record_player_provenance(
        self, player: Player, provider: str, norm_player: NormalizedPlayer
    ) -> None:
        """Field-level provenance for the canonical player profile."""
        fields = {
            "name": (norm_player.name, "PROVIDER_NAME"),
            "date_of_birth": (norm_player.date_of_birth, "ISO_DATE"),
            "nationality": (norm_player.nationality, None),
            "primary_position": (norm_player.primary_position, "PROVIDER_POSITION"),
            "height_cm": (norm_player.height_cm, "CM"),
            "weight_kg": (norm_player.weight_kg, "KG"),
            "photo_url": (norm_player.photo_url, None),
        }
        for field_name, (value, transformation) in fields.items():
            if value is None:
                continue
            await self._record_field_provenance(
                entity_type="player",
                entity_id=player.id,
                field_name=field_name,
                provider=provider,
                provider_entity_id=norm_player.provider_id,
                value=str(value) if not isinstance(value, (int, float)) else value,
                transformation=transformation,
            )
            canonical_value = getattr(player, field_name, None)
            if canonical_value is not None and str(canonical_value) != str(value):
                await self._record_field_conflict(
                    entity_type="player",
                    entity_id=player.id,
                    field_name=field_name,
                    canonical_value=canonical_value,
                    provider=provider,
                    provider_value=value,
                )

    @staticmethod
    def _apply_completeness(player: Player) -> None:
        """Share of tracked profile fields that are actually known."""
        tracked = (
            player.date_of_birth,
            player.nationality,
            player.primary_position,
            player.height_cm,
            player.weight_kg,
            player.photo_url,
            player.club_id,
            player.first_name if player.last_name else None,
        )
        known = sum(1 for value in tracked if value is not None)
        player.data_completeness = round(known / len(tracked), 4)

    async def _record_aliases(
        self, player: Player, provider: str, norm_player: NormalizedPlayer
    ) -> None:
        """Persist every observed spelling for this player (idempotent)."""
        seen: set[str] = set()
        for alias in norm_player.aliases or []:
            cleaned = str(alias).strip()
            if not cleaned or cleaned == player.name or cleaned in seen:
                continue
            seen.add(cleaned)
            existing = (
                await self._session.execute(
                    select(PlayerAlias).where(
                        PlayerAlias.player_id == player.id,
                        PlayerAlias.provider == provider,
                        PlayerAlias.alias == cleaned,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                self._session.add(
                    PlayerAlias(
                        player_id=player.id,
                        alias=cleaned,
                        alias_type="SOURCE_NAME",
                        provider=provider,
                        provider_entity_id=norm_player.provider_id,
                        confidence=1.0,
                    )
                )
            else:
                existing.last_seen_at = datetime.now(timezone.utc)

    async def upsert_player_season_stats(
        self,
        provider: str,
        norm_stat: NormalizedPlayerStats,
        player_id: uuid.UUID,
        competition_season_id: uuid.UUID,
        snapshot_id: uuid.UUID | None = None,
    ) -> PlayerSeasonStats:
        """Upsert one player-season statistics row for a canonical player.

        This is the public, single-row entry point used when a caller already
        knows the canonical player and competition-season (fixtures, backfills
        and the decision-intelligence integration suite). The bulk ingestion
        path resolves the same rows inside `normalize_players_payload`.
        """
        club_id: uuid.UUID | None = None
        if norm_stat.provider_club_id:
            club_stmt = select(ClubIdentity).where(
                ClubIdentity.provider == provider,
                ClubIdentity.provider_club_id == norm_stat.provider_club_id,
            )
            identity = (await self._session.execute(club_stmt)).scalar_one_or_none()
            if identity is not None:
                club_id = identity.club_id

        stat_stmt = select(PlayerSeasonStats).where(
            PlayerSeasonStats.player_id == player_id,
            PlayerSeasonStats.club_id == club_id,
            PlayerSeasonStats.competition_season_id == competition_season_id,
        )
        existing = (await self._session.execute(stat_stmt)).scalar_one_or_none()

        if existing is not None:
            existing.appearances = norm_stat.appearances
            existing.lineups = norm_stat.lineups
            existing.minutes = norm_stat.minutes
            existing.position = norm_stat.position
            existing.rating = norm_stat.rating
            existing.goals = norm_stat.goals
            existing.assists = norm_stat.assists
            existing.conceded = norm_stat.conceded
            existing.raw_stats = norm_stat.raw_stats
            existing.snapshot_id = snapshot_id
            row = existing
        else:
            row = PlayerSeasonStats(
                player_id=player_id,
                club_id=club_id,
                competition_season_id=competition_season_id,
                snapshot_id=snapshot_id,
                appearances=norm_stat.appearances,
                lineups=norm_stat.lineups,
                minutes=norm_stat.minutes,
                position=norm_stat.position,
                rating=norm_stat.rating,
                goals=norm_stat.goals,
                assists=norm_stat.assists,
                conceded=norm_stat.conceded,
                raw_stats=norm_stat.raw_stats,
            )
            self._session.add(row)
        await self._session.flush()

        # Field-level provenance: which provider supplied each metric.
        for metric, value in (
            ("appearances", norm_stat.appearances),
            ("lineups", norm_stat.lineups),
            ("minutes", norm_stat.minutes),
            ("goals", norm_stat.goals),
            ("assists", norm_stat.assists),
            ("conceded", norm_stat.conceded),
        ):
            if value is None:
                continue
            await self._record_field_provenance(
                entity_type="player_season_stat",
                entity_id=row.id,
                field_name=metric,
                provider=provider,
                provider_entity_id=norm_stat.provider_player_id,
                value=value,
                transformation="PROVIDER_SEASON_STAT",
            )
        return row

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

    async def normalize_competitions_payload(
        self, provider: str, payload: dict[str, Any]
    ) -> list[tuple[Competition, list[Season]]]:
        """Normalize API-Football /leagues into Competition/Season/CompetitionSeason.

        The canonical schema keeps season-level dates and the current flag on
        competition_seasons, not on seasons (seasons are shared across
        competitions and unique by name).
        """
        normalized_results = transform_api_football_leagues(payload)
        results: list[tuple[Competition, list[Season]]] = []

        for norm_comp, norm_seasons in normalized_results:
            comp = await self.get_or_create_competition(
                name=norm_comp.name,
                country=norm_comp.country,
                code=norm_comp.code,
                comp_type=norm_comp.type,
            )

            # Record the provider's competition id against the canonical competition
            # so later season-level payloads resolve to the right league.
            existing_identity = (
                await self._session.execute(
                    select(CompetitionIdentity).where(
                        CompetitionIdentity.provider == provider,
                        CompetitionIdentity.provider_competition_id == norm_comp.provider_id,
                    )
                )
            ).scalar_one_or_none()
            if existing_identity is None:
                self._session.add(
                    CompetitionIdentity(
                        competition_id=comp.id,
                        provider=provider,
                        provider_competition_id=norm_comp.provider_id,
                        confidence=1.0,
                        resolution_method="DIRECT_PROVIDER_ID",
                    )
                )
            else:
                existing_identity.last_seen_at = datetime.now(timezone.utc)
                if existing_identity.competition_id != comp.id:
                    # A placeholder competition was created before the provider
                    # catalogue was known. The real competition replaces it, and the
                    # placeholder is retired when nothing else references it.
                    placeholder = (
                        await self._session.execute(
                            select(Competition).where(Competition.id == existing_identity.competition_id)
                        )
                    ).scalar_one_or_none()
                    if placeholder is not None and placeholder.name.startswith("Provider competition "):
                        await self._retire_placeholder_competition(placeholder)
                    existing_identity.competition_id = comp.id

            seasons: list[Season] = []
            for norm_season in norm_seasons:
                season = await self.get_or_create_season(
                    name=norm_season.name,
                    start_year=norm_season.start_year,
                    end_year=norm_season.end_year,
                )
                comp_season = await self.get_or_create_competition_season(
                    competition_id=comp.id, season_id=season.id
                )
                comp_season.start_date = norm_season.start_date
                comp_season.end_date = norm_season.end_date
                comp_season.is_current = norm_season.is_current
                seasons.append(season)

            results.append((comp, seasons))

        await self._session.commit()
        return results

    async def normalize_players_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
        return_stats: bool = False,
    ) -> list[Player] | tuple[list[Player], dict[str, int]]:
        normalized_players, stats_list = transform_api_football_players(payload)
        players: list[Player] = []
        raw_records = payload.get("response", []) if isinstance(payload, dict) else []
        raw_count = len(raw_records) if isinstance(raw_records, list) else 0
        unique_provider_ids = {np.provider_id for np in normalized_players}
        counters: dict[str, int] = {
            "records_seen": raw_count,
            "records_parsed": len(normalized_players),
            "records_rejected": max(0, raw_count - len(normalized_players)),
            "records_deduplicated": max(0, len(normalized_players) - len(unique_provider_ids)),
            "players_inserted": 0,
            "players_updated": 0,
            "season_stats_inserted": 0,
            "season_stats_updated": 0,
            "memberships_written": 0,
            "records_failed": 0,
        }

        player_map: dict[str, Player] = {}
        for np in normalized_players:
            player, created = await self.upsert_player_with_status(provider, np)
            if created:
                counters["players_inserted"] += 1
            else:
                counters["players_updated"] += 1
            player_map[np.provider_id] = player
            players.append(player)

        # Cache club lookups
        club_lookup: dict[str, uuid.UUID] = {}
        # Cache competition_season lookups
        comp_season_lookup: dict[tuple[str, int], uuid.UUID] = {}
        # Best (most recent, then most played) club evidence per player, used
        # to maintain Player.club_id without inventing a club when none exists.
        best_club: dict[str, tuple[tuple[int, int, int], uuid.UUID]] = {}
        # Time-aware registration rows: (player_id, club_id, competition_season_id,
        # source_record_id, season_year).
        membership_rows: list[tuple[uuid.UUID, uuid.UUID | None, uuid.UUID, str, int]] = []
        latest_season_by_player: dict[uuid.UUID, int] = {}

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

            if club_id is not None:
                evidence = (
                    stat.season_year,
                    stat.appearances or 0,
                    stat.minutes or 0,
                )
                previous = best_club.get(stat.provider_player_id)
                if previous is None or evidence > previous[0]:
                    best_club[stat.provider_player_id] = (evidence, club_id)

            comp_key = (stat.provider_league_id, stat.season_year)
            if comp_key in comp_season_lookup:
                comp_season_id = comp_season_lookup[comp_key]
            else:
                comp = await self.resolve_competition(
                    provider=provider,
                    provider_league_id=stat.provider_league_id,
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
                counters["season_stats_updated"] += 1
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
                counters["season_stats_inserted"] += 1
                # The row needs its generated id before the provenance can point at it.
                await self._session.flush()

            # Field-level provenance for the season statistics: which provider
            # supplied this minute value, for this competition-season.
            stat_row = existing_stat if existing_stat is not None else new_stat
            for metric, value in (
                ("appearances", stat.appearances),
                ("lineups", stat.lineups),
                ("minutes", stat.minutes),
                ("goals", stat.goals),
                ("assists", stat.assists),
                ("conceded", stat.conceded),
            ):
                if value is None:
                    continue
                await self._record_field_provenance(
                    entity_type="player_season_stat",
                    entity_id=stat_row.id,
                    field_name=metric,
                    provider=provider,
                    provider_entity_id=stat.provider_player_id,
                    value=value,
                    transformation="PROVIDER_SEASON_STAT",
                )

            membership_rows.append(
                (
                    player.id,
                    club_id,
                    comp_season_id,
                    f"{provider}:player:{stat.provider_player_id}:team:{stat.provider_club_id or 'none'}"
                    f":league:{stat.provider_league_id}:season:{stat.season_year}",
                    stat.season_year,
                )
            )
            if stat.season_year > latest_season_by_player.get(player.id, -1):
                latest_season_by_player[player.id] = stat.season_year

        # Only fill a missing current club; never overwrite a known association
        # with evidence from an older season.
        for provider_player_id, (_, club_id) in best_club.items():
            player = player_map.get(provider_player_id)
            if player is not None and player.club_id is None:
                player.club_id = club_id

        # Time-aware club memberships: one row per (player, club, competition-season)
        # registration, so a later club never erases an earlier one.
        for player_id, club_id, comp_season_id, source_record_id, season_year in membership_rows:
            existing_membership = (
                await self._session.execute(
                    select(PlayerClubMembership).where(
                        PlayerClubMembership.source_provider == provider,
                        PlayerClubMembership.source_record_id == source_record_id,
                    )
                )
            ).scalar_one_or_none()
            if existing_membership is not None:
                existing_membership.club_id = club_id
                existing_membership.competition_season_id = comp_season_id
                existing_membership.provenance = {"season_year": season_year}
                continue
            self._session.add(
                PlayerClubMembership(
                    player_id=player_id,
                    club_id=club_id,
                    competition_season_id=comp_season_id,
                    membership_type="REGISTRATION",
                    is_current=False,
                    source_provider=provider,
                    source_record_id=source_record_id,
                    provenance={"season_year": season_year},
                )
            )
            counters["memberships_written"] += 1

        # The newest observed season per player marks the current registration.
        for player_id, season_year in latest_season_by_player.items():
            await self._session.execute(
                select(PlayerClubMembership).where(
                    PlayerClubMembership.player_id == player_id,
                    PlayerClubMembership.source_provider == provider,
                )
            )
            memberships = (
                await self._session.execute(
                    select(PlayerClubMembership).where(
                        PlayerClubMembership.player_id == player_id,
                        PlayerClubMembership.source_provider == provider,
                    )
                )
            ).scalars().all()
            for membership in memberships:
                recorded = (membership.provenance or {}).get("season_year")
                membership.is_current = recorded == season_year

        await self._session.commit()
        if return_stats:
            return players, counters
        return players

    async def _retire_placeholder_competition(self, placeholder: Competition) -> None:
        """Delete a placeholder competition that nothing else references.

        A placeholder exists only because the provider catalogue had not been
        ingested for that competition yet. It is removed only when no statistics,
        membership or fixture points at it, so no canonical evidence is lost.
        """
        from app.db.models.canonical import Match, PlayerSeasonStats
        from app.db.models.expansion import PlayerClubMembership

        season_rows = (
            await self._session.execute(
                select(func.count(PlayerSeasonStats.id)).where(
                    PlayerSeasonStats.competition_season_id.in_(
                        select(CompetitionSeason.id).where(
                            CompetitionSeason.competition_id == placeholder.id
                        )
                    )
                )
            )
        ).scalar() or 0
        memberships = (
            await self._session.execute(
                select(func.count(PlayerClubMembership.id)).where(
                    PlayerClubMembership.competition_season_id.in_(
                        select(CompetitionSeason.id).where(
                            CompetitionSeason.competition_id == placeholder.id
                        )
                    )
                )
            )
        ).scalar() or 0
        fixtures = (
            await self._session.execute(
                select(func.count(Match.id)).where(
                    Match.competition_season_id.in_(
                        select(CompetitionSeason.id).where(
                            CompetitionSeason.competition_id == placeholder.id
                        )
                    )
                )
            )
        ).scalar() or 0
        if season_rows or memberships or fixtures:
            return
        await self._session.delete(placeholder)

    async def resolve_competition(
        self, provider: str, provider_league_id: str
    ) -> Competition:
        """Resolve a provider competition id onto a canonical competition.

        The mapping lives in `competition_identities`. When the provider catalogue has
        not been ingested for that competition yet, a clearly-marked placeholder
        competition is created and mapped, so the provider id is never lost and a
        later catalogue ingestion can complete the name and country.
        """
        identity = (
            await self._session.execute(
                select(CompetitionIdentity).where(
                    CompetitionIdentity.provider == provider,
                    CompetitionIdentity.provider_competition_id == provider_league_id,
                )
            )
        ).scalar_one_or_none()
        if identity is not None:
            competition = (
                await self._session.execute(
                    select(Competition).where(Competition.id == identity.competition_id)
                )
            ).scalar_one()
            return competition

        competition = await self.get_or_create_competition(
            name=f"Provider competition {provider_league_id}",
            country="Unknown",
            comp_type="LEAGUE",
        )
        self._session.add(
            CompetitionIdentity(
                competition_id=competition.id,
                provider=provider,
                provider_competition_id=provider_league_id,
                confidence=1.0,
                resolution_method="DIRECT_PROVIDER_ID",
            )
        )
        await self._session.flush()
        return competition

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

    async def _resolve_or_create_player(
        self,
        provider: str,
        provider_player_id: str,
        name: str,
        position: str | None = None,
    ) -> uuid.UUID:
        id_stmt = select(PlayerIdentity).where(
            PlayerIdentity.provider == provider,
            PlayerIdentity.provider_player_id == provider_player_id,
        )
        identity = (await self._session.execute(id_stmt)).scalar_one_or_none()
        if identity is not None:
            return identity.player_id

        player = Player(
            name=name,
            primary_position=position,
        )
        self._session.add(player)
        await self._session.flush()

        new_identity = PlayerIdentity(
            player_id=player.id,
            provider=provider,
            provider_player_id=provider_player_id,
            confidence=1.0,
            resolution_method="DIRECT_PROVIDER_ID",
        )
        self._session.add(new_identity)
        await self._session.flush()
        return player.id

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

    async def normalize_events_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
        default_fixture_id: str | None = None,
    ) -> list[MatchEvent]:
        normalized_events = transform_api_football_events(payload, fixture_id=default_fixture_id)
        events: list[MatchEvent] = []

        match_cache: dict[str, Match | None] = {}
        club_cache: dict[str, uuid.UUID] = {}
        player_cache: dict[str, uuid.UUID] = {}

        for ne in normalized_events:
            if not ne.provider_fixture_id:
                continue

            # 1. Resolve Match
            if ne.provider_fixture_id in match_cache:
                match = match_cache[ne.provider_fixture_id]
            else:
                m_stmt = select(Match).where(
                    Match.provider == provider,
                    Match.provider_fixture_id == ne.provider_fixture_id,
                )
                match = (await self._session.execute(m_stmt)).scalar_one_or_none()
                match_cache[ne.provider_fixture_id] = match

            if match is None:
                continue

            # 2. Resolve Club
            if ne.provider_club_id in club_cache:
                club_id = club_cache[ne.provider_club_id]
            else:
                club_id = await self._resolve_or_create_club(
                    provider=provider,
                    provider_club_id=ne.provider_club_id,
                    name=ne.club_name or "Unknown Club",
                )
                club_cache[ne.provider_club_id] = club_id

            # 3. Resolve Player if present
            player_id: uuid.UUID | None = None
            if ne.provider_player_id:
                if ne.provider_player_id in player_cache:
                    player_id = player_cache[ne.provider_player_id]
                else:
                    player_id = await self._resolve_or_create_player(
                        provider=provider,
                        provider_player_id=ne.provider_player_id,
                        name=ne.player_name or "Unknown Player",
                    )
                    player_cache[ne.provider_player_id] = player_id

            # 4. Resolve Assist Player if present
            assist_player_id: uuid.UUID | None = None
            if ne.provider_assist_id:
                if ne.provider_assist_id in player_cache:
                    assist_player_id = player_cache[ne.provider_assist_id]
                else:
                    assist_player_id = await self._resolve_or_create_player(
                        provider=provider,
                        provider_player_id=ne.provider_assist_id,
                        name=ne.assist_name or "Unknown Player",
                    )
                    player_cache[ne.provider_assist_id] = assist_player_id

            # 5. Upsert MatchEvent by (match_id, event_key)
            ev_stmt = select(MatchEvent).where(
                MatchEvent.match_id == match.id,
                MatchEvent.event_key == ne.event_key,
            )
            existing_event = (await self._session.execute(ev_stmt)).scalar_one_or_none()

            if existing_event is not None:
                existing_event.club_id = club_id
                existing_event.player_id = player_id
                existing_event.assist_player_id = assist_player_id
                existing_event.event_type = ne.event_type
                existing_event.event_detail = ne.event_detail
                existing_event.minute = ne.minute
                existing_event.extra_minute = ne.extra_minute
                existing_event.comments = ne.comments
                existing_event.provider_event_id = ne.provider_event_id
                if snapshot_id:
                    existing_event.snapshot_id = snapshot_id
                events.append(existing_event)
            else:
                new_event = MatchEvent(
                    match_id=match.id,
                    club_id=club_id,
                    player_id=player_id,
                    assist_player_id=assist_player_id,
                    event_type=ne.event_type,
                    event_detail=ne.event_detail,
                    minute=ne.minute,
                    extra_minute=ne.extra_minute,
                    comments=ne.comments,
                    event_key=ne.event_key,
                    provider_event_id=ne.provider_event_id,
                    snapshot_id=snapshot_id,
                )
                self._session.add(new_event)
                events.append(new_event)

        await self._session.commit()
        return events

    async def normalize_lineups_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
        default_fixture_id: str | None = None,
    ) -> list[MatchLineup]:
        normalized_lineups = transform_api_football_lineups(payload, fixture_id=default_fixture_id)
        lineups: list[MatchLineup] = []

        match_cache: dict[str, Match | None] = {}
        club_cache: dict[str, uuid.UUID] = {}
        player_cache: dict[str, uuid.UUID] = {}

        for nl in normalized_lineups:
            if not nl.provider_fixture_id:
                continue

            # 1. Resolve Match
            if nl.provider_fixture_id in match_cache:
                match = match_cache[nl.provider_fixture_id]
            else:
                m_stmt = select(Match).where(
                    Match.provider == provider,
                    Match.provider_fixture_id == nl.provider_fixture_id,
                )
                match = (await self._session.execute(m_stmt)).scalar_one_or_none()
                match_cache[nl.provider_fixture_id] = match

            if match is None:
                continue

            # 2. Resolve Club
            if nl.provider_club_id in club_cache:
                club_id = club_cache[nl.provider_club_id]
            else:
                club_id = await self._resolve_or_create_club(
                    provider=provider,
                    provider_club_id=nl.provider_club_id,
                    name=nl.club_name or "Unknown Club",
                )
                club_cache[nl.provider_club_id] = club_id

            # 3. Resolve Player
            if nl.provider_player_id in player_cache:
                player_id = player_cache[nl.provider_player_id]
            else:
                player_id = await self._resolve_or_create_player(
                    provider=provider,
                    provider_player_id=nl.provider_player_id,
                    name=nl.player_name,
                    position=nl.position,
                )
                player_cache[nl.provider_player_id] = player_id

            # 4. Upsert MatchLineup by (match_id, club_id, player_id)
            lu_stmt = select(MatchLineup).where(
                MatchLineup.match_id == match.id,
                MatchLineup.club_id == club_id,
                MatchLineup.player_id == player_id,
            )
            existing_lineup = (await self._session.execute(lu_stmt)).scalar_one_or_none()

            if existing_lineup is not None:
                existing_lineup.is_starter = nl.is_starter
                existing_lineup.jersey_number = nl.jersey_number
                existing_lineup.position = nl.position
                existing_lineup.formation_position = nl.grid
                existing_lineup.formation = nl.formation
                existing_lineup.is_captain = nl.is_captain
                existing_lineup.coach_name = nl.coach_name
                if snapshot_id:
                    existing_lineup.snapshot_id = snapshot_id
                lineups.append(existing_lineup)
            else:
                new_lineup = MatchLineup(
                    match_id=match.id,
                    club_id=club_id,
                    player_id=player_id,
                    is_starter=nl.is_starter,
                    jersey_number=nl.jersey_number,
                    position=nl.position,
                    formation_position=nl.grid,
                    formation=nl.formation,
                    is_captain=nl.is_captain,
                    coach_name=nl.coach_name,
                    snapshot_id=snapshot_id,
                )
                self._session.add(new_lineup)
                lineups.append(new_lineup)

        await self._session.commit()
        return lineups

    async def normalize_statistics_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
        default_fixture_id: str | None = None,
    ) -> list[MatchStatistics]:
        normalized_stats = transform_api_football_statistics(payload, fixture_id=default_fixture_id)
        statistics_list: list[MatchStatistics] = []

        match_cache: dict[str, Match | None] = {}
        club_cache: dict[str, uuid.UUID] = {}

        for ns in normalized_stats:
            if not ns.provider_fixture_id:
                continue

            # 1. Resolve Match
            if ns.provider_fixture_id in match_cache:
                match = match_cache[ns.provider_fixture_id]
            else:
                m_stmt = select(Match).where(
                    Match.provider == provider,
                    Match.provider_fixture_id == ns.provider_fixture_id,
                )
                match = (await self._session.execute(m_stmt)).scalar_one_or_none()
                match_cache[ns.provider_fixture_id] = match

            if match is None:
                continue

            # 2. Resolve Club
            if ns.provider_club_id in club_cache:
                club_id = club_cache[ns.provider_club_id]
            else:
                club_id = await self._resolve_or_create_club(
                    provider=provider,
                    provider_club_id=ns.provider_club_id,
                    name=ns.club_name or "Unknown Club",
                )
                club_cache[ns.provider_club_id] = club_id

            # 3. Upsert MatchStatistics by (match_id, club_id)
            st_stmt = select(MatchStatistics).where(
                MatchStatistics.match_id == match.id,
                MatchStatistics.club_id == club_id,
            )
            existing_stat = (await self._session.execute(st_stmt)).scalar_one_or_none()

            if existing_stat is not None:
                existing_stat.possession_pct = ns.possession_pct
                existing_stat.shots_total = ns.shots_total
                existing_stat.shots_on_target = ns.shots_on_target
                existing_stat.shots_off_target = ns.shots_off_target
                existing_stat.blocked_shots = ns.blocked_shots
                existing_stat.shots_inside_box = ns.shots_inside_box
                existing_stat.shots_outside_box = ns.shots_outside_box
                existing_stat.fouls = ns.fouls
                existing_stat.corners = ns.corners
                existing_stat.offsides = ns.offsides
                existing_stat.yellow_cards = ns.yellow_cards
                existing_stat.red_cards = ns.red_cards
                existing_stat.saves = ns.saves
                existing_stat.passes_total = ns.passes_total
                existing_stat.passes_accurate = ns.passes_accurate
                existing_stat.pass_accuracy_pct = ns.pass_accuracy_pct
                existing_stat.expected_goals = ns.expected_goals
                existing_stat.free_kicks = ns.free_kicks
                existing_stat.raw_stats = ns.raw_stats
                if snapshot_id:
                    existing_stat.snapshot_id = snapshot_id
                statistics_list.append(existing_stat)
            else:
                new_stat = MatchStatistics(
                    match_id=match.id,
                    club_id=club_id,
                    possession_pct=ns.possession_pct,
                    shots_total=ns.shots_total,
                    shots_on_target=ns.shots_on_target,
                    shots_off_target=ns.shots_off_target,
                    blocked_shots=ns.blocked_shots,
                    shots_inside_box=ns.shots_inside_box,
                    shots_outside_box=ns.shots_outside_box,
                    fouls=ns.fouls,
                    corners=ns.corners,
                    offsides=ns.offsides,
                    yellow_cards=ns.yellow_cards,
                    red_cards=ns.red_cards,
                    saves=ns.saves,
                    passes_total=ns.passes_total,
                    passes_accurate=ns.passes_accurate,
                    pass_accuracy_pct=ns.pass_accuracy_pct,
                    expected_goals=ns.expected_goals,
                    free_kicks=ns.free_kicks,
                    raw_stats=ns.raw_stats,
                    snapshot_id=snapshot_id,
                )
                self._session.add(new_stat)
                statistics_list.append(new_stat)

        await self._session.commit()
        return statistics_list

    async def normalize_player_match_stats_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
        default_fixture_id: str | None = None,
    ) -> list[PlayerMatchStats]:
        normalized_records = transform_api_football_player_statistics(
            payload, fixture_id=default_fixture_id
        )
        stats_results: list[PlayerMatchStats] = []

        match_cache: dict[str, Match | None] = {}
        club_cache: dict[str, uuid.UUID] = {}
        player_cache: dict[str, uuid.UUID] = {}

        for nr in normalized_records:
            if not nr.provider_fixture_id:
                continue

            # 1. Resolve Match
            if nr.provider_fixture_id in match_cache:
                match = match_cache[nr.provider_fixture_id]
            else:
                m_stmt = select(Match).where(
                    Match.provider == provider,
                    Match.provider_fixture_id == nr.provider_fixture_id,
                )
                match = (await self._session.execute(m_stmt)).scalar_one_or_none()
                match_cache[nr.provider_fixture_id] = match

            if match is None:
                continue

            # 2. Resolve Club
            if nr.provider_club_id in club_cache:
                club_id = club_cache[nr.provider_club_id]
            else:
                club_id = await self._resolve_or_create_club(
                    provider=provider,
                    provider_club_id=nr.provider_club_id,
                    name=nr.club_name or "Unknown Club",
                )
                club_cache[nr.provider_club_id] = club_id

            # 3. Resolve Player
            if nr.provider_player_id in player_cache:
                player_id = player_cache[nr.provider_player_id]
            else:
                player_id = await self._resolve_or_create_player(
                    provider=provider,
                    provider_player_id=nr.provider_player_id,
                    name=nr.player_name,
                    position=nr.position,
                )
                player_cache[nr.provider_player_id] = player_id

            # 4. Cross-check with MatchLineup if available
            lu_stmt = select(MatchLineup).where(
                MatchLineup.match_id == match.id,
                MatchLineup.club_id == club_id,
                MatchLineup.player_id == player_id,
            )
            lineup = (await self._session.execute(lu_stmt)).scalar_one_or_none()

            is_starter = nr.is_starter
            is_substitute = nr.is_substitute
            is_captain = nr.is_captain
            formation_position = nr.grid
            position = nr.position
            jersey_number = nr.jersey_number

            if lineup is not None:
                is_starter = lineup.is_starter
                is_substitute = not lineup.is_starter
                if lineup.is_captain:
                    is_captain = True
                if lineup.formation_position:
                    formation_position = lineup.formation_position
                if not position and lineup.position:
                    position = lineup.position
                if jersey_number is None and lineup.jersey_number is not None:
                    jersey_number = lineup.jersey_number

            # 5. Upsert PlayerMatchStats by (match_id, club_id, player_id)
            pms_stmt = select(PlayerMatchStats).where(
                PlayerMatchStats.match_id == match.id,
                PlayerMatchStats.club_id == club_id,
                PlayerMatchStats.player_id == player_id,
            )
            existing_stat = (await self._session.execute(pms_stmt)).scalar_one_or_none()

            if existing_stat is not None:
                existing_stat.provider = provider
                existing_stat.provider_player_id = nr.provider_player_id
                existing_stat.provider_fixture_id = nr.provider_fixture_id
                existing_stat.provider_club_id = nr.provider_club_id
                existing_stat.is_starter = is_starter
                existing_stat.is_substitute = is_substitute
                existing_stat.position = position
                existing_stat.jersey_number = jersey_number
                existing_stat.formation_position = formation_position
                existing_stat.is_captain = is_captain
                existing_stat.minutes = nr.minutes
                existing_stat.rating = nr.rating
                existing_stat.goals = nr.goals
                existing_stat.assists = nr.assists
                existing_stat.shots_total = nr.shots_total
                existing_stat.shots_on_target = nr.shots_on_target
                existing_stat.offsides = nr.offsides
                existing_stat.passes_total = nr.passes_total
                existing_stat.passes_key = nr.passes_key
                existing_stat.pass_accuracy = nr.pass_accuracy
                existing_stat.tackles_total = nr.tackles_total
                existing_stat.blocks = nr.blocks
                existing_stat.interceptions = nr.interceptions
                existing_stat.duels_total = nr.duels_total
                existing_stat.duels_won = nr.duels_won
                existing_stat.dribbles_attempts = nr.dribbles_attempts
                existing_stat.dribbles_success = nr.dribbles_success
                existing_stat.dribbles_past = nr.dribbles_past
                existing_stat.fouls_drawn = nr.fouls_drawn
                existing_stat.fouls_committed = nr.fouls_committed
                existing_stat.yellow_cards = nr.yellow_cards
                existing_stat.red_cards = nr.red_cards
                existing_stat.penalties_won = nr.penalties_won
                existing_stat.penalties_committed = nr.penalties_committed
                existing_stat.penalties_scored = nr.penalties_scored
                existing_stat.penalties_missed = nr.penalties_missed
                existing_stat.penalties_saved = nr.penalties_saved
                existing_stat.saves = nr.saves
                existing_stat.goals_conceded = nr.goals_conceded
                existing_stat.clean_sheet = nr.clean_sheet
                existing_stat.raw_stats = nr.raw_stats
                if snapshot_id:
                    existing_stat.snapshot_id = snapshot_id
                stats_results.append(existing_stat)
            else:
                new_stat = PlayerMatchStats(
                    match_id=match.id,
                    club_id=club_id,
                    player_id=player_id,
                    provider=provider,
                    provider_player_id=nr.provider_player_id,
                    provider_fixture_id=nr.provider_fixture_id,
                    provider_club_id=nr.provider_club_id,
                    is_starter=is_starter,
                    is_substitute=is_substitute,
                    position=position,
                    jersey_number=jersey_number,
                    formation_position=formation_position,
                    is_captain=is_captain,
                    minutes=nr.minutes,
                    rating=nr.rating,
                    goals=nr.goals,
                    assists=nr.assists,
                    shots_total=nr.shots_total,
                    shots_on_target=nr.shots_on_target,
                    offsides=nr.offsides,
                    passes_total=nr.passes_total,
                    passes_key=nr.passes_key,
                    pass_accuracy=nr.pass_accuracy,
                    tackles_total=nr.tackles_total,
                    blocks=nr.blocks,
                    interceptions=nr.interceptions,
                    duels_total=nr.duels_total,
                    duels_won=nr.duels_won,
                    dribbles_attempts=nr.dribbles_attempts,
                    dribbles_success=nr.dribbles_success,
                    dribbles_past=nr.dribbles_past,
                    fouls_drawn=nr.fouls_drawn,
                    fouls_committed=nr.fouls_committed,
                    yellow_cards=nr.yellow_cards,
                    red_cards=nr.red_cards,
                    penalties_won=nr.penalties_won,
                    penalties_committed=nr.penalties_committed,
                    penalties_scored=nr.penalties_scored,
                    penalties_missed=nr.penalties_missed,
                    penalties_saved=nr.penalties_saved,
                    saves=nr.saves,
                    goals_conceded=nr.goals_conceded,
                    clean_sheet=nr.clean_sheet,
                    raw_stats=nr.raw_stats,
                    snapshot_id=snapshot_id,
                )
                self._session.add(new_stat)
                stats_results.append(new_stat)

        await self._session.commit()
        return stats_results

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
        fixture_param = None
        if run.parameters and isinstance(run.parameters, dict):
            fixture_param = run.parameters.get("fixture") or run.parameters.get("id")
        str_fixture_param = str(fixture_param) if fixture_param is not None else None

        if endpoint == "teams":
            clubs = await self.normalize_teams_payload(provider_name, payload)
            return {"entity": "clubs", "count": len(clubs), "snapshot_id": str(snapshot_id)}
        elif endpoint in ("leagues", "competitions"):
            comps = await self.normalize_competitions_payload(provider_name, payload)
            return {
                "entity": "competitions",
                "count": len(comps),
                "snapshot_id": str(snapshot_id),
            }
        elif endpoint == "players":
            players, counters = await self.normalize_players_payload(
                provider_name,
                payload,
                snapshot_id=snapshot.id,
                return_stats=True,
            )
            return {
                "entity": "players",
                "count": len({player.id for player in players}),
                "snapshot_id": str(snapshot_id),
                **counters,
            }
        elif endpoint in ("fixtures", "fixtures_round", "fixture"):
            matches = await self.normalize_fixtures_payload(
                provider_name, payload, snapshot_id=snapshot.id
            )
            return {"entity": "matches", "count": len(matches), "snapshot_id": str(snapshot_id)}
        elif endpoint in ("fixtures/events", "events"):
            events = await self.normalize_events_payload(
                provider_name, payload, snapshot_id=snapshot.id, default_fixture_id=str_fixture_param
            )
            return {"entity": "match_events", "count": len(events), "snapshot_id": str(snapshot_id)}
        elif endpoint in ("fixtures/lineups", "lineups"):
            lineups = await self.normalize_lineups_payload(
                provider_name, payload, snapshot_id=snapshot.id, default_fixture_id=str_fixture_param
            )
            return {"entity": "match_lineups", "count": len(lineups), "snapshot_id": str(snapshot_id)}
        elif endpoint in ("fixtures/statistics", "statistics"):
            stats = await self.normalize_statistics_payload(
                provider_name, payload, snapshot_id=snapshot.id, default_fixture_id=str_fixture_param
            )
            return {"entity": "match_statistics", "count": len(stats), "snapshot_id": str(snapshot_id)}
        elif endpoint in ("fixtures/players", "players_fixture", "fixture_players"):
            player_stats = await self.normalize_player_match_stats_payload(
                provider_name, payload, snapshot_id=snapshot.id, default_fixture_id=str_fixture_param
            )
            return {"entity": "player_match_stats", "count": len(player_stats), "snapshot_id": str(snapshot_id)}
        elif endpoint in ("transfers", "player_transfers"):
            transfers = await self.normalize_transfers_payload(
                provider_name, payload, snapshot_id=snapshot.id, ingestion_run_id=run.id
            )
            return {"entity": "transfers", "count": len(transfers), "snapshot_id": str(snapshot_id)}
        else:
            return {
                "entity": endpoint,
                "count": 0,
                "message": f"no normalizer mapped for endpoint {endpoint}",
            }

    async def normalize_transfers_payload(
        self,
        provider: str,
        payload: dict[str, Any],
        snapshot_id: uuid.UUID | None = None,
        ingestion_run_id: uuid.UUID | None = None,
    ) -> list[Transfer]:
        """Deterministic normalization of provider transfers into canonical Transfer entities (Phase 4.1F)."""
        normalized_transfers = transform_api_football_transfers(payload)
        transfers: list[Transfer] = []

        for nt in normalized_transfers:
            is_valid, _ = validate_transfer(nt)
            if not is_valid:
                continue

            # 1. Resolve player identity
            player_stmt = select(PlayerIdentity).where(
                PlayerIdentity.provider == provider,
                PlayerIdentity.provider_player_id == nt.provider_player_id,
            )
            player_ident = (await self._session.execute(player_stmt)).scalar_one_or_none()
            player = None
            if player_ident:
                player = (await self._session.execute(select(Player).where(Player.id == player_ident.player_id))).scalar_one_or_none()

            if not player:
                name_stmt = select(Player).where(Player.name == nt.player_name)
                player = (await self._session.execute(name_stmt)).scalar_one_or_none()
                if player:
                    self._session.add(PlayerIdentity(
                        player_id=player.id,
                        provider=provider,
                        provider_player_id=nt.provider_player_id,
                        confidence=0.95,
                        resolution_method="NAME_EXACT_MATCH",
                    ))
                    await self._session.flush()

            player_resolved = player is not None
            if not player:
                continue

            # 2. Resolve from_club identity
            from_club = None
            if nt.from_provider_club_id:
                fc_ident = (await self._session.execute(
                    select(ClubIdentity).where(
                        ClubIdentity.provider == provider,
                        ClubIdentity.provider_club_id == nt.from_provider_club_id,
                    )
                )).scalar_one_or_none()
                if fc_ident:
                    from_club = (await self._session.execute(select(Club).where(Club.id == fc_ident.club_id))).scalar_one_or_none()
                elif nt.from_club_name:
                    fc_match = (await self._session.execute(select(Club).where(Club.name == nt.from_club_name))).scalar_one_or_none()
                    if fc_match:
                        from_club = fc_match
                    else:
                        from_club = Club(name=nt.from_club_name, country="Unknown")
                        self._session.add(from_club)
                        await self._session.flush()
                        self._session.add(ClubIdentity(
                            club_id=from_club.id,
                            provider=provider,
                            provider_club_id=nt.from_provider_club_id,
                            confidence=1.0,
                            resolution_method="DIRECT_PROVIDER_ID",
                        ))
                        await self._session.flush()

            # 3. Resolve to_club identity
            to_club = None
            if nt.to_provider_club_id:
                tc_ident = (await self._session.execute(
                    select(ClubIdentity).where(
                        ClubIdentity.provider == provider,
                        ClubIdentity.provider_club_id == nt.to_provider_club_id,
                    )
                )).scalar_one_or_none()
                if tc_ident:
                    to_club = (await self._session.execute(select(Club).where(Club.id == tc_ident.club_id))).scalar_one_or_none()
                elif nt.to_club_name:
                    tc_match = (await self._session.execute(select(Club).where(Club.name == nt.to_club_name))).scalar_one_or_none()
                    if tc_match:
                        to_club = tc_match
                    else:
                        to_club = Club(name=nt.to_club_name, country="Unknown")
                        self._session.add(to_club)
                        await self._session.flush()
                        self._session.add(ClubIdentity(
                            club_id=to_club.id,
                            provider=provider,
                            provider_club_id=nt.to_provider_club_id,
                            confidence=1.0,
                            resolution_method="DIRECT_PROVIDER_ID",
                        ))
                        await self._session.flush()

            from_club_resolved = from_club is not None if nt.from_provider_club_id else True
            to_club_resolved = to_club is not None if nt.to_provider_club_id else True

            # 4. Assess Quality
            quality_status, quality_reasons = assess_transfer_quality(
                nt, player_resolved, from_club_resolved, to_club_resolved
            )

            # 5. Check Idempotency via unique source_record_id
            t_stmt = select(Transfer).where(
                Transfer.source_provider == provider,
                Transfer.source_record_id == nt.source_record_id,
            )
            transfer = (await self._session.execute(t_stmt)).scalar_one_or_none()

            if transfer is not None:
                transfer.player_id = player.id
                transfer.from_club_id = from_club.id if from_club else None
                transfer.to_club_id = to_club.id if to_club else None
                transfer.transfer_date = nt.transfer_date
                transfer.transfer_type = nt.transfer_type
                transfer.fee_value = nt.fee_value
                transfer.fee_currency = nt.fee_currency
                transfer.fee_status = nt.fee_status
                transfer.fee_eur_normalized = nt.fee_eur_normalized
                transfer.is_loan = nt.is_loan
                transfer.is_permanent = nt.is_permanent
                transfer.option_type = nt.option_type
                transfer.data_quality_status = quality_status
                transfer.quality_reasons = quality_reasons
                transfer.raw_data = nt.raw_data
                transfers.append(transfer)
                continue

            transfer = Transfer(
                player_id=player.id,
                from_club_id=from_club.id if from_club else None,
                to_club_id=to_club.id if to_club else None,
                transfer_date=nt.transfer_date,
                transfer_type=nt.transfer_type,
                fee_value=nt.fee_value,
                fee_currency=nt.fee_currency,
                fee_status=nt.fee_status,
                fee_eur_normalized=nt.fee_eur_normalized,
                is_loan=nt.is_loan,
                is_permanent=nt.is_permanent,
                option_type=nt.option_type,
                source_provider=provider,
                source_record_id=nt.source_record_id,
                source_snapshot_id=snapshot_id,
                ingestion_run_id=ingestion_run_id,
                normalization_version="1.0.0",
                data_quality_status=quality_status,
                quality_reasons=quality_reasons,
                raw_data=nt.raw_data,
            )
            self._session.add(transfer)
            transfers.append(transfer)

        await self._session.commit()
        return transfers


