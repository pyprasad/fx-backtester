from src.broker.ig.ig_market_rules import extract_market_rules
from scripts.place_ig_demo_six_pip_order import build_six_pip_order


def _rules(status="TRADEABLE", minimum=6.0, unit="AMOUNT", min_size=0.04):
    return extract_market_rules({
        "instrument": {
            "epic": "CS.D.USDJPY.TODAY.IP",
            "name": "USD/JPY",
            "expiry": "DFB",
            "unit": unit,
            "currencies": [{"code": "GBP", "isDefault": True}],
        },
        "snapshot": {"marketStatus": status, "delayTime": 0},
        "dealingRules": {
            "minNormalStopOrLimitDistance": {"value": minimum},
            "minDealSize": {"value": min_size},
        },
    })


def test_build_six_pip_order_uses_broker_minimum_size_and_distances():
    order = build_six_pip_order(rules=_rules(), direction="SELL", size=None)

    assert order.validation_status == "READY_FOR_DEMO_DRY_RUN"
    assert order.epic == "CS.D.USDJPY.TODAY.IP"
    assert order.direction == "SELL"
    assert order.size == 0.04
    assert order.stop_distance == 6.0
    assert order.limit_distance == 6.0
    assert order.currency == "GBP"


def test_build_six_pip_order_rejects_when_broker_requires_wider_gap():
    order = build_six_pip_order(rules=_rules(minimum=7.0), direction="BUY", size=0.1)

    assert order.validation_status == "NOT_READY"
    assert "STOP_DISTANCE_BELOW_BROKER_MINIMUM" in order.validation_errors
    assert "LIMIT_DISTANCE_BELOW_BROKER_MINIMUM" in order.validation_errors


def test_build_six_pip_order_rejects_size_below_minimum():
    order = build_six_pip_order(rules=_rules(min_size=0.5), direction="SELL", size=0.1)

    assert order.validation_status == "NOT_READY"
    assert "SIZE_BELOW_BROKER_MINIMUM" in order.validation_errors
