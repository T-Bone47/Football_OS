"""Paginated API-Football ingestion CLI.

Fetches every page the provider declares for a scoped endpoint (for example
Premier League 2023 players), stores one immutable Bronze snapshot per page,
and normalizes each page into canonical rows unless `--no-normalize` is given.

Usage (from the repository root):

    python tools/ingest_api_football.py players --league 39 --season 2023 --resume
    python tools/ingest_api_football.py players --league 39 --season 2023 \
        --max-pages 5 --no-normalize

Exit codes: 0 COMPLETE, 2 PARTIAL/UNKNOWN, 3 FAILED, 4 configuration error.
Never prints credentials.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models.canonical import PlayerIdentity
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun
from app.ingestion.capability_registry import CapabilityRegistry
from app.ingestion.service import IngestionService
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore
from app.normalization.service import NormalizationService
from app.providers.registry import default_registry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "resource", choices=["players", "teams", "fixtures", "leagues", "transfers"]
    )
    parser.add_argument("--league", type=int)
    parser.add_argument("--season", type=int)
    parser.add_argument("--date")
    parser.add_argument(
        "--player",
        type=int,
        action="append",
        default=None,
        help="provider player id to fetch (repeatable; transfers only)",
    )
    parser.add_argument(
        "--player-ids",
        default=None,
        help="comma-separated provider player ids (transfers only)",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="fetch transfers for every canonical player with an api-football identity",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=None,
        help="seconds between per-player transfer requests (default: 6.2)",
    )
    parser.add_argument(
        "--rate-limit-backoff",
        type=float,
        default=65.0,
        help="seconds to wait once when the provider reports a rate limit (default: 65)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="maximum number of player scopes to request in this invocation",
    )
    parser.add_argument("--page", type=int, default=1, help="first page (default 1)")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument(
        "--page-delay",
        type=float,
        default=None,
        help="seconds between page requests (default: provider-safe 6.1)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip pages already completed for the same non-page parameters",
    )
    parser.add_argument(
        "--no-normalize", action="store_true", help="store Bronze only"
    )
    parser.add_argument(
        "--renormalize",
        action="store_true",
        help=(
            "after ingestion, normalize the latest snapshot of every completed "
            "page in the same scope (idempotent; use to backfill fixes)"
        ),
    )
    parser.add_argument(
        "--normalize-only",
        action="store_true",
        help="skip fetching; normalize every completed page in the same scope",
    )
    return parser


async def _snapshots_for(session, run_id):
    rows = await session.execute(
        select(DataSnapshot)
        .where(DataSnapshot.ingestion_run_id == run_id)
        .order_by(DataSnapshot.retrieved_at)
    )
    return rows.scalars().all()


def _run_status(run) -> str:
    return str(getattr(run.status, "value", run.status))


def _is_rate_limited(run) -> bool:
    error = (run.error or "").lower()
    return "ratelimit" in error or "rate limit" in error or "too many requests" in error


async def _player_ids_for_transfers(session, args: argparse.Namespace) -> list[int]:
    """Resolve the provider player ids this invocation should request."""
    ids: list[int] = []

    def _add(value: str | int | None) -> None:
        if value is None:
            return
        try:
            candidate = int(str(value).strip())
        except (TypeError, ValueError):
            return
        if candidate > 0 and candidate not in ids:
            ids.append(candidate)

    for value in args.player or []:
        _add(value)
    for value in (args.player_ids or "").split(","):
        _add(value)

    if args.from_db:
        rows = (
            await session.execute(
                select(PlayerIdentity.provider_player_id).where(
                    PlayerIdentity.provider == "api-football"
                )
            )
        ).scalars().all()
        for value in sorted({int(v) for v in rows if str(v).isdigit()}):
            _add(value)

    limit = args.limit
    if limit is not None:
        ids = ids[: max(0, limit)]
    return ids


async def _run_transfers(args: argparse.Namespace, settings) -> int:
    """Per-player transfer ingestion (API-Football /transfers).

    The endpoint does not accept league/season/page; it is scoped by player
    or team. One run and one immutable snapshot per player keeps the job
    resumable and attributable. The provider's free plan allows 10 requests
    per minute and 100 per day, so the loop is paced and stops — rather than
    silently retrying forever — when the provider reports a quota failure.
    """
    interval = args.request_delay if args.request_delay is not None else 6.2
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    summary: dict = {
        "provider": "api-football",
        "resource": "transfers",
        "requested_players": 0,
        "completed_players": 0,
        "failed_players": 0,
        "records_normalized": 0,
        "normalization_failures": [],
        "players": [],
        "status": "NOT_STARTED",
        "stop_reason": None,
    }
    try:
        async with Session() as session:
            player_ids = await _player_ids_for_transfers(session, args)
            summary["requested_players"] = len(player_ids)
            if not player_ids:
                summary["status"] = "FAILED"
                summary["stop_reason"] = "NO_PLAYER_SCOPE"
                print(json.dumps(summary, indent=2))
                return 4

            service = IngestionService(
                session=session,
                provider_registry=default_registry,
                snapshot_store=LocalFilesystemSnapshotStore(
                    settings.snapshot_storage_path
                ),
                capability_registry=CapabilityRegistry(session),
            )
            normalizer = NormalizationService(session)
            stop_reason = None

            for index, player_id in enumerate(player_ids):
                if index > 0 or summary["players"]:
                    await asyncio.sleep(interval)

                run = await service.run("api-football", "transfers", player=player_id)
                status = _run_status(run)
                retried = False
                if status == "FAILED" and _is_rate_limited(run):
                    await asyncio.sleep(args.rate_limit_backoff)
                    run = await service.run(
                        "api-football", "transfers", player=player_id
                    )
                    status = _run_status(run)
                    retried = True

                detail = {
                    "player_id": player_id,
                    "run_id": str(run.id),
                    "status": status,
                    "retried_after_rate_limit": retried,
                    "provider_records": run.record_count,
                    "error": run.error,
                }

                if status in ("SUCCESS", "PARTIAL") and not args.no_normalize:
                    normalized = 0
                    for snapshot in await _snapshots_for(session, run.id):
                        try:
                            outcome = await normalizer.normalize_snapshot(snapshot.id)
                        except Exception as exc:  # noqa: BLE001 - report, do not hide
                            summary["normalization_failures"].append(
                                {
                                    "player_id": player_id,
                                    "snapshot_id": str(snapshot.id),
                                    "error": f"{type(exc).__name__}: {exc}",
                                }
                            )
                            continue
                        if isinstance(outcome, dict) and outcome.get("entity") == "transfers":
                            normalized += int(outcome.get("count") or 0)
                        detail["normalization"] = outcome
                    summary["records_normalized"] += normalized
                    summary["completed_players"] += 1
                    detail["normalized_transfers"] = normalized
                else:
                    summary["failed_players"] += 1
                    if _is_rate_limited(run):
                        stop_reason = "PROVIDER_RATE_LIMIT"

                summary["players"].append(detail)
                if stop_reason:
                    break

            attempted = summary["completed_players"] + summary["failed_players"]
            summary["stop_reason"] = stop_reason or (
                "ALL_REQUESTED_PLAYERS_ATTEMPTED" if attempted == len(player_ids) else "STOPPED"
            )
            if stop_reason == "PROVIDER_RATE_LIMIT":
                summary["status"] = "PARTIAL"
            elif summary["completed_players"] == 0:
                summary["status"] = "FAILED"
            elif summary["failed_players"] == 0:
                summary["status"] = "COMPLETE"
            else:
                summary["status"] = "PARTIAL"
    finally:
        await engine.dispose()

    print(json.dumps(summary, indent=2, default=str))
    status = summary.get("status")
    return 0 if status == "COMPLETE" else 3 if status == "FAILED" else 2


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.normalize_only and args.no_normalize:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error": "--normalize-only conflicts with --no-normalize",
                }
            )
        )
        return 4
    if not args.normalize_only and not settings.api_football_key:
        print(json.dumps({"status": "FAILED", "error": "API_FOOTBALL_KEY is not configured"}))
        return 4

    if args.resource == "transfers":
        if args.normalize_only:
            print(
                json.dumps(
                    {
                        "status": "FAILED",
                        "error": "--normalize-only is not supported for transfers; normalization is part of the per-player run",
                    }
                )
            )
            return 4
        return await _run_transfers(args, settings)

    params: dict = {}
    if args.league is not None:
        params["league"] = args.league
    if args.season is not None:
        params["season"] = args.season
    if args.date is not None:
        params["date"] = args.date

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    summary: dict = {
        "provider": "api-football",
        "resource": args.resource,
        "parameters": params,
        "normalization": {"enabled": not args.no_normalize, "pages": []},
    }
    try:
        async with Session() as session:
            service = IngestionService(
                session=session,
                provider_registry=default_registry,
                snapshot_store=LocalFilesystemSnapshotStore(
                    settings.snapshot_storage_path
                ),
                capability_registry=CapabilityRegistry(session),
            )
            result = None
            if not args.normalize_only:
                result = await service.run_paginated(
                    "api-football",
                    args.resource,
                    start_page=args.page,
                    max_pages=args.max_pages,
                    request_interval_seconds=args.page_delay,
                    resume=args.resume,
                    **params,
                )
                summary["ingestion"] = result.to_dict()
            else:
                summary["ingestion"] = {
                    "status": "SKIPPED",
                    "stop_reason": "NORMALIZE_ONLY",
                }

            if not args.no_normalize:
                normalizer = NormalizationService(session)
                runs_to_normalize = list(result.runs) if result is not None else []
                if args.renormalize or args.normalize_only:
                    rows = (
                        await session.execute(
                            select(IngestionRun)
                            .join(
                                DataSource,
                                DataSource.id == IngestionRun.data_source_id,
                            )
                            .where(
                                DataSource.name == "api-football",
                                IngestionRun.endpoint == args.resource,
                            )
                            .order_by(IngestionRun.started_at.asc())
                        )
                    ).scalars().all()
                    latest_by_page: dict[int, IngestionRun] = {}
                    for run in rows:
                        parameters = dict(run.parameters or {})
                        page = parameters.get("page")
                        status = str(getattr(run.status, "value", run.status))
                        if (
                            isinstance(page, int)
                            and status in ("SUCCESS", "PARTIAL")
                            and IngestionService._same_scope(parameters, params)
                        ):
                            latest_by_page[page] = run
                    runs_to_normalize = [
                        latest_by_page[page] for page in sorted(latest_by_page)
                    ]

                for run in runs_to_normalize:
                    for snapshot in await _snapshots_for(session, run.id):
                        try:
                            outcome = await normalizer.normalize_snapshot(snapshot.id)
                        except Exception as exc:  # noqa: BLE001 - report, do not hide
                            summary["normalization"]["pages"].append(
                                {
                                    "page": (run.parameters or {}).get("page"),
                                    "snapshot_id": str(snapshot.id),
                                    "status": "FAILED",
                                    "error": f"{type(exc).__name__}: {exc}",
                                }
                            )
                        else:
                            summary["normalization"]["pages"].append(
                                {
                                    "page": (run.parameters or {}).get("page"),
                                    "snapshot_id": str(snapshot.id),
                                    "status": "OK",
                                    "result": outcome,
                                }
                            )
    finally:
        await engine.dispose()

    print(json.dumps(summary, indent=2, default=str))
    if args.normalize_only:
        failed = any(
            page.get("status") == "FAILED"
            for page in summary["normalization"]["pages"]
        )
        return 3 if failed else 0
    status = summary.get("ingestion", {}).get("status")
    return 0 if status == "COMPLETE" else 3 if status == "FAILED" else 2


def main() -> int:
    args = _parser().parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
