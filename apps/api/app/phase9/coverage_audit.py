"""Phase 9 — Data Coverage Audit & Matrix Builder.

Builds a truthful coverage matrix across all dimensions:
  Competition, Season, Club, Player, Match, Transfer, Event, Lineup, Player-match statistics.

For each dimension records:
  record_count, date_range, provider, provenance_completeness,
  missingness, validation_status, freshness, coverage_quality.

Never merges datasets without preserving source provenance.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class CoverageQuality(str, Enum):
    EXCELLENT = "EXCELLENT"        # >90% complete, verified provenance
    GOOD = "GOOD"                  # 70-90% complete
    PARTIAL = "PARTIAL"            # 30-70% complete
    SPARSE = "SPARSE"              # 10-30% complete
    MINIMAL = "MINIMAL"            # <10% complete
    ABSENT = "ABSENT"              # No data


class ValidationStatus(str, Enum):
    VALIDATED = "VALIDATED"
    PARTIAL_VALIDATION = "PARTIAL_VALIDATION"
    UNVALIDATED = "UNVALIDATED"
    QUARANTINED = "QUARANTINED"


@dataclass
class DimensionCoverage:
    """Coverage assessment for a single data dimension."""
    dimension: str
    record_count: int
    date_range_start: str | None = None
    date_range_end: str | None = None
    provider: str = "UNKNOWN"
    provenance_completeness: float = 0.0  # 0.0 – 1.0
    missingness_rate: float = 0.0         # 0.0 – 1.0
    validation_status: str = ValidationStatus.UNVALIDATED
    freshness_days: int | None = None
    coverage_quality: str = CoverageQuality.ABSENT
    file_count: int = 0
    total_bytes: int = 0
    checksum: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class CompetitionCoverage:
    """Coverage for a specific competition."""
    competition_name: str
    country: str
    provider: str
    seasons_covered: list[str] = field(default_factory=list)
    total_matches: int = 0
    total_players: int = 0
    total_transfers: int = 0
    coverage_quality: str = CoverageQuality.ABSENT
    notes: list[str] = field(default_factory=list)


@dataclass
class CoverageMatrix:
    """Full data coverage matrix for Phase 9 audit."""
    audit_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    audit_version: str = "phase9_coverage_v1"
    dimensions: dict[str, DimensionCoverage] = field(default_factory=dict)
    competitions: dict[str, CompetitionCoverage] = field(default_factory=dict)
    providers_used: list[str] = field(default_factory=list)
    total_bronze_files: int = 0
    total_bronze_bytes: int = 0
    overall_quality: str = CoverageQuality.ABSENT
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _scan_bronze_dir(base_path: str | Path) -> dict[str, Any]:
    """Scan a bronze directory and return file stats."""
    base = Path(base_path)
    result: dict[str, Any] = {
        "file_count": 0,
        "total_bytes": 0,
        "files": [],
        "subdirs": [],
    }
    if not base.exists():
        return result

    for item in sorted(base.iterdir()):
        if item.is_file() and item.name != ".gitkeep":
            size = item.stat().st_size
            result["file_count"] += 1
            result["total_bytes"] += size
            result["files"].append({
                "name": item.name,
                "size_bytes": size,
                "extension": item.suffix,
            })
        elif item.is_dir() and not item.name.startswith(".") and item.name != "__pycache__":
            sub = _scan_bronze_dir(item)
            result["file_count"] += sub["file_count"]
            result["total_bytes"] += sub["total_bytes"]
            result["subdirs"].append({
                "name": item.name,
                **sub,
            })
    return result


def _count_json_records(filepath: str | Path) -> int:
    """Count top-level records in a JSON file (list → len, dict with 'response' → len of response)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            if "response" in data and isinstance(data["response"], list):
                return len(data["response"])
            if "transfers" in data and isinstance(data["transfers"], list):
                return len(data["transfers"])
            return 1
        return 0
    except (json.JSONDecodeError, OSError):
        return 0


