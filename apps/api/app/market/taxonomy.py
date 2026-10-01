"""Controlled Transfer Fee and Market Taxonomy (Phase 4.1D).
Enforces zero fabrication, preserves multi-currency provenance, and provides
strict semantic parsing for transfer fees, statuses, and transaction types.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class TransferFeeStatus(str, Enum):
    """Controlled fee status taxonomy (Phase 4.1D).
    Distinguishes factual fees, press estimates, unverified numbers, and structural deal types.
    """
    KNOWN_FEE = "KNOWN_FEE"                      # Verified factual fee confirmed by official club regulatory filing
    REPORTED_FEE = "REPORTED_FEE"                # Press/provider reported fee; plausible but not regulatory-verified
    ESTIMATED_FEE = "ESTIMATED_FEE"              # Algorithmic or market estimation; never treated as factual
    UNKNOWN_FEE = "UNKNOWN_FEE"                  # Fee took place, amount not disclosed or missing (strictly NOT 0)
    FREE_TRANSFER = "FREE_TRANSFER"              # Out of contract / Bosman / contractual release
    LOAN = "LOAN"                                # Temporary sporting registration loan
    LOAN_WITH_OPTION = "LOAN_WITH_OPTION"        # Temporary loan with purchase option
    LOAN_WITH_OBLIGATION = "LOAN_WITH_OBLIGATION"# Temporary loan with mandatory purchase obligation
    UNDISCLOSED = "UNDISCLOSED"                  # Explicitly confirmed by clubs as undisclosed
    NOT_APPLICABLE = "NOT_APPLICABLE"            # Return from loan, youth promotion, etc.


class TransferType(str, Enum):
    PERMANENT = "PERMANENT"
    LOAN = "LOAN"
    FREE = "FREE"
    RETURN_FROM_LOAN = "RETURN_FROM_LOAN"
    YOUTH_PROMOTION = "YOUTH_PROMOTION"
    UNKNOWN = "UNKNOWN"


class OptionType(str, Enum):
    NONE = "NONE"
    BUY_OPTION = "BUY_OPTION"
    BUY_OBLIGATION = "BUY_OBLIGATION"


class DataQualityStatus(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# Versioned fixed FX conversion rates to EUR for standardized comparisons.
# Preserves original currency and raw amount untouched.
FX_RATES_V1: dict[str, float] = {
    "EUR": 1.0,
    "GBP": 1.17,
    "USD": 0.92,
    "CHF": 1.05,
    "BRL": 0.16,
}


@dataclass(frozen=True)
class ParsedFee:
    fee_value: float | None
    fee_currency: str | None
    fee_status: TransferFeeStatus
    fee_eur_normalized: float | None
    is_loan: bool
    is_permanent: bool
    transfer_type: TransferType
    option_type: OptionType


def normalize_currency(amount: float | None, currency: str | None) -> float | None:
    """Converts amount to normalized EUR using versioned FX rates.
    Never overwrites the original amount or currency.
    """
    if amount is None or currency is None:
        return None
    rate = FX_RATES_V1.get(currency.upper())
    if rate is None:
        return None
    return round(amount * rate, 2)


def parse_fee_string(raw_str: str | None) -> ParsedFee:
    """Deterministic parser for provider fee strings (e.g. '€ 60M', 'Loan', 'Free', 'N/A').
    Enforces Principle 1 (Zero Fabrication) and Principle 7 (Unknown is not Zero).
    """
    if raw_str is None:
        return ParsedFee(
            fee_value=None,
            fee_currency=None,
            fee_status=TransferFeeStatus.UNKNOWN_FEE,
            fee_eur_normalized=None,
            is_loan=False,
            is_permanent=True,
            transfer_type=TransferType.PERMANENT,
            option_type=OptionType.NONE,
        )

    s = raw_str.strip()
    if not s or s.lower() in ("-", "n/a", "none", "unknown", "?"):
        return ParsedFee(
            fee_value=None,
            fee_currency=None,
            fee_status=TransferFeeStatus.UNKNOWN_FEE,
            fee_eur_normalized=None,
            is_loan=False,
            is_permanent=True,
            transfer_type=TransferType.PERMANENT,
            option_type=OptionType.NONE,
        )

    lower = s.lower()

    # 1. Undisclosed
    if "undisclosed" in lower:
        return ParsedFee(
            fee_value=None,
            fee_currency=None,
            fee_status=TransferFeeStatus.UNDISCLOSED,
            fee_eur_normalized=None,
            is_loan=False,
            is_permanent=True,
            transfer_type=TransferType.PERMANENT,
            option_type=OptionType.NONE,
        )

    # 2. Free transfer
    if "free" in lower:
        return ParsedFee(
            fee_value=0.0,
            fee_currency="EUR",
            fee_status=TransferFeeStatus.FREE_TRANSFER,
            fee_eur_normalized=0.0,
            is_loan=False,
            is_permanent=True,
            transfer_type=TransferType.FREE,
            option_type=OptionType.NONE,
        )

    # 3. Back from loan / Return
    if "back" in lower or "return" in lower:
        return ParsedFee(
            fee_value=None,
            fee_currency=None,
            fee_status=TransferFeeStatus.NOT_APPLICABLE,
            fee_eur_normalized=None,
            is_loan=False,
            is_permanent=False,
            transfer_type=TransferType.RETURN_FROM_LOAN,
            option_type=OptionType.NONE,
        )

    # 4. Loan variations
    if "loan" in lower:
        opt_type = OptionType.NONE
        fee_stat = TransferFeeStatus.LOAN
        if "obligation" in lower:
            opt_type = OptionType.BUY_OBLIGATION
            fee_stat = TransferFeeStatus.LOAN_WITH_OBLIGATION
        elif "option" in lower:
            opt_type = OptionType.BUY_OPTION
            fee_stat = TransferFeeStatus.LOAN_WITH_OPTION

        # Check if there is an associated loan fee amount e.g. "€ 5M loan"
        val, curr = _extract_currency_and_value(s)
        eur_norm = normalize_currency(val, curr) if val is not None else None
        return ParsedFee(
            fee_value=val,
            fee_currency=curr,
            fee_status=fee_stat,
            fee_eur_normalized=eur_norm,
            is_loan=True,
            is_permanent=False,
            transfer_type=TransferType.LOAN,
            option_type=opt_type,
        )

    # 5. Numeric currency fee (e.g. '€ 60M', '£ 25M', '$ 12M', '750K €')
    val, curr = _extract_currency_and_value(s)
    if val is not None:
        eur_norm = normalize_currency(val, curr)
        return ParsedFee(
            fee_value=val,
            fee_currency=curr or "EUR",
            fee_status=TransferFeeStatus.REPORTED_FEE,
            fee_eur_normalized=eur_norm,
            is_loan=False,
            is_permanent=True,
            transfer_type=TransferType.PERMANENT,
            option_type=OptionType.NONE,
        )

    # Fallback for unparseable strings: preserve unknown status
    return ParsedFee(
        fee_value=None,
        fee_currency=None,
        fee_status=TransferFeeStatus.UNKNOWN_FEE,
        fee_eur_normalized=None,
        is_loan=False,
        is_permanent=True,
        transfer_type=TransferType.UNKNOWN,
        option_type=OptionType.NONE,
    )


def _extract_currency_and_value(text: str) -> tuple[float | None, str | None]:
    """Extracts numeric value and currency symbol from textual fee description."""
    curr = None
    if "€" in text or "eur" in text.lower():
        curr = "EUR"
    elif "£" in text or "gbp" in text.lower():
        curr = "GBP"
    elif "$" in text or "usd" in text.lower():
        curr = "USD"
    elif "chf" in text.lower():
        curr = "CHF"

    # Match numeric patterns: e.g. "60M", "17.5M", "750K", "10,000,000", "500000"
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*([mMkK]|mio|mil|thousand)?", text)
    if not match:
        return None, curr

    num_str, suffix = match.groups()
    num_str = num_str.replace(",", ".")
    try:
        val = float(num_str)
    except ValueError:
        return None, curr

    if suffix:
        suf = suffix.lower()
        if suf in ("m", "mio", "mil"):
            val *= 1_000_000
        elif suf in ("k", "thousand"):
            val *= 1_000

    return round(val, 2), curr
