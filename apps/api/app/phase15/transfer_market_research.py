"""Transfer Market Research for Phase 15.

Studies:
- Valuation residuals (realized fee vs pre-deal model projection)
- Fee distributions by age, position, and competition
- Source vs destination league market premiums
- Market segment efficiency

Preserves strict 9-state Fee Taxonomy:
- KNOWN_FEE
- REPORTED_FEE
- ESTIMATED_FEE
- UNKNOWN_FEE
- FREE_TRANSFER
- LOAN
- LOAN_WITH_OPTION
- LOAN_WITH_OBLIGATION
- UNDISCLOSED

CRITICAL RULE:
- NEVER convert UNKNOWN_FEE or UNDISCLOSED into 0.0.
- FREE_TRANSFER has fee 0.0; UNKNOWN_FEE has fee None.
"""

from typing import Any
from pydantic import BaseModel, Field
from app.phase15 import FeeTaxonomy
from app.dev_fixtures import dev_seed_enabled


class TransferMarketRecord(BaseModel):
    transfer_id: str
    player_id: str
    selling_club: str
    buying_club: str
    source_competition: str
    destination_competition: str
    transfer_date: str
    fee_type: FeeTaxonomy
    realized_fee_eur: float | None = None  # None if UNKNOWN_FEE or UNDISCLOSED
    modelled_valuation_eur: float | None = None
    valuation_residual_eur: float | None = None  # realized - modelled
    valuation_residual_pct: float | None = None
    age_at_transfer: int
    position: str
    is_valid_for_residuals: bool


class MarketResidualSlice(BaseModel):
    slice_name: str
    sample_size: int
    mean_residual_pct: float
    median_residual_pct: float
    overestimation_frequency: float  # fraction where modelled > realized
    underestimation_frequency: float  # fraction where realized > modelled
    p10_residual: float
    p90_residual: float
    fee_completeness_ratio: float