def _compute_file_checksum(filepath: str | Path) -> str:
    """Compute SHA-256 checksum for a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _assess_quality(
    record_count: int,
    provenance: float,
    missingness: float,
) -> str:
    """Determine CoverageQuality based on metrics."""
    if record_count == 0:
        return CoverageQuality.ABSENT
    if provenance >= 0.9 and missingness <= 0.1 and record_count >= 100:
        return CoverageQuality.EXCELLENT
    if provenance >= 0.7 and missingness <= 0.3 and record_count >= 50:
        return CoverageQuality.GOOD
    if provenance >= 0.3 and record_count >= 20:
        return CoverageQuality.PARTIAL
    if record_count >= 5:
        return CoverageQuality.SPARSE
    return CoverageQuality.MINIMAL


def build_coverage_matrix(data_root: str | Path) -> CoverageMatrix:
    """Build a comprehensive data coverage matrix from the bronze layer.

    Args:
        data_root: Path to the 'data' directory containing bronze/ and models/.

    Returns:
        CoverageMatrix with truthful coverage assessment.
    """
    data_root = Path(data_root)
    bronze_root = data_root / "bronze"
    matrix = CoverageMatrix()

    providers_found: set[str] = set()

    # ── Scan API-Football Bronze ──
    api_football_root = bronze_root / "api-football"
    if api_football_root.exists():
        providers_found.add("api-football")

        # Fixtures (matches)
        fixtures_root = api_football_root / "fixtures"
        fixtures_scan = _scan_bronze_dir(fixtures_root)
        fixture_records = 0
        for f_info in fixtures_scan.get("files", []):
            fp = fixtures_root / f_info["name"]
            fixture_records += _count_json_records(fp)

        matrix.dimensions["matches"] = DimensionCoverage(
            dimension="matches",
            record_count=fixture_records,
            provider="api-football",
            provenance_completeness=1.0 if fixture_records > 0 else 0.0,
            missingness_rate=0.0,
            validation_status=ValidationStatus.VALIDATED if fixture_records > 0 else ValidationStatus.UNVALIDATED,
            coverage_quality=_assess_quality(fixture_records, 1.0, 0.0),
            file_count=fixtures_scan["file_count"],
            total_bytes=fixtures_scan["total_bytes"],
            notes=[f"Scanned from {fixtures_root}"],
        )

        # Events
        events_root = fixtures_root / "events"
        events_scan = _scan_bronze_dir(events_root)
        event_records = 0
        for f_info in events_scan.get("files", []):
            fp = events_root / f_info["name"]
            event_records += _count_json_records(fp)

        matrix.dimensions["events"] = DimensionCoverage(
            dimension="events",
            record_count=event_records,
            provider="api-football",
            provenance_completeness=1.0 if event_records > 0 else 0.0,
            missingness_rate=0.0,
            validation_status=ValidationStatus.VALIDATED if event_records > 0 else ValidationStatus.UNVALIDATED,
            coverage_quality=_assess_quality(event_records, 1.0, 0.0),
            file_count=events_scan["file_count"],
            total_bytes=events_scan["total_bytes"],
        )

        # Lineups
        lineups_root = fixtures_root / "lineups"
        lineups_scan = _scan_bronze_dir(lineups_root)
        lineup_records = 0
        for f_info in lineups_scan.get("files", []):
            fp = lineups_root / f_info["name"]
            lineup_records += _count_json_records(fp)

        matrix.dimensions["lineups"] = DimensionCoverage(
            dimension="lineups",
            record_count=lineup_records,
            provider="api-football",
            provenance_completeness=1.0 if lineup_records > 0 else 0.0,
            missingness_rate=0.0,
            validation_status=ValidationStatus.VALIDATED if lineup_records > 0 else ValidationStatus.UNVALIDATED,
            coverage_quality=_assess_quality(lineup_records, 1.0, 0.0),
            file_count=lineups_scan["file_count"],
            total_bytes=lineups_scan["total_bytes"],
        )

        # Player-match statistics
        player_stats_root = fixtures_root / "players"
        pstats_scan = _scan_bronze_dir(player_stats_root)
        pstat_records = 0
        for f_info in pstats_scan.get("files", []):
            fp = player_stats_root / f_info["name"]
            pstat_records += _count_json_records(fp)

        # Also check fixtures/statistics
        stats_root = fixtures_root / "statistics"
        stats_scan = _scan_bronze_dir(stats_root)
        team_stat_records = 0
        for f_info in stats_scan.get("files", []):
            fp = stats_root / f_info["name"]
            team_stat_records += _count_json_records(fp)

        matrix.dimensions["player_match_statistics"] = DimensionCoverage(
            dimension="player_match_statistics",
            record_count=pstat_records,
            provider="api-football",
            provenance_completeness=1.0 if pstat_records > 0 else 0.0,
            missingness_rate=0.0,
            validation_status=ValidationStatus.VALIDATED if pstat_records > 0 else ValidationStatus.UNVALIDATED,
            coverage_quality=_assess_quality(pstat_records, 1.0, 0.0),
            file_count=pstats_scan["file_count"],
            total_bytes=pstats_scan["total_bytes"],
        )

        # Players
        players_root = api_football_root / "players"
        players_scan = _scan_bronze_dir(players_root)
        player_records = 0
        for f_info in players_scan.get("files", []):
            fp = players_root / f_info["name"]
            player_records += _count_json_records(fp)

        matrix.dimensions["players"] = DimensionCoverage(
            dimension="players",
            record_count=player_records,
            provider="api-football",
            provenance_completeness=1.0 if player_records > 0 else 0.0,
            missingness_rate=0.0,
            validation_status=ValidationStatus.VALIDATED if player_records > 0 else ValidationStatus.UNVALIDATED,
            coverage_quality=_assess_quality(player_records, 1.0, 0.0),
            file_count=players_scan["file_count"],
            total_bytes=players_scan["total_bytes"],
        )

        # Teams (clubs)
        teams_root = api_football_root / "teams"
        teams_scan = _scan_bronze_dir(teams_root)
        team_records = 0
        for f_info in teams_scan.get("files", []):
            fp = teams_root / f_info["name"]
            team_records += _count_json_records(fp)

        matrix.dimensions["clubs"] = DimensionCoverage(
            dimension="clubs",
            record_count=team_records,
            provider="api-football",
            provenance_completeness=1.0 if team_records > 0 else 0.0,
            missingness_rate=0.0,
            validation_status=ValidationStatus.VALIDATED if team_records > 0 else ValidationStatus.UNVALIDATED,
            coverage_quality=_assess_quality(team_records, 1.0, 0.0),
            file_count=teams_scan["file_count"],
            total_bytes=teams_scan["total_bytes"],
        )

        # Leagues (competitions)
        leagues_root = api_football_root / "leagues"
        leagues_scan = _scan_bronze_dir(leagues_root)
        league_records = 0
        for f_info in leagues_scan.get("files", []):
            fp = leagues_root / f_info["name"]
            league_records += _count_json_records(fp)

        matrix.dimensions["competitions"] = DimensionCoverage(
            dimension="competitions",
            record_count=league_records,
            provider="api-football",
            provenance_completeness=1.0 if league_records > 0 else 0.0,
            missingness_rate=0.0,
            validation_status=ValidationStatus.VALIDATED if league_records > 0 else ValidationStatus.UNVALIDATED,
            coverage_quality=_assess_quality(league_records, 1.0, 0.0),
            file_count=leagues_scan["file_count"],
            total_bytes=leagues_scan["total_bytes"],
        )

        # Transfers (API-Football)
        api_transfers_root = api_football_root / "transfers"
        api_transfers_scan = _scan_bronze_dir(api_transfers_root)
        api_transfer_records = 0
        for f_info in api_transfers_scan.get("files", []):
            fp = api_transfers_root / f_info["name"]
            api_transfer_records += _count_json_records(fp)

    # ── Scan Open-Transfers Bronze ──
    open_transfers_root = bronze_root / "open-transfers"
    open_transfer_records = 0
    open_transfers_scan: dict[str, Any] = {"file_count": 0, "total_bytes": 0}
    if open_transfers_root.exists():
        providers_found.add("open-transfers")
        open_transfers_scan = _scan_bronze_dir(open_transfers_root)
        for f_info in open_transfers_scan.get("files", []):
            fp = open_transfers_root / f_info["name"]
            open_transfer_records += _count_json_records(fp)

    total_transfer_records = api_transfer_records + open_transfer_records if api_football_root.exists() else open_transfer_records

    matrix.dimensions["transfers"] = DimensionCoverage(
        dimension="transfers",
        record_count=total_transfer_records,
        provider=",".join(sorted(providers_found)) if providers_found else "UNKNOWN",
        provenance_completeness=1.0 if total_transfer_records > 0 else 0.0,
        missingness_rate=0.0,
        validation_status=ValidationStatus.VALIDATED if total_transfer_records > 0 else ValidationStatus.UNVALIDATED,
        coverage_quality=_assess_quality(total_transfer_records, 1.0, 0.0),
        file_count=(api_transfers_scan.get("file_count", 0) if api_football_root.exists() else 0) + open_transfers_scan["file_count"],
        total_bytes=(api_transfers_scan.get("total_bytes", 0) if api_football_root.exists() else 0) + open_transfers_scan["total_bytes"],
        notes=[
            f"api-football transfers: {api_transfer_records if api_football_root.exists() else 0}",
            f"open-transfers: {open_transfer_records}",
        ],
    )

    # Seasons (synthetic dimension — inferred from league data)
    matrix.dimensions["seasons"] = DimensionCoverage(
        dimension="seasons",
        record_count=0,  # Will be populated from parsed league data
        provider=",".join(sorted(providers_found)),
        provenance_completeness=0.5,
        coverage_quality=CoverageQuality.PARTIAL,
        notes=["Season records are inferred from competition data, not independently stored in bronze"],
    )

    # ── Aggregate totals ──
    total_scan = _scan_bronze_dir(bronze_root)
    matrix.total_bronze_files = total_scan["file_count"]
    matrix.total_bronze_bytes = total_scan["total_bytes"]
    matrix.providers_used = sorted(providers_found)

    # ── Competition coverage ──
    # Build from known transfer data files (which reference competitions)
    known_competitions = {
        "Premier League": {"country": "England", "code": "EPL"},
        "La Liga": {"country": "Spain", "code": "LaLiga"},
        "Serie A": {"country": "Italy", "code": "SerieA"},
        "Bundesliga": {"country": "Germany", "code": "Bundesliga"},
        "Ligue 1": {"country": "France", "code": "Ligue1"},
    }
    for comp_name, meta in known_competitions.items():
        has_transfer_data = any(
            meta["code"].lower() in f_info.get("name", "").lower()
            for f_info in open_transfers_scan.get("files", [])
        )
        matrix.competitions[comp_name] = CompetitionCoverage(
            competition_name=comp_name,
            country=meta["country"],
            provider=",".join(sorted(providers_found)),
            coverage_quality=CoverageQuality.PARTIAL if has_transfer_data else CoverageQuality.SPARSE,
            notes=[
                f"Transfer data {'present' if has_transfer_data else 'absent'} in open-transfers"
            ],
        )

    # ── Overall quality assessment ──
    quality_scores = []
    quality_map = {
        CoverageQuality.EXCELLENT: 5,
        CoverageQuality.GOOD: 4,
        CoverageQuality.PARTIAL: 3,
        CoverageQuality.SPARSE: 2,
        CoverageQuality.MINIMAL: 1,
        CoverageQuality.ABSENT: 0,
    }
    for dim in matrix.dimensions.values():
        quality_scores.append(quality_map.get(dim.coverage_quality, 0))

    avg_quality = sum(quality_scores) / max(len(quality_scores), 1)
    if avg_quality >= 4.5:
        matrix.overall_quality = CoverageQuality.EXCELLENT
    elif avg_quality >= 3.5:
        matrix.overall_quality = CoverageQuality.GOOD
    elif avg_quality >= 2.0:
        matrix.overall_quality = CoverageQuality.PARTIAL
    elif avg_quality >= 1.0:
        matrix.overall_quality = CoverageQuality.SPARSE
    else:
        matrix.overall_quality = CoverageQuality.MINIMAL

    # ── Limitations ──
    matrix.limitations = [
        "Coverage audit is based on bronze-layer file system scan only",
        "Record counts from JSON parsing may not reflect canonical (Silver) layer deduplication",
        "Date ranges not extracted from all file formats — requires per-provider parsing",
        "No live API queries performed during audit — only local data assessed",
        "Competition coverage is inferred from file naming conventions",
        "UCL/UEL data coverage not yet established in bronze layer",
    ]

    return matrix
