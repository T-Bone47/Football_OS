"""Phase 10 — Persistent Scenarios & Match Scenario Integration (§11, §12).

Supports persistent multi-alternative transfer and squad planning scenarios:
  - Scenario A: sell X / buy Y
  - Scenario B: retain X / buy Y
  - Scenario C: sell X / promote academy player

Strictly distinguishes across all representations:
  - OBSERVED: Verified historical facts (matches played, actual wages, historical fees)
  - MODELLED: Statistical engine inferences (expected valuation, calibrated probability, tactical fit)
  - SCENARIO: Hypothetical simulations conditional on scout assumptions

Truth rules: a scenario computes ARITHMETIC ONLY on what the user entered (net spend, wage delta). Anything that
would need a validated model (squad rating, tactical balance, points, win probability) is None / NOT_MODELLED,
because no validated match-prediction model exists. The previous version returned constants chosen by the sign of
the spend (+1.2 / -0.5 rating, +2.5 balance, +1.8 / -0.8 points) and a formula labelled as a
"calibrated_multinomial_logit_v1" output, with HIGH confidence.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.persistence.factory import get_stores
from app.persistence.stores import CollectionStore
from app.security.tokens import Principal


class DataModality(str, Enum):
    OBSERVED = "OBSERVED"
    MODELLED = "MODELLED"
    SCENARIO = "SCENARIO"


class ScenarioType(str, Enum):
    SELL_BUY = "SELL_BUY"
    RETAIN_BUY = "RETAIN_BUY"
    SELL_PROMOTE = "SELL_PROMOTE"
    CUSTOM = "CUSTOM"


VALID_ACTIONS = ("BUY", "SELL", "RETAIN", "PROMOTE_ACADEMY")
_NOT_MODELLED = {
    "status": "NOT_MODELLED",
    "reason": "No validated match-prediction model exists; no forecast is produced.",
}


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


@dataclass
class ScenarioPlayerMovement:
    """A simulated in/out player movement within a scenario. Fee/wage None = unknown (not zero)."""
    player_id: str
    player_name: str
    action: str  # 'BUY', 'SELL', 'RETAIN', 'PROMOTE_ACADEMY'
    fee_eur: float | None = None
    wage_eur_weekly: float | None = None
    modality: str = DataModality.SCENARIO
    tactical_role: str = ""
    notes: str = ""


@dataclass
class ScenarioSimulationResult:
    """Arithmetic outputs of a scenario. None = not computed / not computable from the inputs."""
    net_transfer_spend_eur: float | None = None
    wage_bill_delta_weekly: float | None = None
    squad_overall_rating_delta: float | None = None
    tactical_balance_delta: float | None = None
    projected_league_points_delta: float | None = None
    match_prediction_impact: dict[str, Any] = field(default_factory=lambda: dict(_NOT_MODELLED))
    confidence: str = "UNASSESSED"
    data_status: str = "ARITHMETIC_ONLY"
    evidence_nodes: list[str] = field(default_factory=list)


@dataclass
class PersistentScenario:
    """Persistent recruitment / squad scenario record (§11)."""
    scenario_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    name: str = ""
    scenario_type: str = ScenarioType.SELL_BUY
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    assumptions: list[str] = field(default_factory=list)
    movements: list[ScenarioPlayerMovement] = field(default_factory=list)
    results: ScenarioSimulationResult = field(default_factory=ScenarioSimulationResult)
    model_versions: dict[str, str] = field(default_factory=dict)  # empty: no model is used
    provenance_hash: str | None = None
    owner_id: str = ""
    organization_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScenarioEngine:
    """Scenario store backed by a CollectionStore so scenarios survive a process restart. Starts empty; nothing is seeded."""

    _COLLECTION = "phase10_scenarios"

    def __init__(self, store: CollectionStore | None = None) -> None:
        self._store = store
        self._scenarios: dict[str, PersistentScenario] = {}
        if store is not None:
            for record in store.list(self._COLLECTION):
                data = record.payload
                movements = [ScenarioPlayerMovement(**m) for m in data.get("movements", [])]
                results = ScenarioSimulationResult(**data.get("results", {}))
                self._scenarios[record.record_id] = PersistentScenario(
                    scenario_id=record.record_id,
                    project_id=data.get("project_id", ""),
                    name=data.get("name", ""),
                    scenario_type=data.get("scenario_type", ScenarioType.SELL_BUY),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    assumptions=data.get("assumptions", []),
                    movements=movements,
                    results=results,
                    model_versions=data.get("model_versions", {}),
                    provenance_hash=data.get("provenance_hash"),
                    owner_id=record.owner_id,
                    organization_id=record.organization_id,
                )

    def _save(self, scenario: PersistentScenario) -> None:
        if self._store is not None:
            self._store.put(self._COLLECTION, scenario.scenario_id, scenario.owner_id, scenario.organization_id, scenario.to_dict())

    @staticmethod
    def _can_see(principal: Principal, scenario: PersistentScenario) -> bool:
        in_org = principal.org_id is not None and scenario.organization_id == principal.org_id
        return in_org or scenario.owner_id == principal.user_id

    def create_scenario(self, project_id: str, data: dict[str, Any], owner_id: str = "", organization_id: str | None = None) -> PersistentScenario:
        if not str(data.get("name") or "").strip():
            raise ValueError("scenario name is required")
        if not owner_id:
            raise ValueError("owner_id is required")
        movements = []
        for m in data.get("movements", []):
            if not str(m.get("player_id") or "").strip() or not str(m.get("player_name") or "").strip():
                raise ValueError("every movement needs player_id and player_name")
            if m.get("action") not in VALID_ACTIONS:
                raise ValueError(f"movement action must be one of {VALID_ACTIONS}")
            movements.append(
                ScenarioPlayerMovement(
                    player_id=m["player_id"],
                    player_name=m["player_name"],
                    action=m["action"],
                    fee_eur=_opt_float(m.get("fee_eur")),
                    wage_eur_weekly=_opt_float(m.get("wage_eur_weekly")),
                    tactical_role=m.get("tactical_role", ""),
                )
            )
        s_id = data.get("scenario_id") or f"scen_{uuid.uuid4().hex[:8]}"
        if s_id in self._scenarios:
            raise ValueError(f"scenario '{s_id}' already exists")
        scenario = PersistentScenario(
            scenario_id=s_id,
            project_id=project_id,
            name=str(data["name"]).strip(),
            scenario_type=data.get("scenario_type", ScenarioType.SELL_BUY),
            assumptions=list(data.get("assumptions", [])),
            movements=movements,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        scenario.results = self.simulate(scenario)
        self._scenarios[s_id] = scenario
        self._save(scenario)
        return scenario

    def get_scenario(self, scenario_id: str) -> PersistentScenario | None:
        return self._scenarios.get(scenario_id)

    def get_scenario_for(self, principal: Principal, scenario_id: str) -> PersistentScenario:
        scenario = self._scenarios.get(scenario_id)
        if scenario is None or not self._can_see(principal, scenario):
            raise KeyError(f"Scenario '{scenario_id}' not found")
        return scenario

    def list_scenarios(self, project_id: str | None = None) -> list[dict[str, Any]]:
        res = list(self._scenarios.values())
        if project_id:
            res = [s for s in res if s.project_id == project_id]
        return [s.to_dict() for s in res]

    def list_scenarios_for(self, principal: Principal, project_id: str | None = None) -> list[dict[str, Any]]:
        return [
            s.to_dict()
            for s in self._scenarios.values()
            if self._can_see(principal, s) and (not project_id or s.project_id == project_id)
        ]

    def simulate(self, scenario: PersistentScenario) -> ScenarioSimulationResult:
        """Sums what the user entered. A missing fee/wage makes the corresponding total unknown (None), not zero."""
        net_spend: float | None = 0.0
        wage_delta: float | None = 0.0
        missing_fee: list[str] = []
        for m in scenario.movements:
            if m.action == "RETAIN":
                continue
            sign = -1.0 if m.action == "SELL" else 1.0
            if m.fee_eur is None:
                net_spend = None
                missing_fee.append(m.player_name)
            elif net_spend is not None:
                net_spend += sign * m.fee_eur
            if m.wage_eur_weekly is None:
                wage_delta = None
            elif wage_delta is not None:
                wage_delta += sign * m.wage_eur_weekly

        evidence = [f"SUPPLIED: {len(scenario.movements)} movement(s) exactly as entered by the user"]
        if net_spend is None:
            evidence.append(f"UNKNOWN: net transfer spend, fee missing for {', '.join(missing_fee)}")
        else:
            evidence.append(f"COMPUTED: net transfer spend EUR {net_spend:,.2f} (sum of supplied fees)")
        evidence.append("NOT_MODELLED: squad rating, tactical balance, league points and match impact (no validated model)")
        return ScenarioSimulationResult(
            net_transfer_spend_eur=net_spend,
            wage_bill_delta_weekly=wage_delta,
            evidence_nodes=evidence,
        )


def _default_engine() -> ScenarioEngine:
    return ScenarioEngine(store=get_stores()[0])


scenario_engine = _default_engine()
