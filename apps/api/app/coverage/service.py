"""Coverage service (Phase 7).

Answers the questions a scouting platform has to answer honestly:

* how many canonical players exist, and how many provider records back them;
* how complete the profile and the statistics are;
* which provider competitions and seasons are covered, and which are not;
* which countries are priority countries, and how much of each population is covered;
* what the next ingestion task should be.

Coverage is never expressed as a percentage when the expected population is unknown.
In that case a status is reported instead: ``UNKNOWN_SCOPE``, ``PARTIAL``,
``IN_PROGRESS``, ``COMPLETE_FOR_DECLARED_SCOPE`` or ``BLOCKED``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import (
    Club,
    Competition,
    CompetitionSeason,
    Match,
    MatchEvent,
    MatchLineup,
    MatchStatistics,
    Player,
    PlayerIdentity,
    PlayerMatchStats,
    PlayerSeasonStats,
    Season,
    Transfer,
)
from app.db.models.expansion import (
    CountryPriority,
    IngestionCheckpoint,
    IngestionFailure,
    PlayerAlias,
    PlayerClubMembership,
)
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
from app.identity.names import normalize_name

# Coverage vocabulary.
UNKNOWN_SCOPE = "UNKNOWN_SCOPE"
PARTIAL = "PARTIAL"
IN_PROGRESS = "IN_PROGRESS"
COMPLETE_FOR_DECLARED_SCOPE = "COMPLETE_FOR_DECLARED_SCOPE"
BLOCKED = "BLOCKED"

_PROFILE_FIELDS = (
    "date_of_birth",
    "nationality",
    "primary_position",
    "height_cm",
    "weight_kg",
    "photo_url",
    "club_id",
)


async def _scalar(session: AsyncSession, statement) -> int:
    result = await session.execute(statement)
    return int(result.scalar() or 0)


async def profile_completeness(session: AsyncSession) -> dict[str, Any]:
    """Share of tracked profile fields that are known, per player."""
    total = await _scalar(session, select(func.count(Player.id)))
    if total == 0:
        return {"players": 0, "mean_completeness": None, "by_field": {}}
    mean = await session.execute(select(func.avg(Player.data_completeness)))
    by_field: dict[str, int] = {}
    for field in _PROFILE_FIELDS:
        column = getattr(Player, field)
        by_field[field] = await _scalar(
            session, select(func.count(Player.id)).where(column.isnot(None))
        )
    complete = await _scalar(
        session, select(func.count(Player.id)).where(Player.data_completeness >= 1.0)
    )
    return {
        "players": total,
        "mean_completeness": round(float(mean.scalar() or 0.0), 4),
        "players_fully_complete": complete,
        "by_field": by_field,
    }


async def statistic_completeness(session: AsyncSession) -> dict[str, Any]:
    """Season-statistic completeness: measured zero vs. not reported."""
    total = await _scalar(session, select(func.count(PlayerSeasonStats.id)))
    if total == 0:
        return {"season_rows": 0, "minutes_known": 0, "minutes_unknown": 0, "measured_zero_minutes": 0}
    minutes_known = await _scalar(
        session, select(func.count(PlayerSeasonStats.id)).where(PlayerSeasonStats.minutes.isnot(None))
    )
    measured_zero = await _scalar(
        session,
        select(func.count(PlayerSeasonStats.id)).where(
            PlayerSeasonStats.minutes.isnot(None), PlayerSeasonStats.minutes == 0
        ),
    )
    goals_known = await _scalar(
        session, select(func.count(PlayerSeasonStats.id)).where(PlayerSeasonStats.goals.isnot(None))
    )
    return {
        "season_rows": total,
        "minutes_known": minutes_known,
        "minutes_unknown": total - minutes_known,
        "measured_zero_minutes": measured_zero,
        "goals_known": goals_known,
        "goals_unknown": total - goals_known,
    }


async def provider_coverage(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(
                DataSource.name,
                func.count(PlayerIdentity.id),
                func.count(func.distinct(PlayerIdentity.player_id)),
            )
            .select_from(DataSource)
            .outerjoin(
                PlayerIdentity,
                (PlayerIdentity.provider == DataSource.name) & (PlayerIdentity.id.isnot(None)),
            )
            .group_by(DataSource.name)
            .order_by(DataSource.name)
        )
    ).all()
    result: list[dict[str, Any]] = []
    for name, identity_rows, distinct_players in rows:
        runs = (
            await session.execute(
                select(IngestionRun)
                .join(DataSource, DataSource.id == IngestionRun.data_source_id)
                .where(DataSource.name == name)
                .order_by(IngestionRun.finished_at.desc())
            )
        ).scalars().all()
        last_success = next(
            (
                run.finished_at
                for run in runs
                if str(getattr(run.status, "value", run.status)) == "SUCCESS" and run.finished_at
            ),
            None,
        )
        checkpoints = (
            await session.execute(
                select(IngestionCheckpoint)
                .where(IngestionCheckpoint.provider == name)
                .order_by(IngestionCheckpoint.id)
            )
        ).scalars().all()
        status_counts: dict[str, int] = {}
        for checkpoint in checkpoints:
            status_counts[checkpoint.status] = status_counts.get(checkpoint.status, 0) + 1
        result.append(
            {
                "provider": name,
                "identity_rows": int(identity_rows or 0),
                "unique_players": int(distinct_players or 0),
                "runs": len(runs),
                "last_success_at": last_success.isoformat() if last_success else None,
                "checkpoints": len(checkpoints),
                "checkpoint_status": status_counts,
                "enabled": True,
            }
        )
    return result


async def competition_coverage(session: AsyncSession) -> list[dict[str, Any]]:
    """Per competition-season coverage of the player universe."""
    rows = (
        await session.execute(
            select(
                Competition.id,
                Competition.name,
                Competition.country,
                Season.name,
                func.count(func.distinct(PlayerSeasonStats.player_id)),
                func.count(PlayerSeasonStats.id),
                func.count(func.distinct(PlayerSeasonStats.club_id)),
            )
            .select_from(PlayerSeasonStats)
            .join(CompetitionSeason, CompetitionSeason.id == PlayerSeasonStats.competition_season_id)
            .join(Competition, Competition.id == CompetitionSeason.competition_id)
            .join(Season, Season.id == CompetitionSeason.season_id)
            .group_by(Competition.id, Competition.name, Competition.country, Season.name)
            .order_by(Competition.name, Season.name)
        )
    ).all()
    return [
        {
            "competition": name,
            "country": country,
            "season": season,
            "players": int(players or 0),
            "player_season_rows": int(rows_count or 0),
            "clubs": int(clubs or 0),
            "status": IN_PROGRESS if (rows_count or 0) else UNKNOWN_SCOPE,
        }
        for _cid, name, country, season, players, rows_count, clubs in rows
    ]


async def country_coverage(session: AsyncSession) -> dict[str, Any]:
    """Two separate measures, never conflated.

    * ``national_team_countries`` - the priority countries from the dated snapshot.
    * ``club_based_players_by_nationality`` - players of those nationalities found
      through club competitions, which can only ever be a sample of the population.
    """
    priorities = (
        await session.execute(
            select(CountryPriority).where(CountryPriority.is_active.is_(True)).order_by(CountryPriority.rank)
        )
    ).scalars().all()
    total_players = await _scalar(session, select(func.count(Player.id)))

    entries: list[dict[str, Any]] = []
    covered = 0
    for priority in priorities:
        spellings = {normalize_name(priority.country_name)}
        if priority.notes:
            spellings.add(normalize_name(priority.notes))
        count = 0
        for player in (
            await session.execute(select(Player.nationality).where(Player.nationality.isnot(None)))
        ).scalars().all():
            if normalize_name(player) in spellings:
                count += 1
        if count:
            covered += 1
        entries.append(
            {
                "rank": priority.rank,
                "country_code": priority.country_code,
                "country": priority.country_name,
                "ranking_source": priority.ranking_source,
                "ranking_snapshot_date": priority.ranking_snapshot_date.isoformat(),
                "players_with_nationality": count,
                "coverage_status": PARTIAL if count else UNKNOWN_SCOPE,
                "denominator": "players ingested in the canonical index with this nationality",
            }
        )

    unknown_nationality = await _scalar(
        session, select(func.count(Player.id)).where(Player.nationality.is_(None))
    )
    return {
        "ranking_scope": priorities[0].scope_label if priorities else None,
        "ranking_source": priorities[0].ranking_source if priorities else None,
        "ranking_snapshot_date": priorities[0].ranking_snapshot_date.isoformat() if priorities else None,
        "selected_countries": len(priorities),
        "countries_with_covered_players": covered,
        "country_coverage_pct": round(covered / len(priorities) * 100, 2) if priorities else None,
        "coverage_denominator": "selected priority countries with at least one ingested player",
        "players_without_nationality": unknown_nationality,
        "canonical_players": total_players,
        "countries": entries,
        "note": (
            "Nationality coverage counts players already in the canonical index. It is not a "
            "claim about the total population of footballers from those countries."
        ),
    }


async def ingestion_state(session: AsyncSession) -> dict[str, Any]:
    runs = (
        await session.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(50))
    ).scalars().all()
    by_status: dict[str, int] = {}
    for run in runs:
        key = str(getattr(run.status, "value", run.status))
        by_status[key] = by_status.get(key, 0) + 1
    checkpoints = (
        await session.execute(select(IngestionCheckpoint).order_by(IngestionCheckpoint.id))
    ).scalars().all()
    checkpoint_status: dict[str, int] = {}
    for checkpoint in checkpoints:
        checkpoint_status[checkpoint.status] = checkpoint_status.get(checkpoint.status, 0) + 1
    failures = (
        await session.execute(select(IngestionFailure).order_by(IngestionFailure.id))
    ).scalars().all()
    failure_status: dict[str, int] = {}
    for failure in failures:
        failure_status[failure.status] = failure_status.get(failure.status, 0) + 1
    last_success = await session.execute(
        select(func.max(IngestionRun.finished_at)).where(IngestionRun.status == "SUCCESS")
    )
    last_success_at = last_success.scalar()
    return {
        "recent_runs_by_status": by_status,
        "last_successful_ingestion_at": (
            last_success_at.isoformat() if last_success_at else None
        ),
        "checkpoints_by_status": checkpoint_status,
        "failures_by_status": failure_status,
        "checkpoints": [checkpoint.scope_key for checkpoint in checkpoints][:50],
    }


async def duplicate_state(session: AsyncSession) -> dict[str, Any]:
    duplicate_groups = await session.execute(
        select(func.count())
        .select_from(
            select(PlayerIdentity.provider, PlayerIdentity.provider_player_id)
            .group_by(PlayerIdentity.provider, PlayerIdentity.provider_player_id)
            .having(func.count() > 1)
            .subquery()
        )
    )
    players_without_identity = await _scalar(
        session,
        select(func.count(Player.id)).where(
            ~select(PlayerIdentity.id).where(PlayerIdentity.player_id == Player.id).exists()
        ),
    )
    players_with_multiple_identities = await _scalar(
        session,
        select(func.count(func.distinct(PlayerIdentity.player_id))).where(
            PlayerIdentity.player_id.isnot(None)
        ),
    )
    return {
        "duplicate_provider_id_groups": int(duplicate_groups.scalar() or 0),
        "players_without_identity": players_without_identity,
        "distinct_players_with_identities": players_with_multiple_identities,
    }


async def provenance_summary(session: AsyncSession) -> dict[str, Any]:
    """Field-level provenance and unresolved conflicts."""
    from app.db.models.expansion import FieldProvenance, SourceConflict

    total = await _scalar(session, select(func.count(FieldProvenance.id)))
    by_entity: dict[str, int] = {}
    rows = (
        await session.execute(
            select(FieldProvenance.entity_type, func.count(FieldProvenance.id)).group_by(
                FieldProvenance.entity_type
            )
        )
    ).all()
    for entity_type, count in rows:
        by_entity[entity_type] = int(count)
    by_provider: dict[str, int] = {}
    provider_rows = (
        await session.execute(
            select(FieldProvenance.provider, func.count(FieldProvenance.id)).group_by(
                FieldProvenance.provider
            )
        )
    ).all()
    for provider, count in provider_rows:
        by_provider[provider] = int(count)
    conflicts = await _scalar(session, select(func.count(SourceConflict.id)))
    open_conflicts = await _scalar(
        session, select(func.count(SourceConflict.id)).where(SourceConflict.status == "OPEN")
    )
    return {
        "field_provenance_rows": total,
        "by_entity_type": by_entity,
        "by_provider": by_provider,
        "conflicts": conflicts,
        "open_conflicts": open_conflicts,
    }


async def entity_provenance(
    session: AsyncSession, entity_type: str, entity_id: str
) -> dict[str, Any]:
    """The provenance of one entity's fields, and its unresolved conflicts."""
    import uuid as uuid_module

    from app.db.models.expansion import FieldProvenance, SourceConflict

    try:
        identifier = uuid_module.UUID(str(entity_id))
    except (TypeError, ValueError):
        return {"entity_type": entity_type, "entity_id": str(entity_id), "fields": [], "conflicts": []}
    rows = (
        await session.execute(
            select(FieldProvenance)
            .where(
                FieldProvenance.entity_type == entity_type,
                FieldProvenance.entity_id == identifier,
            )
            .order_by(FieldProvenance.field_name)
        )
    ).scalars().all()
    conflicts = (
        await session.execute(
            select(SourceConflict).where(
                SourceConflict.entity_type == entity_type,
                SourceConflict.entity_id == identifier,
            )
        )
    ).scalars().all()
    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "fields": [
            {
                "field": row.field_name,
                "provider": row.provider,
                "provider_entity_id": row.provider_entity_id,
                "value": row.source_value,
                "transformation": row.transformation,
                "confidence": row.confidence,
                "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None,
            }
            for row in rows
        ],
        "conflicts": [
            {
                "field": row.field_name,
                "candidates": row.candidates,
                "status": row.status,
                "resolution": row.resolution,
            }
            for row in conflicts
        ],
    }


