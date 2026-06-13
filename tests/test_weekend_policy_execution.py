from datetime import datetime, timezone

import polars as pl

from src.execution.tick_execution_engine import execute_signal
from src.strategies.signal import Signal


def _signal(direction):
    timestamp = datetime(2025, 1, 3, 20, 0, tzinfo=timezone.utc)
    return Signal(
        "s", timestamp, timestamp, "USDJPY", direction, "market", 150.0, "4H", "1H", [], {"atr_14": 0.1},
        149.8 if direction == "LONG" else 150.2, 150.4 if direction == "LONG" else 149.6, 1.0,
    )


def _ticks():
    return pl.DataFrame({
        "timestamp_utc": [
            datetime(2025, 1, 3, 20, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, 20, 30, tzinfo=timezone.utc),
            datetime(2025, 1, 3, 20, 31, tzinfo=timezone.utc),
        ],
        "bid": [150.0, 150.05, 150.06], "ask": [150.02, 150.07, 150.08],
        "spread_pips": [2.0, 2.0, 2.0],
    })


def _force_config(config):
    config.execution["slippage_enabled"] = False
    config.weekend_policy["enabled"] = True
    config.weekend_policy["policy_name"] = "force"
    config.weekend_policy["force_close_on_friday"]["enabled"] = True
    config.weekend_policy["force_close_on_friday"]["close_time_utc"] = "20:30"
    return config


def test_force_close_short_uses_ask_and_long_uses_bid(strategy_config):
    config = _force_config(strategy_config)
    short = execute_signal(_signal("SHORT"), _ticks(), config, 10000)
    long = execute_signal(_signal("LONG"), _ticks(), config, 10000)
    assert short.exit_price == 150.07
    assert long.exit_price == 150.05
    assert short.exit_reason == long.exit_reason == "weekend_force_close"
    assert short.weekend_policy_events[0]["event_type"] == "TRADE_FORCE_CLOSED_FRIDAY"


def test_partial_reduce_and_tighten_do_not_repeat(strategy_config):
    config = strategy_config
    config.execution["slippage_enabled"] = False
    config.weekend_policy["enabled"] = True
    config.weekend_policy["reduce_position_before_weekend"]["enabled"] = True
    config.weekend_policy["reduce_position_before_weekend"]["min_open_trade_r_to_apply"] = 0.0
    config.weekend_policy["tighten_stop_before_weekend"]["enabled"] = True
    config.weekend_policy["tighten_stop_before_weekend"]["min_open_trade_r_to_apply"] = 0.0
    trade = execute_signal(_signal("LONG"), _ticks(), config, 10000)
    event_types = [event["event_type"] for event in trade.weekend_policy_events]
    assert event_types.count("TRADE_PARTIALLY_REDUCED_FRIDAY") == 1
    assert event_types.count("TRADE_STOP_TIGHTENED_FRIDAY") <= 1
    assert any(item.get("reason") == "weekend_partial_reduce" for item in trade.partial_exits)


def test_force_close_uses_last_available_friday_tick(strategy_config):
    config = _force_config(strategy_config)
    ticks = pl.DataFrame({
        "timestamp_utc": [
            datetime(2025, 1, 3, 20, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 5, 21, 1, tzinfo=timezone.utc),
        ],
        "bid": [150.0, 151.0], "ask": [150.02, 151.02], "spread_pips": [2.0, 2.0],
    })
    trade = execute_signal(_signal("SHORT"), ticks, config, 10000)
    assert trade.exit_timestamp_utc == datetime(2025, 1, 3, 20, 1, tzinfo=timezone.utc)
    assert trade.exit_price == 150.02
    assert any(
        event["event_type"] == "WEEKEND_CLOSE_USED_LAST_AVAILABLE_FRIDAY_TICK"
        for event in trade.weekend_policy_events
    )