class TransferMarketResearchEngine:
    """Computes transfer market residuals and distributions under strict fee taxonomy governance."""

    def __init__(self) -> None:
        self._records: list[TransferMarketRecord] = []

    def record_transfer(
        self,
        transfer_id: str,
        player_id: str,
        selling_club: str,
        buying_club: str,
        source_competition: str,
        destination_competition: str,
        transfer_date: str,
        fee_type: FeeTaxonomy,
        realized_fee_eur: float | None,
        modelled_valuation_eur: float | None,
        age_at_transfer: int,
        position: str,
    ) -> TransferMarketRecord:
        # Zero fabrication check: UNKNOWN_FEE or UNDISCLOSED must NOT be coerced to 0.0
        if fee_type in (FeeTaxonomy.UNKNOWN_FEE, FeeTaxonomy.UNDISCLOSED):
            if realized_fee_eur == 0.0:
                # Force None to adhere to anti-fabrication doctrine
                realized_fee_eur = None

        residual_eur: float | None = None
        residual_pct: float | None = None
        is_valid = False

        if realized_fee_eur is not None and modelled_valuation_eur is not None and modelled_valuation_eur > 0:
            residual_eur = round(realized_fee_eur - modelled_valuation_eur, 2)
            residual_pct = round((residual_eur / modelled_valuation_eur) * 100, 2)
            is_valid = True

        rec = TransferMarketRecord(
            transfer_id=transfer_id,
            player_id=player_id,
            selling_club=selling_club,
            buying_club=buying_club,
            source_competition=source_competition,
            destination_competition=destination_competition,
            transfer_date=transfer_date,
            fee_type=fee_type,
            realized_fee_eur=realized_fee_eur,
            modelled_valuation_eur=modelled_valuation_eur,
            valuation_residual_eur=residual_eur,
            valuation_residual_pct=residual_pct,
            age_at_transfer=age_at_transfer,
            position=position,
            is_valid_for_residuals=is_valid,
        )

        self._records.append(rec)
        return rec

    def compute_residual_slice(
        self,
        slice_name: str,
        filter_fn: Any = None,
    ) -> MarketResidualSlice:
        eligible = self._records if filter_fn is None else [r for r in self._records if filter_fn(r)]
        valid_residuals = [r.valuation_residual_pct for r in eligible if r.is_valid_for_residuals and r.valuation_residual_pct is not None]

        n_total = len(eligible)
        n_valid = len(valid_residuals)

        if n_valid == 0:
            return MarketResidualSlice(
                slice_name=slice_name,
                sample_size=0,
                mean_residual_pct=0.0,
                median_residual_pct=0.0,
                overestimation_frequency=0.0,
                underestimation_frequency=0.0,
                p10_residual=0.0,
                p90_residual=0.0,
                fee_completeness_ratio=0.0,
            )

        sorted_res = sorted(valid_residuals)
        mean_res = sum(sorted_res) / n_valid
        median_res = sorted_res[n_valid // 2]
        over_freq = len([x for x in sorted_res if x < 0]) / n_valid
        under_freq = len([x for x in sorted_res if x > 0]) / n_valid
        p10 = sorted_res[int(0.10 * n_valid)]
        p90 = sorted_res[min(int(0.90 * n_valid), n_valid - 1)]

        return MarketResidualSlice(
            slice_name=slice_name,
            sample_size=n_valid,
            mean_residual_pct=round(mean_res, 2),
            median_residual_pct=round(median_res, 2),
            overestimation_frequency=round(over_freq, 3),
            underestimation_frequency=round(under_freq, 3),
            p10_residual=round(p10, 2),
            p90_residual=round(p90, 2),
            fee_completeness_ratio=round(n_valid / max(n_total, 1), 3),
        )

    def list_records(self) -> list[TransferMarketRecord]:
        return list(self._records)


_GLOBAL_TRANSFER_ENGINE: TransferMarketResearchEngine | None = None


def get_transfer_market_engine() -> TransferMarketResearchEngine:
    global _GLOBAL_TRANSFER_ENGINE
    if _GLOBAL_TRANSFER_ENGINE is None:
        _GLOBAL_TRANSFER_ENGINE = TransferMarketResearchEngine()
        if dev_seed_enabled():  # demo fixtures only (DEV_SEED)
            # Seed diverse transfers respecting fee taxonomy
            _GLOBAL_TRANSFER_ENGINE.record_transfer(
                transfer_id="tr_2023_001",
                player_id="ply_declan_rice",
                selling_club="West Ham",
                buying_club="Arsenal",
                source_competition="EPL",
                destination_competition="EPL",
                transfer_date="2023-07-15",
                fee_type=FeeTaxonomy.KNOWN_FEE,
                realized_fee_eur=116000000.0,
                modelled_valuation_eur=98000000.0,
                age_at_transfer=24,
                position="DM",
            )
            _GLOBAL_TRANSFER_ENGINE.record_transfer(
                transfer_id="tr_2023_002",
                player_id="ply_free_agent",
                selling_club="Paris Saint-Germain",
                buying_club="Real Madrid",
                source_competition="Ligue_1",
                destination_competition="La_Liga",
                transfer_date="2024-07-01",
                fee_type=FeeTaxonomy.FREE_TRANSFER,
                realized_fee_eur=0.0,
                modelled_valuation_eur=180000000.0,
                age_at_transfer=25,
                position="FW",
            )
            _GLOBAL_TRANSFER_ENGINE.record_transfer(
                transfer_id="tr_2023_003",
                player_id="ply_undisclosed_talent",
                selling_club="Sporting CP",
                buying_club="Chelsea",
                source_competition="Liga_Portugal",
                destination_competition="EPL",
                transfer_date="2023-08-20",
                fee_type=FeeTaxonomy.UNDISCLOSED,
                realized_fee_eur=None,  # NEVER 0.0
                modelled_valuation_eur=22000000.0,
                age_at_transfer=20,
                position="CM",
            )
    return _GLOBAL_TRANSFER_ENGINE
