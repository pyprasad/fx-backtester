from datetime import datetime, timezone

import polars as pl

from src.execution.tick_execution_engine import evaluate_executable_entry_guardrail, execute_signal
from src.strategies.signal import Signal


def _signal(direction):
    price = 103.10
    return Signal(
        "s", datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc),
        datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc), "USDJPY", direction, "market",
        price, "4H", "1H", [], {}, 103.00 if direction == "LONG" else 103.20,
        103.50 if direction == "LONG" else 102.50, 2.0,
    )


def test_long_enters_ask_and_short_enters_bid(ticks, strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    long = execute_signal(_signal("LONG"), ticks.sort("timestamp_utc"), strategy_config, 10000)
    short = execute_signal(_signal("SHORT"), ticks.sort("timestamp_utc"), strategy_config, 10000)
    assert long.entry_price == 103.12
    assert short.entry_price == 103.10
    assert long.exit_price == 103.12
    assert short.exit_price == 103.14


def test_short_stop_triggers_when_ask_equals_float_noisy_stop(ticks, strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    signal = _signal("SHORT")
    signal.proposed_stop = 103.14000000000003
    trade = execute_signal(signal, ticks.sort("timestamp_utc"), strategy_config, 10000)
    assert trade.exit_timestamp_utc == ticks.sort("timestamp_utc")["timestamp_utc"][-1]
    assert trade.exit_reason == "stop_loss"


def test_executable_entry_guardrail_rejects_actual_tiny_risk(ticks, strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    signal = _signal("SHORT")
    signal.proposed_stop = 103.105

    decision = evaluate_executable_entry_guardrail(
        signal, ticks.sort("timestamp_utc"), strategy_config
    )

    assert decision.initial_risk_pips == 0.5
    assert "REJECT_BELOW_MIN_INITIAL_RISK_PIPS" in decision.rejection_reasons


def test_fixed_take_profit_short_uses_ask_side(strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    strategy_config.exit["fixed_take_profit"] = {
        "enabled": True,
        "target_pips": 4.0,
        "execution_mode": "attached_limit",
        "disable_partial_take_profit": True,
        "disable_move_stop_to_breakeven": True,
        "disable_runner": True,
    }
    signal = Signal(
        "s", datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc),
        datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc), "USDJPY", "SHORT", "market",
        150.0, "4H", "1H", [], {}, 150.20, 149.50, 2.0,
    )
    ticks = pl.DataFrame({
        "timestamp_utc": [
            datetime(2021, 1, 4, 9, 0, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 1, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 2, tzinfo=timezone.utc),
        ],
        "bid": [150.00, 149.95, 149.94],
        "ask": [150.02, 149.97, 149.96],
        "spread_pips": [2.0, 2.0, 2.0],
    })

    trade = execute_signal(signal, ticks, strategy_config, 10000)

    assert trade.exit_reason == "take_profit"
    assert trade.entry_price == 150.00
    assert trade.target_price == 149.96
    assert trade.exit_timestamp_utc == datetime(2021, 1, 4, 9, 2, tzinfo=timezone.utc)
    assert trade.exit_price == 149.96
    assert trade.partial_exits == []
    assert trade.breakeven_moved is False
    assert trade.notes == "fixed_take_profit_pips=4.0;fixed_take_profit_execution_mode=attached_limit"


def test_fixed_take_profit_long_uses_bid_side(strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    strategy_config.entry["long"]["enabled"] = True
    strategy_config.exit["fixed_take_profit"] = {
        "enabled": True,
        "target_pips": 3.0,
        "execution_mode": "attached_limit",
        "disable_partial_take_profit": True,
        "disable_move_stop_to_breakeven": True,
        "disable_runner": True,
    }
    signal = Signal(
        "s", datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc),
        datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc), "USDJPY", "LONG", "market",
        150.0, "4H", "1H", [], {}, 149.80, 150.50, 2.0,
    )
    ticks = pl.DataFrame({
        "timestamp_utc": [
            datetime(2021, 1, 4, 9, 0, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 1, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 2, tzinfo=timezone.utc),
        ],
        "bid": [150.00, 150.02, 150.05],
        "ask": [150.02, 150.04, 150.07],
        "spread_pips": [2.0, 2.0, 2.0],
    })

    trade = execute_signal(signal, ticks, strategy_config, 10000)

    assert trade.exit_reason == "take_profit"
    assert trade.entry_price == 150.02
    assert trade.target_price == 150.05
    assert trade.exit_timestamp_utc == datetime(2021, 1, 4, 9, 2, tzinfo=timezone.utc)
    assert trade.exit_price == 150.05


def test_fixed_take_profit_guardrail_uses_absolute_target_distance(ticks, strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    strategy_config.exit["fixed_take_profit"] = {
        "enabled": True,
        "target_pips": 1.0,
        "execution_mode": "attached_limit",
        "disable_partial_take_profit": True,
        "disable_move_stop_to_breakeven": True,
        "disable_runner": True,
    }
    signal = _signal("SHORT")

    decision = evaluate_executable_entry_guardrail(signal, ticks.sort("timestamp_utc"), strategy_config)

    assert "REJECT_BELOW_BROKER_MIN_TP_DISTANCE" in decision.rejection_reasons


def test_fixed_take_profit_managed_market_close_skips_attached_limit_min_tp_rejection(
    ticks, strategy_config
):
    strategy_config.execution["slippage_enabled"] = False
    strategy_config.exit["fixed_take_profit"] = {
        "enabled": True,
        "target_pips": 1.0,
        "execution_mode": "managed_market_close",
        "disable_partial_take_profit": True,
        "disable_move_stop_to_breakeven": True,
        "disable_runner": True,
    }
    signal = _signal("SHORT")

    decision = evaluate_executable_entry_guardrail(signal, ticks.sort("timestamp_utc"), strategy_config)

    assert decision.accepted
    assert "REJECT_BELOW_BROKER_MIN_TP_DISTANCE" not in decision.rejection_reasons
    assert "WARN_FIXED_TP_MANAGED_MARKET_CLOSE_NOT_ATTACHED_LIMIT" in decision.warnings


def test_trade_lifecycle_throttles_stop_amends(strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    strategy_config.broker_execution_guardrails["trade_lifecycle"] = {
        "enabled": True,
        "stop_amend_min_interval_seconds": 60,
        "stop_amend_min_move_pips": 0.0,
        "max_stop_amends_per_trade": 10,
        "max_stop_amends_per_minute": 10,
    }
    signal = _signal("SHORT")
    signal.indicator_snapshot = {"atr_14": 0.1}
    ticks = pl.DataFrame({
        "timestamp_utc": [
            datetime(2021, 1, 4, 9, 0, 0, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 10, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 20, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 30, tzinfo=timezone.utc),
        ],
        "bid": [103.10, 102.96, 102.86, 103.08],
        "ask": [103.12, 102.98, 102.88, 103.10],
        "spread_pips": [2.0, 2.0, 2.0, 2.0],
    })

    trade = execute_signal(signal, ticks, strategy_config, 10000)

    assert trade.exit_reason == "trailing_stop"
    assert trade.stop_amend_count == 1
    assert trade.stop_amend_skipped_count > 0
    assert "STOP_AMEND_INTERVAL_THROTTLED" in trade.stop_amend_skip_reasons
    assert trade.partial_close_request_count == 1


def test_trade_lifecycle_rate_limits_repeated_stop_amend_skip_logs(strategy_config):
    strategy_config.execution["slippage_enabled"] = False
    strategy_config.broker_execution_guardrails["trade_lifecycle"] = {
        "enabled": True,
        "stop_amend_min_interval_seconds": 60,
        "stop_amend_min_move_pips": 0.0,
        "stop_amend_skip_log_interval_seconds": 60,
        "max_stop_amends_per_trade": 1,
        "max_stop_amends_per_minute": 10,
    }
    signal = _signal("SHORT")
    signal.indicator_snapshot = {"atr_14": 0.1}
    ticks = pl.DataFrame({
        "timestamp_utc": [
            datetime(2021, 1, 4, 9, 0, 0, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 10, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 20, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 30, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 1, 20, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 1, 30, tzinfo=timezone.utc),
        ],
        "bid": [103.10, 102.96, 102.86, 102.84, 102.82, 103.08],
        "ask": [103.12, 102.98, 102.88, 102.86, 102.84, 103.10],
        "spread_pips": [2.0] * 6,
    })

    trade = execute_signal(signal, ticks, strategy_config, 10000)

    assert trade.stop_amend_count == 1
    assert trade.stop_amend_skipped_count == 2
    assert trade.stop_amend_skip_reasons == [
        "MAX_STOP_AMENDS_PER_TRADE",
        "MAX_STOP_AMENDS_PER_TRADE",
    ]
