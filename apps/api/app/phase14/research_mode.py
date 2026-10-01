"""Phase 14 — Governed Research Workspace Engine (§21).

Enables exploratory analytical investigations into decision dynamics and model behavior:
  - Supports investigations into:
    - Player career trajectories
    - Recruitment outcome distributions
    - Tactical realization fidelity
    - Prediction calibration reliability
    - Valuation divergence and market drift
  - Strict Epistemic Modality Separation:
    - OBSERVED (empirical match and market telemetry)
    - MODELLED (algorithmic predictions and fit scores)
    - ANALYSIS (structured delta and correlation calculations)
    - HYPOTHESIS (unverified analytical conjectures)
  - Core Epistemic Doctrine: A hypothesis is strictly distinct from observed facts.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase14 import EpistemicModality


@dataclass
class ResearchItem:
    """Individual item within a research dossier with explicit epistemic tagging (§21)."""
    item_id: str = field(default_factory=lambda: f"item_{uuid.uuid4().hex[:8]}")
    title: str = ""
    modality: EpistemicModality = EpistemicModality.OBSERVED
    content: str = ""
    evidence_source: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["modality"] = self.modality.value
        return data


@dataclass
class ResearchDossier:
    """A governed research study snapshot capturing hypotheses, evidence, and conclusions (§21)."""
    dossier_id: str = field(default_factory=lambda: f"res_{uuid.uuid4().hex[:12]}")
    topic: str = "Tactical Inversion Stability in Transition Phases"
    hypothesis: str = "Inverted Fullbacks stepping into midfield reduce opponent counterattack xG by >15%."
    created_by: str = "analyst_research_lead"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    items: list[ResearchItem] = field(default_factory=list)
    validation_status: str = "UNDER_INVESTIGATION"  # "CONFIRMED_BY_EVIDENCE", "REFUTED_BY_EVIDENCE", "UNDER_INVESTIGATION", "INSUFFICIENT_DATA"
    conclusion: str = ""
    digest: str = ""

    def calculate_digest(self) -> str:
        payload = {
            "dossier_id": self.dossier_id,
            "topic": self.topic,
            "hypothesis": self.hypothesis,
            "items": [i.to_dict() for i in self.items],
            "validation_status": self.validation_status,
            "conclusion": self.conclusion,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        self.digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return self.digest

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [i.to_dict() for i in self.items]
        return data


class ResearchWorkspaceEngine:
    """Governed research engine maintaining epistemic distinction between hypothesis and evidence."""

    def __init__(self) -> None:
        self._dossiers: dict[str, ResearchDossier] = {}
        self._seed_default_dossiers()

    def create_research_dossier(
        self,
        topic: str,
        hypothesis: str,
        items: list[dict[str, Any]],
        created_by: str = "analyst_lead",
    ) -> ResearchDossier:
        """Creates a new research dossier with explicit epistemic tagging."""
        research_items: list[ResearchItem] = []
        for itm in items:
            modality_str = itm.get("modality", "HYPOTHESIS")
            mod = EpistemicModality[modality_str] if modality_str in EpistemicModality.__members__ else EpistemicModality.HYPOTHESIS
            research_items.append(
                ResearchItem(
                    title=itm.get("title", ""),
                    modality=mod,
                    content=itm.get("content", ""),
                    evidence_source=itm.get("evidence_source", "manual_input"),
                    confidence=float(itm.get("confidence", 0.8)),
                )
            )

        # Check evidence distribution
        has_observed = any(i.modality == EpistemicModality.OBSERVED for i in research_items)
        status = "UNDER_INVESTIGATION" if has_observed else "INSUFFICIENT_DATA"

        dossier = ResearchDossier(
            topic=topic,
            hypothesis=hypothesis,
            created_by=created_by,
            items=research_items,
            validation_status=status,
            conclusion="Investigation ongoing. Epistemic note: Hypotheses must not be treated as empirical facts.",
        )
        dossier.calculate_digest()
        self._dossiers[dossier.dossier_id] = dossier
        return dossier

    def get_dossier(self, dossier_id: str) -> ResearchDossier | None:
        return self._dossiers.get(dossier_id)

    def list_dossiers(self) -> list[ResearchDossier]:
        return list(self._dossiers.values())

    def _seed_default_dossiers(self) -> None:
        """Seeds benchmark research dossiers for tactical inversion and valuation divergence."""
        items = [
            {
                "title": "Empirical Inverted Fullback Pitch Usage",
                "modality": "OBSERVED",
                "content": "Jurriën Timber spent 42.1% of in-possession touches inside central midfield third.",
                "evidence_source": "wyscout_epl_2023_2024_tracking",
                "confidence": 0.98,
            },
            {
                "title": "Modelled Defensive Impact on Transitions",
                "modality": "MODELLED",
                "content": "Tactical fit model v2.1 estimated +0.14 improvement in counter-press recovery speed.",
                "evidence_source": "tactical_fit_v2.1",
                "confidence": 0.85,
            },
            {
                "title": "Working Hypothesis on Structural Solidity",
                "modality": "HYPOTHESIS",
                "content": "Dual-pivot rest defense directly prevents opposition half-space central progression.",
                "evidence_source": "tactical_research_group",
                "confidence": 0.60,
            },
        ]
        self.create_research_dossier(
            topic="Inverted Fullback Central Progression Stability",
            hypothesis="Central progression via inverted fullbacks maintains superior transition protection than wide overlaps.",
            items=items,
            created_by="tactical_director",
        )


research_workspace_engine = ResearchWorkspaceEngine()
