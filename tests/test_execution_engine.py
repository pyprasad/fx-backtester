from datetime import datetime, timezone

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
