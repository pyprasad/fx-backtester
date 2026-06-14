from src.broker.ig.ig_market_rules import extract_market_rules


def _metadata(minimum=2):
    return {
        "instrument": {
            "epic": "CS.D.USDJPY.CFD.IP", "name": "USD/JPY", "expiry": "-",
            "pipSize": 0.01, "currencies": [{"code": "JPY"}],
        },
        "snapshot": {"marketStatus": "TRADEABLE", "delayTime": 0},
        "dealingRules": {"minNormalStopOrLimitDistance": {"value": minimum}},
    }


def test_extracts_usdjpy_rules_and_validates_minimum():
    rules = extract_market_rules(_metadata())
    assert rules.pip_size == 0.01
    assert rules.min_stop_distance_pips == 2
    assert rules.validation(3)["ready"] is True


def test_not_ready_when_broker_minimum_exceeds_strategy_minimum():
    rules = extract_market_rules(_metadata(4))
    assert "BROKER_MIN_STOP_EXCEEDS_STRATEGY_MIN_RISK" in rules.validation(3)["errors"]
