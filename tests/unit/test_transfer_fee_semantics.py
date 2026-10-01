"""Unit tests for Transfer Fee Semantics, Taxonomy, and Currency Preservation (Phase 4.1D).
"""
import pytest

from app.market.taxonomy import (
    DataQualityStatus,
    OptionType,
    TransferFeeStatus,
    TransferType,
    normalize_currency,
    parse_fee_string,
)


def test_known_or_reported_fees():
    # Euro Millions
    p1 = parse_fee_string("€ 60M")
    assert p1.fee_value == 60_000_000.0
    assert p1.fee_currency == "EUR"
    assert p1.fee_status == TransferFeeStatus.REPORTED_FEE
    assert p1.fee_eur_normalized == 60_000_000.0
    assert p1.is_permanent is True
    assert p1.is_loan is False

    # Decimal Millions
    p2 = parse_fee_string("€ 17.5M")
    assert p2.fee_value == 17_500_000.0
    assert p2.fee_currency == "EUR"
    assert p2.fee_eur_normalized == 17_500_000.0

    # Thousands
    p3 = parse_fee_string("€ 700K")
    assert p3.fee_value == 700_000.0
    assert p3.fee_currency == "EUR"
    assert p3.fee_eur_normalized == 700_000.0


def test_multi_currency_preservation():
    # British Pounds
    p_gbp = parse_fee_string("£ 25M")
    assert p_gbp.fee_value == 25_000_000.0
    assert p_gbp.fee_currency == "GBP"
    # Preserves original GBP value untouched, calculates normalized EUR
    assert p_gbp.fee_eur_normalized == 25_000_000.0 * 1.17

    # US Dollars
    p_usd = parse_fee_string("$ 10M")
    assert p_usd.fee_value == 10_000_000.0
    assert p_usd.fee_currency == "USD"
    assert p_usd.fee_eur_normalized == 10_000_000.0 * 0.92


def test_free_transfer_semantics():
    p_free = parse_fee_string("Free")
    assert p_free.fee_status == TransferFeeStatus.FREE_TRANSFER
    assert p_free.fee_value == 0.0
    assert p_free.transfer_type == TransferType.FREE
    assert p_free.is_permanent is True
    assert p_free.is_loan is False


def test_unknown_fee_is_not_zero():
    """Principle 7: UNKNOWN IS NOT ZERO.
    An unknown or missing fee must NEVER be recorded as 0.0.
    """
    for raw in [None, "", " - ", "N/A", "Unknown", "?"]:
        p_unknown = parse_fee_string(raw)
        assert p_unknown.fee_status == TransferFeeStatus.UNKNOWN_FEE
        assert p_unknown.fee_value is None
        assert p_unknown.fee_value != 0.0
        assert p_unknown.fee_eur_normalized is None


def test_undisclosed_fee():
    p_undisc = parse_fee_string("Undisclosed")
    assert p_undisc.fee_status == TransferFeeStatus.UNDISCLOSED
    assert p_undisc.fee_value is None
    assert p_undisc.fee_value != 0.0


def test_loan_semantics():
    # Pure Loan
    p_loan = parse_fee_string("Loan")
    assert p_loan.fee_status == TransferFeeStatus.LOAN
    assert p_loan.is_loan is True
    assert p_loan.is_permanent is False
    assert p_loan.transfer_type == TransferType.LOAN
    assert p_loan.option_type == OptionType.NONE

    # Loan with option
    p_opt = parse_fee_string("Loan with option")
    assert p_opt.fee_status == TransferFeeStatus.LOAN_WITH_OPTION
    assert p_opt.is_loan is True
    assert p_opt.is_permanent is False
    assert p_opt.option_type == OptionType.BUY_OPTION

    # Loan with obligation
    p_ob = parse_fee_string("Loan with obligation")
    assert p_ob.fee_status == TransferFeeStatus.LOAN_WITH_OBLIGATION
    assert p_ob.is_loan is True
    assert p_ob.is_permanent is False
    assert p_ob.option_type == OptionType.BUY_OBLIGATION

    # Loan with fee
    p_fee_loan = parse_fee_string("€ 4M loan")
    assert p_fee_loan.is_loan is True
    assert p_fee_loan.fee_value == 4_000_000.0
    assert p_fee_loan.fee_currency == "EUR"


def test_return_from_loan():
    p_ret = parse_fee_string("Back from loan")
    assert p_ret.transfer_type == TransferType.RETURN_FROM_LOAN
    assert p_ret.fee_status == TransferFeeStatus.NOT_APPLICABLE
    assert p_ret.fee_value is None
    assert p_ret.is_loan is False
    assert p_ret.is_permanent is False


def test_currency_normalizer():
    assert normalize_currency(100.0, "EUR") == 100.0
    assert normalize_currency(100.0, "GBP") == 117.0
    assert normalize_currency(100.0, "USD") == 92.0
    assert normalize_currency(None, "EUR") is None
    assert normalize_currency(100.0, None) is None
    assert normalize_currency(100.0, "XYZ") is None
