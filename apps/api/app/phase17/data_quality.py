"""Live DataQualityReport (§10).

Two passes, both on real data:
1. `assess_payload` runs on the Bronze payload before Silver promotion.
2. `assess_silver` runs on the canonical rows for a competition season.

Every check reports PASS / WARN / FAIL with the number of affected records.
A check that cannot run (e.g. cross-provider conflict with a single
provider) reports WARN with `evaluated: false` — never PASS.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.canonical import Club, ClubIdentity, Match, MatchEvent, MatchLineup, Player, PlayerIdentity
from app.db.models.operations import QualityReport
from app.normalization.statsbomb_transformers import is_starter
from app.phase17 import QualityStatus
from app.phase17.contract_drift import ContractCheck, ContractStatus

MAX_PLAUSIBLE_GOALS = 15
MAX_MINUTE = 130


@dataclass
class QualityCheck:
    name: str
    status: QualityStatus
    affected_records: int
    detail: str
    evaluated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status.value, "affected_records": self.affected_records,
                "detail": self.detail, "evaluated": self.evaluated}


@dataclass
class DataQualityReport:
    scope: str
    records_examined: int
    checks: list[QualityCheck] = field(default_factory=list)
    snapshot_sha256: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def overall(self) -> QualityStatus:
        statuses = {c.status for c in self.checks}
        if QualityStatus.FAIL in statuses:
            return QualityStatus.FAIL
        if QualityStatus.WARN in statuses:
            return QualityStatus.WARN
        return QualityStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "overall": self.overall.value, "records_examined": self.records_examined,
                "snapshot_sha256": self.snapshot_sha256, "created_at": self.created_at,
                "checks": [c.to_dict() for c in self.checks]}

    async def persist(self, session: AsyncSession) -> QualityReport:
        row = QualityReport(scope=self.scope, snapshot_sha256=self.snapshot_sha256, overall=self.overall.value,
                            checks=[c.to_dict() for c in self.checks], records_examined=self.records_examined)
        session.add(row)
        await session.flush()
        return row


def _ok(name: str, n: int, detail: str = "") -> QualityCheck:
    return QualityCheck(name, QualityStatus.PASS if n == 0 else QualityStatus.FAIL, n, detail)


def assess_payload(
    provider: str,
    resource: str,
    payload: Any,
    params: dict[str, Any],
    contract: ContractCheck,
    snapshot_sha256: str | None = None,
) -> DataQualityReport:
    records = payload if isinstance(payload, list) else []
    report = DataQualityReport(scope=f"bronze:{provider}:{resource}", records_examined=len(records),
                               snapshot_sha256=snapshot_sha256)

    blocking = [f for f in contract.findings if f.get("severity") == "BLOCK"]
    report.checks.append(QualityCheck(
        "schema_validation",
        QualityStatus.FAIL if contract.status == ContractStatus.INGESTION_BLOCKED
        else QualityStatus.WARN if contract.status in (ContractStatus.CONTRACT_WARN, ContractStatus.NO_CONTRACT)
        else QualityStatus.PASS,
        sum(int(f.get("records", 1)) for f in blocking),
        contract.status.value,
    ))

    if provider == "statsbomb" and resource == "matches":
        ids = Counter(r.get("match_id") for r in records)
        report.checks.append(_ok("duplicate_detection", sum(c - 1 for c in ids.values() if c > 1),
                                 "duplicate match_id in payload"))
        null_scores = sum(1 for r in records if r.get("home_score") is None or r.get("away_score") is None)
        report.checks.append(QualityCheck("null_checks", QualityStatus.PASS if null_scores == 0 else QualityStatus.WARN,
                                          null_scores, "matches without a final score"))
        impossible = sum(1 for r in records for k in ("home_score", "away_score")
                         if isinstance(r.get(k), int) and not 0 <= r[k] <= MAX_PLAUSIBLE_GOALS)
        report.checks.append(_ok("impossible_values", impossible, f"score outside [0, {MAX_PLAUSIBLE_GOALS}]"))
        today = datetime.now(timezone.utc).date().isoformat()
        future_finished = sum(1 for r in records if r.get("home_score") is not None and str(r.get("match_date")) > today)
        report.checks.append(_ok("temporal_validation", future_finished, "scored match dated in the future"))
        comp = str(params.get("competition_id"))
        season = str(params.get("season_id"))
        wrong_comp = sum(1 for r in records if str((r.get("competition") or {}).get("competition_id")) != comp)
        wrong_season = sum(1 for r in records if str((r.get("season") or {}).get("season_id")) != season)
        report.checks.append(_ok("competition_consistency", wrong_comp, f"records not in competition {comp}"))
        report.checks.append(_ok("season_consistency", wrong_season, f"records not in season {season}"))
        self_play = sum(1 for r in records
                        if (r.get("home_team") or {}).get("home_team_id") == (r.get("away_team") or {}).get("away_team_id"))
        report.checks.append(_ok("identity_consistency", self_play, "home team id equals away team id"))

    elif provider == "statsbomb" and resource == "lineups":
        report.checks.append(_ok("team_count", 0 if len(records) == 2 else 1, f"{len(records)} teams (expected 2)"))
        pids = Counter(p.get("player_id") for t in records for p in t.get("lineup", []))
        report.checks.append(_ok("duplicate_detection", sum(c - 1 for c in pids.values() if c > 1),
                                 "player listed twice in one match"))
        starters = [sum(1 for p in t.get("lineup", []) if is_starter(p.get("positions") or [])) for t in records]
        bad = sum(1 for s in starters if s != 11)
        report.checks.append(_ok("impossible_values", bad, f"starting XI sizes {starters} (expected 11)"))

    elif provider == "statsbomb" and resource == "events":
        ids = Counter(e.get("id") for e in records)
        report.checks.append(_ok("duplicate_detection", sum(c - 1 for c in ids.values() if c > 1), "duplicate event id"))
        bad_minute = sum(1 for e in records if not 0 <= int(e.get("minute", 0)) <= MAX_MINUTE)
        report.checks.append(_ok("impossible_values", bad_minute, f"minute outside [0, {MAX_MINUTE}]"))
        bad_loc = sum(1 for e in records if isinstance(e.get("location"), list) and len(e["location"]) >= 2
                      and not (0 <= e["location"][0] <= 120 and 0 <= e["location"][1] <= 80))
        report.checks.append(_ok("pitch_bounds", bad_loc, "location outside the 120x80 StatsBomb pitch"))
        teams = {(e.get("team") or {}).get("id") for e in records if e.get("team")}
        report.checks.append(_ok("identity_consistency", 0 if len(teams) == 2 else 1, f"{len(teams)} team ids in events"))

    report.checks.append(QualityCheck(
        "provider_conflict_detection", QualityStatus.WARN, 0,
        "single provider for this resource; cross-provider comparison not possible", evaluated=False,
    ))
    return report


async def assess_silver(session: AsyncSession, provider: str, competition_season_id) -> DataQualityReport:
    matches = (await session.execute(
        select(Match).where(Match.provider == provider, Match.competition_season_id == competition_season_id)
    )).scalars().all()
    report = DataQualityReport(scope=f"silver:{provider}:{competition_season_id}", records_examined=len(matches))
    match_ids = [m.id for m in matches]

    orphans = sum(1 for m in matches if m.snapshot_id is None)
    report.checks.append(_ok("referential_integrity", orphans, "Silver match with no Bronze snapshot (orphan)"))

    dup = Counter((m.home_club_id, m.away_club_id, m.date) for m in matches)
    report.checks.append(_ok("duplicate_detection", sum(c - 1 for c in dup.values() if c > 1), "duplicate fixture"))

    now = datetime.now(timezone.utc)
    future = sum(1 for m in matches if m.status == "FINISHED" and m.date > now)
    report.checks.append(_ok("temporal_validation", future, "FINISHED match dated in the future"))

    # Cross-resource conflict: Silver goal events vs the provider's own score.
    if match_ids:
        goals = dict((await session.execute(
            select(MatchEvent.match_id, func.count()).where(MatchEvent.match_id.in_(match_ids),
                                                             MatchEvent.event_type == "GOAL")
            .group_by(MatchEvent.match_id))).all())
        with_events = set((await session.execute(
            select(MatchEvent.match_id).where(MatchEvent.match_id.in_(match_ids)).distinct())).scalars().all())
        mismatched = [str(m.id) for m in matches if m.id in with_events
                      and goals.get(m.id, 0) != (m.home_score or 0) + (m.away_score or 0)]
        report.checks.append(QualityCheck(
            "score_event_reconciliation",
            QualityStatus.FAIL if mismatched else QualityStatus.PASS if with_events else QualityStatus.WARN,
            len(mismatched), f"{len(with_events)} matches with events reconciled against final score",
            evaluated=bool(with_events),
        ))
        lineup_counts = dict((await session.execute(
            select(MatchLineup.match_id, func.count()).where(MatchLineup.match_id.in_(match_ids))
            .group_by(MatchLineup.match_id))).all())
        thin = sum(1 for c in lineup_counts.values() if c < 22)
        if lineup_counts:
            report.checks.append(_ok("lineup_completeness", thin,
                                     f"{len(lineup_counts)} matches with lineups; fewer than 22 players"))
        else:
            report.checks.append(QualityCheck("lineup_completeness", QualityStatus.WARN, 0,
                                              "no lineups ingested for this scope", evaluated=False))

    # Identity consistency: one canonical entity per provider id.
    dup_players = (await session.execute(
        select(PlayerIdentity.provider_player_id).where(PlayerIdentity.provider == provider)
        .group_by(PlayerIdentity.provider_player_id).having(func.count(func.distinct(PlayerIdentity.player_id)) > 1)
    )).scalars().all()
    dup_clubs = (await session.execute(
        select(ClubIdentity.provider_club_id).where(ClubIdentity.provider == provider)
        .group_by(ClubIdentity.provider_club_id).having(func.count(func.distinct(ClubIdentity.club_id)) > 1)
    )).scalars().all()
    report.checks.append(_ok("identity_consistency", len(dup_players) + len(dup_clubs),
                             "provider id mapped to more than one canonical entity"))

    unnamed = (await session.execute(select(func.count()).select_from(Player).where(Player.name == ""))).scalar_one()
    unnamed_clubs = (await session.execute(select(func.count()).select_from(Club).where(Club.name == ""))).scalar_one()
    report.checks.append(_ok("null_checks", unnamed + unnamed_clubs, "canonical entity with empty name"))
    return report
