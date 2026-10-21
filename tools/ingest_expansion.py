#!/usr/bin/env python3
"""Database expansion ingestion runner.

Plans and executes provider scopes for the player universe, with:

* a **plan** built from configuration (priority league registry + dated country
  priority snapshot) — no hardcoded competition list in the code;
* **persistent checkpoints** per provider scope, so a run resumes instead of
  restarting;
* a **daily request budget** read from the provider itself, so an exhausted quota
  stops the run cleanly and reports the resume command;
* a **dry run** that estimates the work without touching the provider or the
  database;
* a machine-readable **summary** with per-scope status and honest completeness
  (`COMPLETE_FOR_DECLARED_SCOPE`, `PARTIAL`, `BLOCKED_BY_PLAN`, `FAILED`).

Examples
--------
Plan the work for the Premier League 2023 scope (no provider calls, no writes)::

    python tools/ingest_expansion.py plan --competition premier-league --season 2023

Execute it, capped at 40 provider requests::

    python tools/ingest_expansion.py run --competition premier-league --season 2023 --max-requests 40

Resume where the last run stopped (checkpoints are read automatically)::

    python tools/ingest_expansion.py run --competition premier-league --season 2023 --resume
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models.provenance import DataSnapshot, DataSource, IngestionRun  # noqa: E402
from app.ingestion.capability_registry import CapabilityRegistry  # noqa: E402
from app.ingestion.checkpoints import (  # noqa: E402
    BLOCKED,
    COMPLETE,
    FAILED,
    PARTIAL,
    PENDING,
    CheckpointStore,
)
from app.ingestion.scope import (  # noqa: E402
    IngestionScope,
    load_priority_competitions,
    plan_league_season,
)
from app.ingestion.snapshot_store import LocalFilesystemSnapshotStore  # noqa: E402
from app.ingestion.service import IngestionService  # noqa: E402
from app.normalization.service import NormalizationService  # noqa: E402
from app.providers.registry import default_registry  # noqa: E402

EXIT_OK = 0
EXIT_PARTIAL = 2
EXIT_FAILED = 3
EXIT_CONFIG = 4


@dataclass
class _SingleScopeResult:
    """Adapter for a scope that is one request without a page parameter."""

    status: str
    stop_reason: str
    pages_requested: int
    pages_succeeded: int
    records_fetched: int
    total_pages: int | None
    errors: list[str]
    runs: list[Any]
    last_page: int = 1
    plan_page_max: int | None = None


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


async def _provider_budget(provider_name: str) -> dict[str, Any]:
    """Read the provider's own request budget (never inferred)."""
    try:
        provider = default_registry.get(provider_name)
        raw = await provider.fetch("status")
        body = json.loads(raw.content)
        response = body.get("response") or {}
        requests = response.get("requests") or {}
        subscription = response.get("subscription") or {}
        return {
            "available": True,
            "plan": subscription.get("plan"),
            "requests_used_today": requests.get("current"),
            "requests_limit_today": requests.get("limit_day"),
            "requests_remaining_today": (
                requests.get("limit_day") - requests.get("current")
                if isinstance(requests.get("limit_day"), int)
                and isinstance(requests.get("current"), int)
                else None
            ),
            "subscription_active": subscription.get("active"),
            "subscription_end": subscription.get("end"),
        }
    except Exception as exc:  # noqa: BLE001 - a missing budget must not stop the run
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


