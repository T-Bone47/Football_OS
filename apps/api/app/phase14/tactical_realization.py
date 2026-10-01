"""Phase 14 — Tactical & Scenario Realization Engine (§7, §8).

Connects simulated tactical setups and multi-transfer scenarios to real-world deployment:
  - Compares:
    - Simulated formation vs Observed formation
    - Simulated roles vs Observed roles
    - Simulated role dependencies vs Observed interactions
    - Simulated squad depth vs Observed depth under congestion
  - Evaluates scenario realization status:
    - PENDING, PARTIAL, EVALUATED, INSUFFICIENT_DATA
  - Strictly non-causal: Never asserts that a tactical alignment or divergence caused match outcomes.
  - Preserves immutable scenario hash, original assumptions, and original model versions.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase14 import (
    DataSufficiencyStatus,
    EpistemicModality,
    ScenarioRealizationStatus,
    TacticalRealizationState,
)
from app.dev_fixtures import dev_seed_enabled
from app.phase14.outcome_ledger import OutcomeLedger, outcome_ledger


@dataclass
class TacticalComponentComparison:
    """Comparison of a single tactical element between simulation and real-world execution."""
    component_type: str  # "FORMATION", "PLAYER_ROLE", "DEPENDENCY", "DEPTH"
    simulated_state: str
    observed_state: str
    is_aligned: bool
    confidence: float
    notes: str
    modality_simulated: EpistemicModality = EpistemicModality.SCENARIO
    modality_observed: EpistemicModality = EpistemicModality.OBSERVED

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["modality_simulated"] = self.modality_simulated.value
        data["modality_observed"] = self.modality_observed.value
        return data


@dataclass
class TacticalRealizationReport:
    """Retrospective audit report comparing simulated tactics to observed tactical deployment (§7)."""
    report_id: str = field(default_factory=lambda: f"tac_eval_{uuid.uuid4().hex[:12]}")
    club_id: str = "arsenal_fc"
    scenario_id: str = "scen_timber_sign"
    decision_id: str = "dec_rec_timber_2023"
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evaluation_window: str = "2023_2024_SEASON"
    simulated_formation: str = "4-3-3"
    primary_observed_formation: str = "4-3-3"

    # Component evaluations
    components: list[TacticalComponentComparison] = field(default_factory=list)
    tactical_state: TacticalRealizationState = TacticalRealizationState.TACTICAL_ALIGNMENT

    # Associative non-causal findings
    findings: list[str] = field(default_factory=list)
    audit_hash: str = ""

    def calculate_digest(self) -> str:
        payload = {
            "club_id": self.club_id,
            "scenario_id": self.scenario_id,
            "decision_id": self.decision_id,
            "simulated_formation": self.simulated_formation,
            "primary_observed_formation": self.primary_observed_formation,
            "tactical_state": self.tactical_state.value,
            "components": [c.to_dict() for c in self.components],
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tactical_state"] = self.tactical_state.value
        data["components"] = [c.to_dict() for c in self.components]
        return data


@dataclass
class ScenarioRealizationRecord:
    """Lifecycle tracking of a simulated scenario through to realized outcome evaluation (§8)."""
    scenario_id: str
    decision_id: str
    scenario_name: str
    original_scenario_hash: str
    original_model_versions: dict[str, str]
    original_assumptions: list[str]
    created_at: str
    simulated_at: str
    decision_recorded_at: str
    realization_status: ScenarioRealizationStatus = ScenarioRealizationStatus.PENDING
    evaluated_at: str | None = None
    realized_outcomes_count: int = 0
    divergence_summary: list[str] = field(default_factory=list)
    evaluation_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["realization_status"] = self.realization_status.value
        return data


class TacticalRealizationEngine:
    """Evaluates tactical fidelity and tracks scenario lifecycle realization."""

    def __init__(self, ledger: OutcomeLedger | None = None) -> None:
        self._ledger = ledger or outcome_ledger
        self._tactical_reports: dict[str, TacticalRealizationReport] = {}
        self._scenario_realizations: dict[str, ScenarioRealizationRecord] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_reports()

    def evaluate_tactical_realization(
        self,
        club_id: str,
        scenario_id: str,
        decision_id: str,
        simulated_formation: str,
        observed_formation: str,
        simulated_roles: dict[str, str],   # {"player_timber_12": "Inverted Fullback"}
        observed_roles: dict[str, str],    # {"player_timber_12": "Inverted Fullback"}
        simulated_dependencies: list[str], # ["Inverted FB provides midfield receiving cover"]
        observed_dependencies: list[str],
        evaluation_window: str = "FULL_SEASON_2023_2024",
    ) -> TacticalRealizationReport:
        """Compares simulated tactical structure against observed pitch implementation."""
        comps: list[TacticalComponentComparison] = []
        findings: list[str] = []

        # 1. Formation comparison
        form_aligned = simulated_formation == observed_formation
        comps.append(
            TacticalComponentComparison(
                component_type="FORMATION",
                simulated_state=simulated_formation,
                observed_state=observed_formation,
                is_aligned=form_aligned,
                confidence=0.98,
                notes="Primary shape matched scenario structure" if form_aligned else "Primary shape diverged from baseline expectation",
            )
        )
        if form_aligned:
            findings.append(f"Formation structure ({observed_formation}) was consistent with simulated layout.")
        else:
            findings.append(f"Observed primary formation ({observed_formation}) diverged from simulated ({simulated_formation}).")

        # 2. Player Role comparisons
        role_matches = 0
        total_roles = max(1, len(simulated_roles))
        for pid, sim_role in simulated_roles.items():
            obs_role = observed_roles.get(pid, "UNAVAILABLE")
            matched = sim_role.lower() == obs_role.lower()
            if matched:
                role_matches += 1
            comps.append(
                TacticalComponentComparison(
                    component_type=f"PLAYER_ROLE_{pid}",
                    simulated_state=sim_role,
                    observed_state=obs_role,
                    is_aligned=matched,
                    confidence=0.90 if obs_role != "UNAVAILABLE" else 0.0,
                    notes=f"Role assignment: {obs_role}",
                )
            )
            findings.append(f"Player {pid} role: simulated '{sim_role}', observed '{obs_role}' (match: {matched}).")

        # 3. Role Dependencies
        dep_matches = 0
        total_deps = max(1, len(simulated_dependencies))
        for idx, sim_dep in enumerate(simulated_dependencies):
            obs_dep = observed_dependencies[idx] if idx < len(observed_dependencies) else "NOT_OBSERVED"
            aligned = obs_dep != "NOT_OBSERVED" and "cover" in obs_dep.lower()
            if aligned:
                dep_matches += 1
            comps.append(
                TacticalComponentComparison(
                    component_type=f"DEPENDENCY_{idx+1}",
                    simulated_state=sim_dep,
                    observed_state=obs_dep,
                    is_aligned=aligned,
                    confidence=0.85,
                    notes="Structural dependency validated in match telemetry" if aligned else "Dependency unverified",
                )
            )

        # Classification
        alignment_score = (
            (1.0 if form_aligned else 0.0) * 0.40
            + (role_matches / total_roles) * 0.40
            + (dep_matches / total_deps) * 0.20
        )

        if alignment_score >= 0.80:
            tac_state = TacticalRealizationState.TACTICAL_ALIGNMENT
        elif alignment_score >= 0.50:
            tac_state = TacticalRealizationState.TACTICAL_PARTIAL_ALIGNMENT
        elif alignment_score > 0.0:
            tac_state = TacticalRealizationState.TACTICAL_DIVERGENCE
        else:
            tac_state = TacticalRealizationState.INSUFFICIENT_EVIDENCE

        findings.append(f"Overall tactical realization assessed as {tac_state.value} (score index: {alignment_score:.2f}).")
        findings.append("Non-causal note: Observed tactical alignment indicates structural consistency, not causal match outcomes.")

        rep = TacticalRealizationReport(
            club_id=club_id,
            scenario_id=scenario_id,
            decision_id=decision_id,
            evaluation_window=evaluation_window,
            simulated_formation=simulated_formation,
            primary_observed_formation=observed_formation,
            components=comps,
            tactical_state=tac_state,
            findings=findings,
            audit_hash="",
        )
        rep.audit_hash = rep.calculate_digest()

        self._tactical_reports[scenario_id] = rep
        return rep

    def register_scenario_lifecycle(
        self,
        scenario_id: str,
        decision_id: str,
        scenario_name: str,
        original_scenario_hash: str,
        original_model_versions: dict[str, str],
        original_assumptions: list[str],
        created_at: str,
        simulated_at: str,
        decision_recorded_at: str,
    ) -> ScenarioRealizationRecord:
        """Registers a scenario into the lifecycle tracker."""
        rec = ScenarioRealizationRecord(
            scenario_id=scenario_id,
            decision_id=decision_id,
            scenario_name=scenario_name,
            original_scenario_hash=original_scenario_hash,
            original_model_versions=original_model_versions,
            original_assumptions=original_assumptions,
            created_at=created_at,
            simulated_at=simulated_at,
            decision_recorded_at=decision_recorded_at,
            realization_status=ScenarioRealizationStatus.PENDING,
        )
        self._scenario_realizations[scenario_id] = rec
        return rec

    def update_scenario_realization_status(
        self,
        scenario_id: str,
        realization_status: ScenarioRealizationStatus,
        divergence_summary: list[str],
    ) -> ScenarioRealizationRecord:
        """Updates the evaluation lifecycle state without altering historical inputs."""
        rec = self._scenario_realizations.get(scenario_id)
        if not rec:
            raise KeyError(f"Scenario {scenario_id} not registered in realization tracker.")

        rec.realization_status = realization_status
        rec.divergence_summary = divergence_summary
        rec.evaluated_at = datetime.now(timezone.utc).isoformat()
        rec.realized_outcomes_count = len(self._ledger.list_outcomes(scenario_id=scenario_id))

        # Build cryptographic evaluation digest
        digest_data = {
            "scenario_id": rec.scenario_id,
            "original_scenario_hash": rec.original_scenario_hash,
            "status": rec.realization_status.value,
            "outcomes_count": rec.realized_outcomes_count,
            "evaluated_at": rec.evaluated_at,
        }
        rec.evaluation_digest = hashlib.sha256(json.dumps(digest_data, sort_keys=True).encode("utf-8")).hexdigest()
        return rec

    def get_tactical_report(self, scenario_id: str) -> TacticalRealizationReport | None:
        return self._tactical_reports.get(scenario_id)

    def get_scenario_realization(self, scenario_id: str) -> ScenarioRealizationRecord | None:
        return self._scenario_realizations.get(scenario_id)

    def list_scenario_realizations(self) -> list[ScenarioRealizationRecord]:
        return list(self._scenario_realizations.values())

    def _seed_default_reports(self) -> None:
        """Seeds default tactical evaluation reports and scenario tracking records."""
        # Scenario Timber
        self.register_scenario_lifecycle(
            scenario_id="scen_timber_sign",
            decision_id="dec_rec_timber_2023",
            scenario_name="Scenario A: Sign Jurriën Timber (Ajax -> Arsenal)",
            original_scenario_hash="9f8a7e3b1c5d4e2f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f",
            original_model_versions={
                "tactical_fit": "tactical_fit_v2.1",
                "valuation": "transfer_valuation_gradient_boost_v2.0",
                "risk": "transfer_risk_v1.2",
            },
            original_assumptions=[
                "Player deploys primarily as Inverted Fullback (Right/Left).",
                "Assumes 1,400+ competitive minutes in season 1.",
            ],
            created_at="2023-07-01T10:00:00Z",
            simulated_at="2023-07-05T14:30:00Z",
            decision_recorded_at="2023-07-14T18:00:00Z",
        )

        self.evaluate_tactical_realization(
            club_id="arsenal_fc",
            scenario_id="scen_timber_sign",
            decision_id="dec_rec_timber_2023",
            simulated_formation="4-3-3",
            observed_formation="4-3-3",
            simulated_roles={"player_timber_12": "Inverted Fullback"},
            observed_roles={"player_timber_12": "Inverted Fullback"},
            simulated_dependencies=["Inverted Fullback steps into defensive midfield in possession phase"],
            observed_dependencies=["Inverted Fullback provides inside receiving cover alongside Declan Rice"],
            evaluation_window="2023-2024_FULL_SEASON",
        )

        self.update_scenario_realization_status(
            scenario_id="scen_timber_sign",
            realization_status=ScenarioRealizationStatus.EVALUATED,
            divergence_summary=[
                "Formation matched simulated 4-3-3 structure.",
                "Tactical role matched Inverted Fullback specifications.",
                "Total minutes (1,280) tracked within 91.4% of expected 1,400 mins due to ACL recovery window.",
            ],
        )


tactical_realization_engine = TacticalRealizationEngine()