async def next_recommended_tasks(session: AsyncSession) -> list[dict[str, Any]]:
    """The next ingestion work, derived from the checkpoints that are not complete."""
    checkpoints = (
        await session.execute(
            select(IngestionCheckpoint).where(
                IngestionCheckpoint.status.notin_([COMPLETE_FOR_DECLARED_SCOPE])
            )
        )
    ).scalars().all()
    tasks: list[dict[str, Any]] = []
    for checkpoint in checkpoints[:20]:
        tasks.append(
            {
                "provider": checkpoint.provider,
                "entity_type": checkpoint.entity_type,
                "scope_key": checkpoint.scope_key,
                "status": checkpoint.status,
                "last_error": checkpoint.last_error,
                "command": (
                    f"python tools/ingest_expansion.py run --competition {checkpoint.competition or 'premier-league'} "
                    f"--season {checkpoint.season or '2023'} --resume"
                ),
            }
        )
    return tasks


async def compute_coverage(session: AsyncSession) -> dict[str, Any]:
    """The full coverage view."""
    canonical_players = await _scalar(session, select(func.count(Player.id)))
    provider_records = await _scalar(session, select(func.count(PlayerIdentity.id)))
    clubs = await _scalar(session, select(func.count(Club.id)))
    national_teams = await _scalar(
        session, select(func.count(Club.id)).where(Club.country.in_(["National team"]))
    )
    competitions = await _scalar(session, select(func.count(Competition.id)))
    seasons = await _scalar(session, select(func.count(Season.id)))
    competition_seasons = await _scalar(session, select(func.count(CompetitionSeason.id)))
    fixtures = await _scalar(session, select(func.count(Match.id)))
    lineups = await _scalar(session, select(func.count(MatchLineup.id)))
    match_events = await _scalar(session, select(func.count(MatchEvent.id)))
    match_statistics = await _scalar(session, select(func.count(MatchStatistics.id)))
    player_match_stats = await _scalar(session, select(func.count(PlayerMatchStats.id)))
    player_season_stats = await _scalar(session, select(func.count(PlayerSeasonStats.id)))
    transfers = await _scalar(session, select(func.count(Transfer.id)))
    aliases = await _scalar(session, select(func.count(PlayerAlias.id)))
    memberships = await _scalar(session, select(func.count(PlayerClubMembership.id)))
    snapshots = await _scalar(session, select(func.count(DataSnapshot.id)))

    nationality_rows = (
        await session.execute(
            select(Player.nationality, func.count(Player.id))
            .where(Player.nationality.isnot(None))
            .group_by(Player.nationality)
            .order_by(func.count(Player.id).desc())
        )
    ).all()
    position_rows = (
        await session.execute(
            select(Player.primary_position, func.count(Player.id))
            .where(Player.primary_position.isnot(None))
            .group_by(Player.primary_position)
            .order_by(func.count(Player.id).desc())
        )
    ).all()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical": {
            "players": canonical_players,
            "provider_player_records": provider_records,
            "clubs": clubs,
            "national_teams": national_teams,
            "competitions": competitions,
            "seasons": seasons,
            "competition_seasons": competition_seasons,
            "fixtures": fixtures,
            "match_lineups": lineups,
            "match_events": match_events,
            "match_statistics": match_statistics,
            "player_match_stats": player_match_stats,
            "player_season_stats": player_season_stats,
            "transfers": transfers,
            "player_aliases": aliases,
            "player_club_memberships": memberships,
            "bronze_snapshots": snapshots,
        },
        "profile_completeness": await profile_completeness(session),
        "statistic_completeness": await statistic_completeness(session),
        "providers": await provider_coverage(session),
        "competitions": await competition_coverage(session),
        "countries": await country_coverage(session),
        "ingestion": await ingestion_state(session),
        "duplicates": await duplicate_state(session),
        "provenance": await provenance_summary(session),
        "players_by_nationality": [
            {"nationality": nationality, "players": count} for nationality, count in nationality_rows
        ],
        "players_by_position": [
            {"position": position, "players": count} for position, count in position_rows
        ],
        "next_recommended_tasks": await next_recommended_tasks(session),
        "coverage_notes": [
            "A provider being reachable is not evidence that the database is complete.",
            "Coverage percentages are only reported where the denominator is defined; otherwise a status is returned.",
        ],
    }
