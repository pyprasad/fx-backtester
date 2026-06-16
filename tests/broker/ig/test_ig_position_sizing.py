import pytest

from src.broker.ig.ig_position_sizing import account_balance, dynamic_deal_size


def test_dynamic_deal_size_matches_risk_percent_for_amount_unit():
    size, context = dynamic_deal_size(
        balance=10000,
        risk_percent=0.25,
        stop_distance_pips=6,
        min_deal_size=0.04,
        instrument_unit="AMOUNT",
    )

    assert size == 4.16
    assert context["risk_amount"] == 25
    assert context["raw_deal_size"] == pytest.approx(4.1666666667)


def test_dynamic_deal_size_respects_minimum():
    size, context = dynamic_deal_size(
        balance=100,
        risk_percent=0.25,
        stop_distance_pips=20,
        min_deal_size=0.04,
        instrument_unit="AMOUNT",
    )

    assert size == 0.04
    assert context["raw_deal_size"] == pytest.approx(0.0125)


def test_account_balance_prefers_cash_balance():
    assert account_balance({"balance": {"balance": 100, "available": 90}}) == 100
