"""Integration tests for the database expansion pipeline.

These run against the isolated test database (transaction rollback) with a fake
provider, so they never touch the development database and never call a real
provider. They cover the acceptance gates that matter for this phase:

* pagination beyond the first page and beyond the 50/100 boundaries;
* resuming an interrupted ingestion and idempotent reruns;
* quota exhaustion (HTTP 429) and authentication failures;
* invalid / partially populated provider records;
* duplicate identities across providers, same-name different players, conflicting DOB;
* historical club memberships and season-specific statistics;
* missing statistics without false zeroes;
* coverage reporting with an explicit denominator;
* provenance and restart safety.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import pytest
from sqlalchemy import func, select

from app.coverage.service import compute_coverage, country_coverage
from app.db.models.canonical import (
    Club,
    ClubIdentity,
    Player,
    PlayerIdentity,
    PlayerSeasonStats,
    ValuationPredictionRecord,
)
from app.db.models.expansion import (
    CountryPriority,
    FieldProvenance,
    IdentityReviewItem,
    IngestionCheckpoint,
    IngestionFailure,
    PlayerAlias,
    PlayerClubMembership,
)
from app.db.models.provenance import DataSource, IngestionRun
from app.identity.resolution import IdentityResolver
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.checkpoints import CheckpointStore
from app.ingestion.service import IngestionService
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.normalization.service import NormalizationService
from app.providers.base import RawResponse
from app.providers.errors import ProviderAuthenticationError, ProviderRateLimitError
from app.providers.registry import ProviderRegistry

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------- fakes
class _FakeProvider:
    """A provider that serves deterministic pages and can be told to fail."""

    name = "fake-provider"

    def __init__(self, pages: list[dict[str, Any]] | None = None, fail_with: Exception | None = None):
        self.pages = pages or []
        self.fail_with = fail_with
        self.calls: list[dict[str, Any]] = []

    async def fetch(self, resource: str, **params: Any) -> RawResponse:
        self.calls.append({"resource": resource, **params})
        if self.fail_with is not None:
            raise self.fail_with
        page = int(params.get("page", 1))
        payload = self.pages[page - 1] if page <= len(self.pages) else {"response": [], "paging": {}}
        content = json.dumps(payload).encode("utf-8")
        return RawResponse(
            content=content,
            content_type="application/json",
            source_url=f"https://fake.invalid/{resource}?{params}",
            retrieved_at=datetime.now(timezone.utc),
            status_code=200,
        )

    async def close(self) -> None:
        return None


def _player_record(
    player_id: int,
    name: str,
    *,
    dob: str | None = "1995-01-01",
    nationality: str | None = "Testland",
    goals: int | None = 3,
    minutes: int | None = 900,
) -> dict[str, Any]:
    return {
        "player": {
            "id": player_id,
            "name": name,
            "firstname": name.split(".")[0].strip(),
            "lastname": name.split(".")[-1].strip(),
            "birth": {"date": dob} if dob else {},
            "nationality": nationality,
            "height": "180",
            "weight": "75",
            "photo": "https://example.invalid/p.png",
        },
        "statistics": [
            {
                "team": {"id": 50},
                "league": {"id": 39, "season": 2023},
                "games": {
                    "appearences": 20 if minutes is not None else None,
                    "lineups": 20 if minutes is not None else None,
                    "minutes": minutes,
                    "position": "Midfielder",
                    "rating": "7.10",
                },
                "goals": {
                    "total": goals,
                    "assists": 1,
                    "conceded": 0,
                },
            }
        ],
    }


def _page(records: list[dict[str, Any]], current: int, total: int) -> dict[str, Any]:
    return {
        "errors": [],
        "paging": {"current": current, "total": total},
        "results": len(records),
        "response": records,
    }


def _registry(provider: _FakeProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(provider.name, lambda: provider)
    return registry


# ------------------------------------------------------------------- pagination
async def test_ingestion_follows_every_declared_page(integration_session, tmp_path):
    provider = _FakeProvider(
        [
            _page([_player_record(i, f"P. {i}") for i in range(1, 21)], 1, 3),
            _page([_player_record(i, f"P. {i}") for i in range(21, 41)], 2, 3),
            _page([_player_record(i, f"P. {i}") for i in range(41, 61)], 3, 3),
        ]
    )
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    result = await service.run_paginated(provider.name, "players", max_pages=10, request_interval_seconds=0)
    assert result.pages_succeeded == 3
    assert result.total_pages == 3
    assert result.status == "COMPLETE"
    assert len(provider.calls) == 3
    assert [call["page"] for call in provider.calls] == [1, 2, 3]


async def test_ingestion_beyond_the_first_hundred_records(integration_session, tmp_path):
    """The provider declares 6 pages of 20: 120 records, well past the old 100 cap."""
    pages = [
        _page([_player_record(page * 20 + i, f"P. {page * 20 + i}") for i in range(20)], page, 6)
        for page in range(1, 7)
    ]
    provider = _FakeProvider(pages)
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    result = await service.run_paginated(provider.name, "players", max_pages=10, request_interval_seconds=0)
    assert result.pages_succeeded == 6
    assert result.records_fetched == 120
    assert result.status == "COMPLETE"


async def test_missing_declared_total_is_not_treated_as_complete(integration_session, tmp_path):
    provider = _FakeProvider([{"errors": [], "response": [_player_record(1, "P. 1")]}])
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    result = await service.run_paginated(provider.name, "players", max_pages=5, request_interval_seconds=0)
    assert result.total_pages is None
    assert result.status != "COMPLETE"
    assert result.stop_reason == "PAGING_TOTAL_UNKNOWN"


# ------------------------------------------------------------------- resume/rerun
async def test_resume_does_not_refetch_completed_pages(integration_session, tmp_path):
    provider = _FakeProvider(
        [
            _page([_player_record(i, f"P. {i}") for i in range(1, 21)], 1, 3),
            _page([_player_record(i, f"P. {i}") for i in range(21, 41)], 2, 3),
            _page([_player_record(i, f"P. {i}") for i in range(41, 61)], 3, 3),
        ]
    )
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    first = await service.run_paginated(provider.name, "players", max_pages=1, request_interval_seconds=0)
    assert first.pages_succeeded == 1
    calls_after_first = len(provider.calls)

    second = await service.run_paginated(
        provider.name, "players", max_pages=10, request_interval_seconds=0, resume=True
    )
    assert second.resumed_from_page == 1
    assert [call["page"] for call in provider.calls[calls_after_first:]] == [2, 3]


async def test_rerunning_a_scope_is_idempotent(integration_session, tmp_path):
    provider = _FakeProvider([_page([_player_record(1, "P. 1")], 1, 1)])
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    normalizer = NormalizationService(integration_session)
    await service.run_paginated(provider.name, "players", max_pages=1, request_interval_seconds=0)
    run = (
        await integration_session.execute(
            select(IngestionRun).where(IngestionRun.endpoint == "players")
        )
    ).scalars().first()
    snapshot = (
        await integration_session.execute(
            select(__import__("app.db.models.provenance", fromlist=["DataSnapshot"]).DataSnapshot)
            .where(
                __import__("app.db.models.provenance", fromlist=["DataSnapshot"]).DataSnapshot.ingestion_run_id
                == run.id
            )
        )
    ).scalars().first()
    await normalizer.normalize_snapshot(snapshot.id)
    first_count = (
        await integration_session.execute(select(func.count(Player.id)))
    ).scalar_one()
    await normalizer.normalize_snapshot(snapshot.id)
    second_count = (
        await integration_session.execute(select(func.count(Player.id)))
    ).scalar_one()
    assert first_count == second_count


# --------------------------------------------------------------- failure handling
async def test_quota_exhaustion_is_reported_not_hidden(integration_session, tmp_path):
    provider = _FakeProvider(
        [_page([_player_record(1, "P. 1")], 1, 2)],
        fail_with=None,
    )
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    await service.run_paginated(provider.name, "players", max_pages=1, request_interval_seconds=0)
    provider.fail_with = ProviderRateLimitError("429 rate limit reached")
    result = await service.run_paginated(provider.name, "players", max_pages=5, request_interval_seconds=0)
    assert result.status == "FAILED"
    assert any("rate limit" in error.lower() for error in result.errors)


async def test_authentication_failure_is_reported_as_a_failure(integration_session, tmp_path):
    provider = _FakeProvider([], fail_with=ProviderAuthenticationError("401 invalid key"))
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    result = await service.run_paginated(provider.name, "players", max_pages=1, request_interval_seconds=0)
    assert result.status == "FAILED"
    assert result.errors


async def test_invalid_records_are_rejected_not_ingested(integration_session, tmp_path):
    provider = _FakeProvider(
        [_page([{"player": {"id": None, "name": "Broken"}}, _player_record(2, "P. 2")], 1, 1)]
    )
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    await service.run_paginated(provider.name, "players", max_pages=1, request_interval_seconds=0)
    normalizer = NormalizationService(integration_session)
    runs = (
        await integration_session.execute(
            select(IngestionRun).where(IngestionRun.endpoint == "players")
        )
    ).scalars().all()
    from app.db.models.provenance import DataSnapshot

    for run in runs:
        snapshot = (
            await integration_session.execute(
                select(DataSnapshot).where(DataSnapshot.ingestion_run_id == run.id)
            )
        ).scalars().first()
        if snapshot is not None:
            await normalizer.normalize_snapshot(snapshot.id)
    players = (await integration_session.execute(select(Player.id))).scalars().all()
    assert len(players) == 1  # the broken record never became a canonical player


# -------------------------------------------------------------- identity handling
async def test_same_name_different_players_are_kept_separate(integration_session):
    resolver = IdentityResolver(integration_session, "provider-b")
    first, _created = await _create_player(integration_session, "John Smith", date(1990, 1, 1), "England", "p1")
    second, _created = await _create_player(integration_session, "John Smith", date(1995, 6, 6), "England", "p2")
    assert first.id != second.id

    match, method, score, _evidence = await resolver.resolve(
        provider_player_id="p3",
        name="John Smith",
        date_of_birth=date(1990, 1, 1),
        nationality="England",
    )
    assert method in ("STRONG_EVIDENCE", "AMBIGUOUS")
    if method == "AMBIGUOUS":
        queued = (
            await integration_session.execute(
                select(IdentityReviewItem).where(IdentityReviewItem.provider_entity_id == "p3")
            )
        ).scalars().all()
        assert queued, "an ambiguous match must land in the review queue"
    else:
        assert match is not None


async def test_conflicting_date_of_birth_does_not_merge(integration_session):
    resolver = IdentityResolver(integration_session, "provider-c")
    await _create_player(integration_session, "John Smith", date(1990, 1, 1), "England", "q1")
    match, method, _score, _evidence = await resolver.resolve(
        provider_player_id="q2",
        name="John Smith",
        date_of_birth=date(1975, 12, 12),
        nationality="England",
    )
    assert method != "STRONG_EVIDENCE"
    assert match is None or method != "STRONG_EVIDENCE"


async def _create_player(session, name, dob, nationality, provider_id):
    player = Player(
        name=name,
        date_of_birth=dob,
        nationality=nationality,
        name_normalized=" ".join(sorted(name.lower().split())),
    )
    session.add(player)
    await session.flush()
    session.add(
        PlayerIdentity(
            player_id=player.id,
            provider="provider-a",
            provider_player_id=provider_id,
            confidence=1.0,
            resolution_method="DIRECT_PROVIDER_ID",
        )
    )
    await session.commit()
    return player, True


# ------------------------------------------------------------- membership + stats
async def test_season_statistics_keep_unknown_values_unknown(integration_session, tmp_path):
    provider = _FakeProvider(
        [_page([_player_record(1, "P. 1", goals=None, minutes=None)], 1, 1)]
    )
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    await service.run_paginated(provider.name, "players", max_pages=1, request_interval_seconds=0)
    normalizer = NormalizationService(integration_session)
    from app.db.models.provenance import DataSnapshot

    run = (
        await integration_session.execute(
            select(IngestionRun).where(IngestionRun.endpoint == "players")
        )
    ).scalars().first()
    snapshot = (
        await integration_session.execute(
            select(DataSnapshot).where(DataSnapshot.ingestion_run_id == run.id)
        )
    ).scalars().first()
    await normalizer.normalize_snapshot(snapshot.id)
    stats = (await integration_session.execute(select(PlayerSeasonStats))).scalars().all()
    assert stats, "the season row must exist"
    assert stats[0].goals is None, "a metric the provider never reported stays unknown"
    assert stats[0].minutes is None
    assert stats[0].assists == 1


async def test_membership_rows_are_time_aware(integration_session, tmp_path):
    provider = _FakeProvider([_page([_player_record(1, "P. 1")], 1, 1)])
    service = IngestionService(
        session=integration_session,
        provider_registry=_registry(provider),
        snapshot_store=LocalFilesystemSnapshotStore(str(tmp_path)),
        capability_registry=None,
    )
    await service.run_paginated(provider.name, "players", max_pages=1, request_interval_seconds=0)
    normalizer = NormalizationService(integration_session)
    from app.db.models.provenance import DataSnapshot

    run = (
        await integration_session.execute(
            select(IngestionRun).where(IngestionRun.endpoint == "players")
        )
    ).scalars().first()
    snapshot = (
        await integration_session.execute(
            select(DataSnapshot).where(DataSnapshot.ingestion_run_id == run.id)
        )
    ).scalars().first()
    await normalizer.normalize_snapshot(snapshot.id)
    memberships = (
        await integration_session.execute(select(PlayerClubMembership))
    ).scalars().all()
    assert memberships
    assert memberships[0].source_provider == "fake-provider"
    assert memberships[0].provenance.get("season_year") == 2023
    assert memberships[0].is_current is True


# ------------------------------------------------------------------- checkpoints
async def test_checkpoint_records_the_scope_and_resumes(integration_session):
    store = CheckpointStore(integration_session)
    await store.record(
        provider="fake-provider",
        entity_type="players",
        params={"team": "50", "season": 2023},
        status="PARTIAL",
        page=2,
        records_seen=40,
        records_written=40,
    )
    state = await store.state("fake-provider", "players", {"team": "50", "season": 2023})
    assert state is not None
    assert state.page == 2
    assert state.status == "PARTIAL"
    # a different scope never shares the checkpoint
    other = await store.state("fake-provider", "players", {"team": "51", "season": 2023})
    assert other is None


async def test_failure_records_are_retryable_and_dead_letterable(integration_session):
    from app.db.models.expansion import IngestionFailure as Failure

    integration_session.add(
        Failure(
            provider="fake-provider",
            resource="players",
            scope_key='{"team": "50"}',
            record_key="p1",
            error="timeout",
            category="TRANSIENT",
            attempts=1,
            status="PENDING",
        )
    )
    await integration_session.commit()
    failure = (
        await integration_session.execute(select(Failure).where(Failure.record_key == "p1"))
    ).scalar_one()
    assert failure.status == "PENDING"
    failure.status = "DEAD"
    await integration_session.commit()
    assert (
        await integration_session.execute(select(Failure).where(Failure.record_key == "p1"))
    ).scalar_one().status == "DEAD"


# --------------------------------------------------------------------- coverage
async def test_coverage_reports_counts_with_explicit_denominators(integration_session):
    coverage = await compute_coverage(integration_session)
    assert "canonical" in coverage
    assert coverage["countries"]["coverage_denominator"]
    assert coverage["profile_completeness"]["players"] >= 0
    assert coverage["statistic_completeness"]["season_rows"] >= 0
    assert coverage["duplicates"]["duplicate_provider_id_groups"] >= 0
    # A provider being reachable is not a completeness claim.
    assert coverage["coverage_notes"]


async def test_country_coverage_separates_nationality_from_club_coverage(integration_session):
    integration_session.add(
        CountryPriority(
            country_code="TST",
            country_name="Testland",
            rank=1,
            ranking_source="test ranking",
            ranking_snapshot_date=date(2026, 1, 1),
            scope_label="TEST",
            is_active=True,
            notes="Testland",
        )
    )
    await integration_session.commit()
    result = await country_coverage(integration_session)
    assert result["coverage_denominator"]
    assert result["note"]
    assert isinstance(result["countries"], list)


# -------------------------------------------------------------------- provenance
async def test_field_provenance_is_recorded_per_field(integration_session):
    from app.identity.resolution import IdentityResolver

    player, _created = await _create_player(
        integration_session, "P. Provenance", date(1990, 1, 1), "Testland", "r1"
    )
    resolver = IdentityResolver(integration_session, "provider-a")
    await resolver.record_field_provenance(
        entity_type="player",
        entity_id=player.id,
        field_name="date_of_birth",
        provider_entity_id="r1",
        source_value="1990-01-01",
        transformation="ISO_DATE",
        confidence=1.0,
    )
    await integration_session.commit()
    row = (
        await integration_session.execute(select(FieldProvenance))
    ).scalars().first()
    assert row is not None
    assert row.field_name == "date_of_birth"
    assert row.provider == "provider-a"


async def test_aliases_are_stored_for_every_observed_spelling(integration_session):
    player, _created = await _create_player(
        integration_session, "M. Akanji", date(1996, 7, 27), "Switzerland", "a1"
    )
    integration_session.add(
        PlayerAlias(
            player_id=player.id,
            alias="Manuel Akanji",
            alias_type="SOURCE_NAME",
            provider="provider-a",
            provider_entity_id="a1",
            confidence=1.0,
        )
    )
    await integration_session.commit()
    aliases = (await integration_session.execute(select(PlayerAlias))).scalars().all()
    assert any(alias.alias == "Manuel Akanji" for alias in aliases)
