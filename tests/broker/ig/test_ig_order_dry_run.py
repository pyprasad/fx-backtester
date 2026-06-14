from datetime import datetime, timezone

import yaml

from src.broker.ig.ig_market_rules import extract_market_rules
from src.broker.ig.ig_order_dry_run import build_dry_run_order
from src.broker.ig.ig_rest_client import IGRestClient
from src.broker.ig.models import InternalTick


def _strategy():
    return yaml.safe_load(open("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml"))


def _rules(status="TRADEABLE", minimum=2):
    return extract_market_rules({
        "instrument": {"epic": "USDJPY", "name": "USD/JPY", "expiry": "-", "pipSize": .01},
        "snapshot": {"marketStatus": status}, "dealingRules": {"minNormalStopOrLimitDistance": {"value": minimum}},
    })


def _tick(hour=12, delayed=False, spread_pips=1):
    ask = 150 + spread_pips * 0.01
    return InternalTick(
        datetime(2026, 6, 15, hour, tzinfo=timezone.utc),
        150, ask, (150 + ask) / 2, spread_pips, "test", "USDJPY", delayed,
        raw={"normalization_price_scale_divisor": 1.0},
    )


def _order(**kwargs):
    tick = kwargs.pop("tick", _tick())
    signal = kwargs.pop("signal", {"direction": "SELL", "stop_price": 150.03, "target_price": 149.88})
    return build_dry_run_order(
        signal=signal, market_rules=kwargs.pop("rules", _rules()), strategy=_strategy(),
        latest_tick=tick, size=1, **kwargs,
    )


def test_builds_valid_sell_dry_run_and_rest_has_no_order_method():
    order = _order()
    assert order.validation_status == "READY_FOR_DEMO_DRY_RUN"
    assert order.dry_run_only is True
    assert not hasattr(IGRestClient, "create_position")


def test_rejects_buy_tiny_risk_broker_minimum_delayed_closed_and_open_position():
    assert "ONLY_SELL_ALLOWED" in _order(signal={"direction": "BUY", "stop_price": 149.97, "target_price": 150.1}).validation_errors
    assert "INITIAL_RISK_BELOW_SELECTED_MINIMUM" in _order(signal={"direction": "SELL", "stop_price": 150.02, "target_price": 149.9}).validation_errors
    assert "STOP_DISTANCE_BELOW_BROKER_MINIMUM" in _order(rules=_rules(minimum=4)).validation_errors
    assert "DELAYED_PRICE" in _order(tick=_tick(delayed=True)).validation_errors
    assert "MARKET_NOT_TRADEABLE" in _order(rules=_rules(status="CLOSED")).validation_errors
    assert "ENTRY_SPREAD_ABOVE_STRATEGY_MAXIMUM" in _order(tick=_tick(spread_pips=7)).validation_errors
    unconfirmed_tick = _tick()
    unconfirmed_tick.raw = {}
    assert "PRICE_SCALING_UNCONFIRMED" in _order(tick=unconfirmed_tick).validation_errors
    assert "MAX_OPEN_POSITIONS_REACHED" in _order(open_positions=1).validation_errors


def test_rejects_after_uk_cutoff():
    assert "ENTRY_AFTER_UK_CUTOFF" in _order(tick=_tick(hour=21)).validation_errors
