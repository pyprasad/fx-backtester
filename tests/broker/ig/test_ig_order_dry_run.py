from datetime import datetime, timezone

import yaml

from src.broker.ig.ig_market_rules import extract_market_rules
from src.broker.ig.ig_order_dry_run import build_dry_run_order
from src.broker.ig.ig_rest_client import IGRestClient
from src.broker.ig.models import InternalTick


def _strategy():
    return yaml.safe_load(open("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml"))


def _strict_strategy():
    return yaml.safe_load(open("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml"))


def _intraday_strategy():
    return yaml.safe_load(open("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_long_short_demo.yaml"))


def _six_pip_strategy():
    return yaml.safe_load(open("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_6pip_attached_demo.yaml"))


def _gbpusd_six_pip_strategy():
    return yaml.safe_load(open("config/strategies/gbpusd_fx_swing_trend_reclaim_v1_intraday_6pip_attached_demo.yaml"))


def _rules(status="TRADEABLE", minimum=2):
    return extract_market_rules({
        "instrument": {"epic": "USDJPY", "name": "USD/JPY", "expiry": "-", "pipSize": .01},
        "snapshot": {"marketStatus": status}, "dealingRules": {"minNormalStopOrLimitDistance": {"value": minimum}},
    })


def _gbpusd_rules(status="TRADEABLE", minimum=6):
    return extract_market_rules({
        "instrument": {
            "epic": "CS.D.GBPUSD.TODAY.IP",
            "name": "GBP/USD",
            "expiry": "-",
            "pipSize": .0001,
            "currencies": [{"code": "GBP", "isDefault": True}],
        },
        "snapshot": {"marketStatus": status},
        "dealingRules": {"minNormalStopOrLimitDistance": {"value": minimum}},
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
        signal=signal, market_rules=kwargs.pop("rules", _rules()),
        strategy=kwargs.pop("strategy", _strategy()),
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
    errors = _order(tick=_tick(hour=21)).validation_errors
    assert "ENTRY_AFTER_UK_CUTOFF" in errors
    assert "OUTSIDE_ALLOWED_LONDON_SESSION" in errors


def test_rejects_outside_backtested_london_sessions():
    errors = _order(tick=_tick(hour=17)).validation_errors

    assert "OUTSIDE_ALLOWED_LONDON_SESSION" in errors
    assert "ENTRY_AFTER_UK_CUTOFF" not in errors


def test_strict_combined_demo_accepts_tokyo_session_and_rejects_spread_ratio():
    strategy = _strict_strategy()

    tokyo_order = _order(strategy=strategy, tick=_tick(hour=0, spread_pips=0.5))
    assert tokyo_order.validation_status == "READY_FOR_DEMO_DRY_RUN"

    wide_spread_errors = _order(strategy=strategy, tick=_tick(hour=0, spread_pips=1.0)).validation_errors
    assert "SPREAD_TO_RISK_RATIO_ABOVE_SELECTED_MAXIMUM" in wide_spread_errors

    session_errors = _order(strategy=strategy, tick=_tick(hour=22, spread_pips=0.5)).validation_errors
    assert "OUTSIDE_ALLOWED_ENTRY_SESSION" in session_errors


def test_intraday_long_short_demo_accepts_buy_and_sell_directions():
    strategy = _intraday_strategy()

    sell = _order(
        strategy=strategy,
        tick=_tick(hour=8, spread_pips=0.5),
        signal={"direction": "SELL", "stop_price": 150.07, "target_price": 149.70},
    )
    assert sell.validation_status == "READY_FOR_DEMO_DRY_RUN"

    buy = _order(
        strategy=strategy,
        tick=_tick(hour=8, spread_pips=0.5),
        signal={"direction": "BUY", "stop_price": 149.94, "target_price": 150.40},
    )
    assert buy.validation_status == "READY_FOR_DEMO_DRY_RUN"


def test_gbpusd_demo_order_uses_gbpusd_epic_from_market_rules():
    tick = InternalTick(
        datetime(2026, 6, 15, 8, tzinfo=timezone.utc),
        1.2500, 1.25008, 1.25004, 0.8, "test", "CS.D.GBPUSD.TODAY.IP", False,
        raw={"normalization_price_scale_divisor": 1.0},
    )

    order = _order(
        strategy=_gbpusd_six_pip_strategy(),
        rules=_gbpusd_rules(),
        tick=tick,
        signal={"direction": "BUY", "stop_price": 1.2492, "target_price": 1.25069},
    )

    assert order.validation_status == "READY_FOR_DEMO_DRY_RUN"
    assert order.epic == "CS.D.GBPUSD.TODAY.IP"
    assert order.currency == "GBP"
    assert order.payload()["epic"] == "CS.D.GBPUSD.TODAY.IP"


def test_intraday_long_short_demo_validates_buy_stop_and_target_side():
    strategy = _intraday_strategy()

    errors = _order(
        strategy=strategy,
        tick=_tick(hour=8, spread_pips=0.5),
        signal={"direction": "BUY", "stop_price": 150.08, "target_price": 150.00},
    ).validation_errors

    assert "LONG_STOP_MUST_BE_BELOW_ENTRY" in errors
    assert "LONG_TARGET_MUST_BE_ABOVE_ENTRY" in errors


def test_six_pip_demo_contract_accepts_exact_ig_minimum_attached_limit_distance():
    strategy = _six_pip_strategy()
    rules = _rules(minimum=6)

    sell = _order(
        strategy=strategy,
        rules=rules,
        tick=_tick(hour=8, spread_pips=0.5),
        signal={"direction": "SELL", "stop_price": 150.07, "target_price": 149.94},
    )
    buy = _order(
        strategy=strategy,
        rules=rules,
        tick=_tick(hour=8, spread_pips=0.5),
        signal={"direction": "BUY", "stop_price": 149.94, "target_price": 150.065},
    )

    assert sell.validation_status == "READY_FOR_DEMO_DRY_RUN"
    assert sell.limit_distance == 6.0
    assert sell.stop_distance == 7.0
    assert buy.validation_status == "READY_FOR_DEMO_DRY_RUN"
    assert buy.limit_distance == 6.0
    assert buy.stop_distance == 6.5
