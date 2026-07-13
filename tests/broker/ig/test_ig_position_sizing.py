import pytest

from src.broker.ig.ig_position_sizing import account_balance, deal_size_from_contract, dynamic_deal_size, fixed_deal_size


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


def test_account_balance_prefers_available_balance_for_execution_sizing():
    assert account_balance({"balance": {"balance": 100, "available": 90}}) == 90


def test_fixed_deal_size_uses_requested_size_for_amount_unit():
    size, context = fixed_deal_size(
        deal_size=0.5,
        min_deal_size=0.04,
        instrument_unit="AMOUNT",
    )

    assert size == 0.5
    assert context["sizing_mode"] == "fixed_deal_size"
    assert context["minimum_applied"] is False


def test_fixed_deal_size_respects_market_minimum():
    size, context = fixed_deal_size(
        deal_size=0.01,
        min_deal_size=0.04,
        instrument_unit="AMOUNT",
    )

    assert size == 0.04
    assert context["minimum_applied"] is True


def test_deal_size_from_contract_supports_fixed_size_mode():
    size, context = deal_size_from_contract(
        contract={"position_sizing": {"mode": "fixed_deal_size", "fixed_deal_size": 1.0}},
        balance=10000,
        stop_distance_pips=20,
        min_deal_size=0.04,
        instrument_unit="AMOUNT",
    )

    assert size == 1.0
    assert context["sizing_mode"] == "fixed_deal_size"