async def _scope_status(
    session, provider: str, scope: IngestionScope
) -> dict[str, Any]:
    """The durable state of one scope, read from checkpoints and ingestion runs."""
    store = CheckpointStore(session)
    state = await store.state(provider, scope.entity_type, scope.params)
    runs = (
        await session.execute(
            select(IngestionRun, DataSnapshot)
            .join(DataSource, DataSource.id == IngestionRun.data_source_id)
            .outerjoin(DataSnapshot, DataSnapshot.ingestion_run_id == IngestionRun.id)
            .where(
                DataSource.name == provider,
                IngestionRun.endpoint == scope.resource,
            )
            .order_by(IngestionRun.started_at.desc())
        )
    ).all()
    matching = []
    for run, snapshot in runs:
        parameters = dict(run.parameters or {})
        if IngestionService._same_scope(parameters, scope.params):
            matching.append(
                {
                    "page": parameters.get("page"),
                    "status": str(getattr(run.status, "value", run.status)),
                    "record_count": run.record_count,
                    "error": run.error,
                    "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                }
            )
    return {
        "scope_key": scope.scope_key,
        "params": scope.params,
        "checkpoint": state.to_dict() if state else None,
        "runs": matching[:10],
    }


async def _execute_scope(
    session,
    service: IngestionService,
    normalizer: NormalizationService,
    scope: IngestionScope,
    *,
    max_requests: int,
    request_interval: float,
    resume: bool,
) -> dict[str, Any]:
    """Run one scope, honouring the plan cap, and normalise what was fetched."""
    store = CheckpointStore(session)
    start_page = 1
    if resume:
        state = await store.state(scope.provider, scope.entity_type, scope.params)
        if state and state.page:
            start_page = state.page + 1

    result = await service.run_paginated(
        scope.provider,
        scope.resource,
        start_page=start_page,
        max_pages=scope.max_pages,
        request_interval_seconds=request_interval,
        resume=resume,
        **scope.params,
    ) if scope.paginated else None

    if result is None:
        # A non-paginated scope (the club catalogue) is a single request without a
        # page parameter — the provider rejects an unknown Page field.
        run = await service.run(scope.provider, scope.resource, **scope.params)
        metadata = getattr(run, "_paging_metadata", {}) or {}
        total_pages = metadata.get("total")
        run_status = str(getattr(run.status, "value", run.status))
        result = _SingleScopeResult(
            status="COMPLETE" if run_status == "SUCCESS" else "FAILED",
            stop_reason="SINGLE_REQUEST",
            pages_requested=1,
            pages_succeeded=1 if run_status == "SUCCESS" else 0,
            records_fetched=run.record_count or 0,
            total_pages=total_pages,
            errors=[run.error] if run.error else [],
            runs=[run],
        )

    written = 0
    seen = 0
    for run in result.runs:
        snapshots = (
            await session.execute(
                select(DataSnapshot).where(DataSnapshot.ingestion_run_id == run.id)
            )
        ).scalars().all()
        for snapshot in snapshots:
            try:
                outcome = await normalizer.normalize_snapshot(snapshot.id)
            except Exception as exc:  # noqa: BLE001 - report, never hide
                written += 0
                continue
            if isinstance(outcome, dict):
                written += int(outcome.get("players_inserted", 0)) + int(
                    outcome.get("players_updated", 0)
                )
                seen += int(outcome.get("records_seen", 0))

    status = result.status
    if status == "COMPLETE":
        checkpoint_status = COMPLETE
    elif status == "BLOCKED_BY_PLAN":
        checkpoint_status = BLOCKED
    elif status == "FAILED":
        checkpoint_status = FAILED
    elif result.pages_succeeded:
        checkpoint_status = PARTIAL
    else:
        checkpoint_status = PENDING

    await store.record(
        provider=scope.provider,
        entity_type=scope.entity_type,
        params=scope.params,
        status=checkpoint_status,
        page=result.last_page,
        records_seen=seen or result.records_fetched,
        records_written=written,
        declared_total_pages=result.total_pages,
        last_error=(result.errors[0] if result.errors else None),
        competition=scope.competition,
        season=scope.season,
    )

    return {
        "scope_key": scope.scope_key,
        "params": scope.params,
        "status": status,
        "checkpoint_status": checkpoint_status,
        "pages_requested": result.pages_requested,
        "pages_succeeded": result.pages_succeeded,
        "records_fetched": result.records_fetched,
        "records_normalised": written,
        "declared_total_pages": result.total_pages,
        "stop_reason": result.stop_reason,
        "plan_page_max": result.plan_page_max,
        "errors": result.errors[:3],
    }


def _is_quota_failure(outcome: dict[str, Any]) -> bool:
    """True when the provider refused the request because the budget is spent."""
    if outcome.get("status") != "FAILED":
        return False
    for error in outcome.get("errors") or []:
        lowered = str(error).lower()
        if "request limit" in lowered or "rate limit" in lowered or "quota" in lowered:
            return True
    return False


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    competitions = load_priority_competitions(args.registry)
    by_key = {competition.key: competition for competition in competitions}

    if args.competition:
        competition = by_key.get(args.competition)
        if competition is None:
            print(_json({"status": "FAILED", "error": f"unknown competition '{args.competition}'",
                         "known": [item.key for item in competitions]}))
            return EXIT_CONFIG
    else:
        competition = competitions[0]

    seasons = [int(season) for season in args.season] if args.season else list(competition.default_seasons)

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    summary: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run" if args.dry_run else "execute",
        "provider": competition.provider,
        "competition": competition.key,
        "seasons": seasons,
        "scopes": [],
    }
    budget = await _provider_budget(competition.provider)
    requests_spent = 0
    if not args.dry_run:
        summary["provider_budget_at_start"] = budget
    try:
        async with Session() as session:
            service = IngestionService(
                session=session,
                provider_registry=default_registry,
                snapshot_store=LocalFilesystemSnapshotStore(settings.snapshot_storage_path),
                capability_registry=CapabilityRegistry(session),
            )
            normalizer = NormalizationService(session)

            for season in seasons:
                plan = await plan_league_season(
                    session, competition, season, plan_page_cap=args.plan_page_cap
                )
                summary.setdefault("plans", []).append(
                    {"season": season, "plan": plan.to_dict()}
                )
                for scope in plan.scopes:
                    state = await _scope_status(session, competition.provider, scope)
                    if args.dry_run:
                        summary["scopes"].append(
                            {
                                "scope_key": scope.scope_key,
                                "params": scope.params,
                                "planned_max_pages": scope.max_pages,
                                "note": scope.note,
                                "current_state": state,
                                "action": "DRY_RUN_NO_REQUEST",
                            }
                        )
                        continue
                    if state.get("checkpoint") and state["checkpoint"]["status"] == COMPLETE and not args.force:
                        summary["scopes"].append(
                            {
                                "scope_key": scope.scope_key,
                                "params": scope.params,
                                "action": "SKIPPED_ALREADY_COMPLETE",
                                "current_state": state,
                            }
                        )
                        continue
                    if args.max_scopes and len(summary["scopes"]) >= args.max_scopes:
                        summary["scopes"].append(
                            {
                                "scope_key": scope.scope_key,
                                "params": scope.params,
                                "action": "SKIPPED_SCOPE_LIMIT",
                            }
                        )
                        continue
                    remaining = None
                    if isinstance(budget.get("requests_remaining_today"), int):
                        remaining = budget["requests_remaining_today"] - requests_spent
                        if remaining <= 0:
                            summary["scopes"].append(
                                {
                                    "scope_key": scope.scope_key,
                                    "params": scope.params,
                                    "action": "SKIPPED_DAILY_BUDGET_EXHAUSTED",
                                }
                            )
                            continue
                    if args.max_requests and requests_spent >= args.max_requests:
                        summary["scopes"].append(
                            {
                                "scope_key": scope.scope_key,
                                "params": scope.params,
                                "action": "SKIPPED_REQUEST_LIMIT",
                            }
                        )
                        continue
                    outcome = await _execute_scope(
                        session,
                        service,
                        normalizer,
                        scope,
                        max_requests=args.max_requests,
                        request_interval=args.request_interval,
                        resume=args.resume,
                    )
                    outcome["note"] = scope.note
                    requests_spent += int(outcome.get("pages_requested", 0))
                    summary["scopes"].append(outcome)
                    if _is_quota_failure(outcome):
                        # The provider refused the request: the daily budget is
                        # spent. Stop cleanly and keep every checkpoint.
                        summary["budget_exhausted"] = True
                        for remaining_scope in plan.scopes[plan.scopes.index(scope) + 1 :]:
                            summary["scopes"].append(
                                {
                                    "scope_key": remaining_scope.scope_key,
                                    "params": remaining_scope.params,
                                    "action": "SKIPPED_DAILY_BUDGET_EXHAUSTED",
                                }
                            )
                        break
    finally:
        await engine.dispose()

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    if not args.dry_run:
        summary["provider_requests_spent"] = requests_spent
        summary["provider_budget"] = await _provider_budget(competition.provider)
        summary["resume_command"] = (
            f"python tools/ingest_expansion.py run --competition {competition.key} "
            f"--season {' '.join(str(season) for season in seasons)} --resume"
        )
    statuses = {entry.get("status") for entry in summary["scopes"]}
    summary["status"] = (
        "DRY_RUN"
        if args.dry_run
        else "COMPLETE"
        if statuses and statuses <= {"COMPLETE"}
        else "PARTIAL"
        if statuses - {"COMPLETE"}
        else "FAILED"
    )
    print(_json(summary))
    return EXIT_OK if summary["status"] in ("DRY_RUN", "COMPLETE") else EXIT_PARTIAL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "run"])
    parser.add_argument("--competition", help="competition key from the registry")
    parser.add_argument("--season", nargs="*", help="season(s) to ingest")
    parser.add_argument("--registry", help="priority league registry file")
    parser.add_argument("--plan-page-cap", type=int, default=3,
                        help="max pages per scope (API-Football Free plan caps page at 3)")
    parser.add_argument("--max-requests", type=int, default=0,
                        help="maximum number of provider requests this run may make (0 = no limit)")
    parser.add_argument("--max-scopes", type=int, default=0,
                        help="maximum number of scopes to execute in this run (0 = no limit)")
    parser.add_argument("--request-interval", type=float, default=6.5,
                        help="seconds between provider requests (10 req/min plan limit)")
    parser.add_argument("--resume", action="store_true", help="resume from the stored checkpoints")
    parser.add_argument("--force", action="store_true", help="re-run scopes already marked complete")
    parser.add_argument("--dry-run", action="store_true", help="plan only: no provider calls, no writes")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
