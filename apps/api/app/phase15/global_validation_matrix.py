"""Global Validation Matrix for Phase 15.

Tracks validation coverage across 9 dimensions:
1. ENGINE (e.g. ValuationEngine, TacticalFit, ContributionModel, MatchPrediction)
2. COMPETITION (EPL, La_Liga, Serie_A, Bundesliga, Ligue_1)
3. SEASON (2022/23, 2023/24, 2024/25)
4. POSITION (GK, DF, MF, FW)
5. ROLE (Inverted FB, Ball Playing CB, Box-to-Box, Deep Lying Playmaker, etc.)
6. AGE_BAND (U21, 21-24, 25-29, 30+)
7. CONFIDENCE_TIER (HIGH, MEDIUM, LOW)
8. OOD_STATUS (IN_DOMAIN, MARGINAL, OOD)
9. DATA_STATUS (DATA_AVAILABLE, LOW_SAMPLE, INSUFFICIENT_DATA)

Validation statuses:
- VALIDATED
- PARTIALLY_VALIDATED
- INSUFFICIENT_DATA
- UNCALIBRATED
- OOD
- NOT_EVALUATED
"""

from typing import Any
from pydantic import BaseModel, Field
from app.phase15 import DataSufficiencyStatus, ValidationMatrixStatus
from app.dev_fixtures import dev_seed_enabled


class ValidationMatrixCell(BaseModel):
    cell_id: str
    engine: str
    competition: str
    season: str
    position: str
    role: str
    age_band: str
    confidence_tier: str
    ood_status: str
    data_status: DataSufficiencyStatus
    validation_status: ValidationMatrixStatus
    sample_size: int
    primary_metric_name: str
    metric_value: float | None = None
    calibration_status: str  # CALIBRATED, MISCALIBRATED, UNKNOWN
    notes: list[str] = Field(default_factory=list)


class GlobalValidationMatrix:
    """Multi-dimensional matrix tracking validated operational boundaries across engines and contexts."""

    def __init__(self) -> None:
        self._cells: dict[str, ValidationMatrixCell] = {}

    def register_cell(
        self,
        engine: str,
        competition: str,
        season: str,
        position: str,
        role: str,
        age_band: str,
        confidence_tier: str,
        ood_status: str,
        data_status: DataSufficiencyStatus,
        sample_size: int,
        primary_metric_name: str,
        metric_value: float | None,
        calibration_status: str = "CALIBRATED",
        notes: list[str] | None = None,
    ) -> ValidationMatrixCell:
        cell_id = f"{engine}:{competition}:{season}:{position}:{role}:{age_band}:{ood_status}".lower()

        val_status: ValidationMatrixStatus
        if ood_status == "OOD":
            val_status = ValidationMatrixStatus.OOD
        elif data_status in (DataSufficiencyStatus.INSUFFICIENT_DATA, DataSufficiencyStatus.UNAVAILABLE) or sample_size == 0:
            val_status = ValidationMatrixStatus.INSUFFICIENT_DATA
        elif sample_size < 15 or data_status == DataSufficiencyStatus.LOW_SAMPLE:
            val_status = ValidationMatrixStatus.PARTIALLY_VALIDATED
        elif calibration_status == "MISCALIBRATED":
            val_status = ValidationMatrixStatus.UNCALIBRATED
        else:
            val_status = ValidationMatrixStatus.VALIDATED

        cell = ValidationMatrixCell(
            cell_id=cell_id,
            engine=engine,
            competition=competition,
            season=season,
            position=position,
            role=role,
            age_band=age_band,
            confidence_tier=confidence_tier,
            ood_status=ood_status,
            data_status=data_status,
            validation_status=val_status,
            sample_size=sample_size,
            primary_metric_name=primary_metric_name,
            metric_value=metric_value,
            calibration_status=calibration_status,
            notes=notes or [],
        )

        self._cells[cell_id] = cell
        return cell

    def query_cells(
        self,
        engine: str | None = None,
        competition: str | None = None,
        validation_status: ValidationMatrixStatus | None = None,
    ) -> list[ValidationMatrixCell]:
        cells = list(self._cells.values())
        if engine:
            cells = [c for c in cells if c.engine.lower() == engine.lower()]
        if competition:
            cells = [c for c in cells if c.competition.lower() == competition.lower()]
        if validation_status:
            cells = [c for c in cells if c.validation_status == validation_status]
        return cells

    def get_summary_coverage(self) -> dict[str, Any]:
        cells = list(self._cells.values())
        total = len(cells)
        validated = len([c for c in cells if c.validation_status == ValidationMatrixStatus.VALIDATED])
        partial = len([c for c in cells if c.validation_status == ValidationMatrixStatus.PARTIALLY_VALIDATED])
        insufficient = len([c for c in cells if c.validation_status == ValidationMatrixStatus.INSUFFICIENT_DATA])
        ood = len([c for c in cells if c.validation_status == ValidationMatrixStatus.OOD])

        return {
            "total_evaluated_cells": total,
            "validated_cells": validated,
            "partially_validated_cells": partial,
            "insufficient_data_cells": insufficient,
            "ood_cells": ood,
            "validation_ratio": round(validated / max(total, 1), 3),
        }


_GLOBAL_VALIDATION_MATRIX: GlobalValidationMatrix | None = None


def get_global_validation_matrix() -> GlobalValidationMatrix:
    global _GLOBAL_VALIDATION_MATRIX
    if _GLOBAL_VALIDATION_MATRIX is None:
        _GLOBAL_VALIDATION_MATRIX = GlobalValidationMatrix()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            # Seed key matrix cells across engines and leagues
            _GLOBAL_VALIDATION_MATRIX.register_cell(
                engine="ValuationEngine",
                competition="EPL",
                season="2023/2024",
                position="MF",
                role="Central Midfielder",
                age_band="21-24",
                confidence_tier="HIGH",
                ood_status="IN_DOMAIN",
                data_status=DataSufficiencyStatus.DATA_AVAILABLE,
                sample_size=84,
                primary_metric_name="MAE_ratio",
                metric_value=0.118,
            )
            _GLOBAL_VALIDATION_MATRIX.register_cell(
                engine="ValuationEngine",
                competition="Bundesliga",
                season="2023/2024",
                position="MF",
                role="Central Midfielder",
                age_band="21-24",
                confidence_tier="MEDIUM",
                ood_status="IN_DOMAIN",
                data_status=DataSufficiencyStatus.DATA_AVAILABLE,
                sample_size=62,
                primary_metric_name="MAE_ratio",
                metric_value=0.134,
            )
            _GLOBAL_VALIDATION_MATRIX.register_cell(
                engine="TacticalFit",
                competition="Serie_A",
                season="2023/2024",
                position="DF",
                role="Wide Centre-Back",
                age_band="25-29",
                confidence_tier="HIGH",
                ood_status="IN_DOMAIN",
                data_status=DataSufficiencyStatus.DATA_AVAILABLE,
                sample_size=45,
                primary_metric_name="Alignment_F1",
                metric_value=0.88,
            )
            _GLOBAL_VALIDATION_MATRIX.register_cell(
                engine="MatchPrediction",
                competition="Ligue_1",
                season="2023/2024",
                position="ALL",
                role="ALL",
                age_band="ALL",
                confidence_tier="LOW",
                ood_status="OOD",
                data_status=DataSufficiencyStatus.LOW_SAMPLE,
                sample_size=12,
                primary_metric_name="Brier_Score",
                metric_value=0.285,
                notes=["High feature divergence in newly promoted teams"],
            )
    return _GLOBAL_VALIDATION_MATRIX
