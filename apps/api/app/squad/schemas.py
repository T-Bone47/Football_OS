"""Pydantic schemas for Squad Intelligence and Transfer Simulation (Phase 5A)."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class SquadPlayerProfile(BaseModel):
    """Profile of a player within a squad construction context."""
    player_id: UUID
    player_name: str
    age: float | None = None
    nationality: str | None = None
    primary_position: str
    position_group: str  # GK, DEF, MID, ATT
    primary_role: str | None = None
    role_confidence: float | None = None
    tactical_fit_score: float | None = None
    estimated_value_eur: float | None = None
    transfer_risk_score: float | None = None
    transfer_risk_level: str | None = None  # LOW, MODERATE, HIGH, CRITICAL
    is_starter: bool = False
    slot_name: str | None = None  # e.g. GK, LCB, RCB, LB, RB, DM, LCM, RCM, LW, ST, RW


class PositionCoverage(BaseModel):
    """Depth and quality analysis for an individual tactical formation slot."""
    slot_name: str
    position_group: str
    starter: SquadPlayerProfile | None = None
    backups: list[SquadPlayerProfile] = Field(default_factory=list)
    depth_count: int = 0
    coverage_quality: float = 0.0  # [0.0, 1.0]
    coverage_status: str = "THIN"  # SOLID, ADEQUATE, THIN, CRITICAL_GAP


class SquadAnalysisResponse(BaseModel):
    """Comprehensive squad analysis against tactical formation and role profiles."""
    club_id: UUID | None = None
    club_name: str | None = None
    formation: str = "4-3-3"
    total_players: int = 0
    starters_count: int = 0
    backups_count: int = 0
    average_age: float = 0.0
    total_estimated_value_eur: float = 0.0
    squad_quality_score: float = 0.0  # [0.0, 1.0]
    role_coverage_score: float = 0.0  # [0.0, 1.0]
    tactical_fit_score: float = 0.0  # [0.0, 1.0]
    depth_risk_score: float = 0.0  # [0.0, 1.0]
    depth_risk_level: str = "MODERATE"  # LOW, MODERATE, HIGH, CRITICAL
    positions: list[PositionCoverage] = Field(default_factory=list)
    key_gaps: list[str] = Field(default_factory=list)
    key_strengths: list[str] = Field(default_factory=list)
    evaluated_at: datetime


class SquadBuildRequest(BaseModel):
    """Request to analyze or construct a squad."""
    club_id: UUID | None = None
    player_ids: list[UUID] | None = None
    formation: str = "4-3-3"
    tactic_style: str | None = None


class TransferSimulationRequest(BaseModel):
    """Request to model transfer transactions on squad structure."""
    club_id: UUID | None = None
    current_player_ids: list[UUID] | None = None
    formation: str = "4-3-3"
    outgoing_player_ids: list[UUID] = Field(default_factory=list)
    incoming_player_ids: list[UUID] = Field(default_factory=list)


class TransferSimulationImpact(BaseModel):
    """Quantitative impact metrics comparing pre- and post-transfer squad state."""
    delta_squad_quality: float
    delta_average_age: float
    delta_total_value_eur: float
    delta_role_coverage: float
    delta_tactical_fit: float
    delta_depth_risk: float
    summary: str
    recommendations: list[str] = Field(default_factory=list)


class TransferSimulationResponse(BaseModel):
    """Before/after simulation response."""
    before: SquadAnalysisResponse
    after: SquadAnalysisResponse
    outgoing_players: list[SquadPlayerProfile] = Field(default_factory=list)
    incoming_players: list[SquadPlayerProfile] = Field(default_factory=list)
    net_spend_eur: float = 0.0  # incoming total value - outgoing total value
    impact: TransferSimulationImpact
    evaluated_at: datetime
