from src.config.config_loader import load_strategy_config
from src.execution.tick_execution_engine import execute_signal
from src.strategies.signal import Signal
from datetime import datetime, timezone


def test_fixed_stake_config_only_changes_sizing_and_run_metadata():
    baseline = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")
    fixed = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.fixed_004.yaml")
    assert fixed.position_sizing["mode"] == "fixed_spread_bet_stake"
    assert fixed.position_sizing["stake_per_pip_gbp"] == 0.04
    assert fixed.entry == baseline.entry
    assert fixed.stop_loss == baseline.stop_loss
    assert fixed.exit == baseline.exit
    assert fixed.broker_execution_guardrails == baseline.broker_execution_guardrails
    assert fixed.weekend_policy["policy_name"] == "force_close_friday_20_30"
    assert fixed.weekend_policy["enabled"] is True
    assert fixed.weekend_policy["force_close_on_friday"]["enabled"] is True


def test_fixed_stake_changes_money_not_execution_path(ticks):
    baseline = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")
    fixed = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.fixed_004.yaml")
    baseline.execution["slippage_enabled"] = fixed.execution["slippage_enabled"] = False
    signal = Signal(
        "s", datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc),
        datetime(2021, 1, 4, 8, 59, tzinfo=timezone.utc), "USDJPY", "SHORT", "market",
        103.10, "4H", "1H", [], {}, 103.20, 102.50, 2.0,
    )

    risk_trade = execute_signal(signal, ticks.sort("timestamp_utc"), baseline, 10000)
    fixed_trade = execute_signal(signal, ticks.sort("timestamp_utc"), fixed, 10000)

    assert fixed_trade.entry_timestamp_utc == risk_trade.entry_timestamp_utc
    assert fixed_trade.exit_timestamp_utc == risk_trade.exit_timestamp_utc
    assert fixed_trade.exit_reason == risk_trade.exit_reason
    assert fixed_trade.pnl_pips == risk_trade.pnl_pips
    assert fixed_trade.net_pnl != risk_trade.net_pnl
