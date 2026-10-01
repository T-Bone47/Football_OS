"""Phase 12 — Market Inefficiency & Value Gap Engine (§12).

Detects structural discrepancies between modelled transfer valuations, peer comparable bands,
and reported market reference points without making speculative price guarantees.

Strict Separation:
  - OBSERVED MARKET DATA: Reported release clause, asking fee, or contract benchmark.
  - MODELLED VALUATION: Machine learning prediction (point estimate + 80% prediction interval).
  - COMPARABLE RANGE: Realized peer transfer benchmarks in same role/age tier.

States:
  NO_SIGNAL, WATCH, POTENTIAL_VALUE_GAP, HIGH_DATA_CONFIDENCE_VALUE_GAP.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.phase12 import MarketOpportunityState
from app.dev_fixtures import dev_seed_enabled


@dataclass
class MarketInefficiencySignal:
    """An analytical market inefficiency signal comparing modelled valuation to market references."""
    signal_id: str = field(default_factory=lambda: f"mkt_gap_{uuid.uuid4().hex[:12]}")
    player_id: str = ""
    player_name: str = ""
    current_club: str = ""
    competition_id: str = "GB-PL"
    position: str = "CB"
    age: int = 22

    # Triple Stream Separation
    observed_market_reference_eur: float = 30_000_000.0  # Reported asking price or release clause
    modelled_valuation_eur: float = 42_000_000.0         # GBR Point Estimate
    modelled_lower_bound_eur: float = 38_000_000.0       # 80% Prediction interval lower bound
    modelled_upper_bound_eur: float = 47_000_000.0       # 80% Prediction interval upper bound
    comparable_range_min_eur: float = 39_000_000.0       # Peer benchmark min
    comparable_range_max_eur: float = 46_000_000.0       # Peer benchmark max

    # Analysis
    raw_value_gap_eur: float = 12_000_000.0              # Modelled - Observed
    value_gap_pct: float = 40.0                          # Gap as % of observed
    opportunity_state: MarketOpportunityState = MarketOpportunityState.POTENTIAL_VALUE_GAP
    confidence: str = "HIGH"                             # HIGH, MODERATE, LOW
    supporting_evidence: list[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["opportunity_state"] = self.opportunity_state.value
        return data


class MarketInefficiencyEngine:
    """Detects and monitors value gaps across the global transfer universe."""

    def __init__(self) -> None:
        self._signals: dict[str, MarketInefficiencySignal] = {}
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            self._seed_default_signals()

    def _seed_default_signals(self) -> None:
        seed = MarketInefficiencySignal(
            signal_id="mkt_gap_inacio_001",
            player_id="cand_inacio",
            player_name="Gonçalo Inácio",
            current_club="Sporting CP",
            competition_id="PT-PL",
            position="CB",
            age=22,
            observed_market_reference_eur=35_000_000.0,
            modelled_valuation_eur=44_500_000.0,
            modelled_lower_bound_eur=40_000_000.0,
            modelled_upper_bound_eur=49_000_000.0,
            comparable_range_min_eur=42_000_000.0,
            comparable_range_max_eur=48_000_000.0,
            raw_value_gap_eur=9_500_000.0,
            value_gap_pct=27.1,
            opportunity_state=MarketOpportunityState.HIGH_DATA_CONFIDENCE_VALUE_GAP,
            confidence="HIGH",
            supporting_evidence=[
                "Reported release clause (€35M) sits below the GBR 80% lower prediction bound (€40M).",
                "Peer comparable tier (U23 Ball Playing CBs) exhibits €42M–€48M transfer realizations.",
                "Contract duration (expires 2027) guarantees club negotiating leverage.",
            ],
        )
        self._signals[seed.player_id] = seed

    def evaluate_opportunity(
        self,
        player_id: str,
        player_name: str,
        current_club: str,
        competition_id: str,
        position: str,
        age: int,
        observed_reference_eur: float,
        modelled_valuation_eur: float,
        lower_bound_eur: float,
        upper_bound_eur: float,
        comparable_min_eur: float,
        comparable_max_eur: float,
    ) -> MarketInefficiencySignal:
        """Calculates value gap and assigns governed opportunity state."""
        gap = modelled_valuation_eur - observed_reference_eur
        gap_pct = (gap / max(observed_reference_eur, 1.0)) * 100.0

        evidence = []
        if gap > 0:
            evidence.append(f"Modelled estimate (€{modelled_valuation_eur/1e6:.1f}M) exceeds observed reference (€{observed_reference_eur/1e6:.1f}M) by {gap_pct:.1f}%.")
        if observed_reference_eur < lower_bound_eur:
            evidence.append(f"Observed reference sits below the 80% conservative lower prediction bound (€{lower_bound_eur/1e6:.1f}M).")

        # Assign state
        if observed_reference_eur < lower_bound_eur and gap_pct >= 20.0:
            state = MarketOpportunityState.HIGH_DATA_CONFIDENCE_VALUE_GAP
            confidence = "HIGH"
        elif gap_pct >= 15.0:
            state = MarketOpportunityState.POTENTIAL_VALUE_GAP
            confidence = "MODERATE"
        elif gap_pct >= 5.0:
            state = MarketOpportunityState.WATCH
            confidence = "MODERATE"
        else:
            state = MarketOpportunityState.NO_SIGNAL
            confidence = "LOW"

        signal = MarketInefficiencySignal(
            player_id=player_id,
            player_name=player_name,
            current_club=current_club,
            competition_id=competition_id,
            position=position,
            age=age,
            observed_market_reference_eur=observed_reference_eur,
            modelled_valuation_eur=modelled_valuation_eur,
            modelled_lower_bound_eur=lower_bound_eur,
            modelled_upper_bound_eur=upper_bound_eur,
            comparable_range_min_eur=comparable_min_eur,
            comparable_range_max_eur=comparable_max_eur,
            raw_value_gap_eur=gap,
            value_gap_pct=gap_pct,
            opportunity_state=state,
            confidence=confidence,
            supporting_evidence=evidence,
        )

        self._signals[player_id] = signal
        return signal

    def get_signal(self, player_id: str) -> MarketInefficiencySignal | None:
        return self._signals.get(player_id)

    def list_signals(self, state: MarketOpportunityState | None = None) -> list[MarketInefficiencySignal]:
        signals = list(self._signals.values())
        if state:
            signals = [s for s in signals if s.opportunity_state == state]
        return signals


market_inefficiency_engine = MarketInefficiencyEngine()
