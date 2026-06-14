from datetime import datetime, timezone

import polars as pl

from src.config.config_loader import apply_weekend_policy_variant, load_strategy_config
from src.execution.tick_execution_engine import execute_signal
from src.strategies.signal import Signal


def _signal():
    timestamp = datetime(2025, 1, 3, 20, 0, tzinfo=timezone.utc)
    return Signal(
        "s", timestamp, timestamp, "USDJPY", "SHORT", "market", 150, "4H", "1H", [],
        {"atr_14": 0.1}, 150.2, 149.6, 1,
    )


def _ticks():
    return pl.DataFrame({
        "timestamp_utc": [
            datetime(2025, 1, 3, 20, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, 20, 30, tzinfo=timezone.utc),
            datetime(2025, 1, 3, 20, 31, tzinfo=timezone.utc),
        ],
        "bid": [150.0, 150.05, 150.06], "ask": [150.02, 150.07, 150.08],
        "spread_pips": [2, 2, 2],
    })


def test_weekend_force_close_is_identical_for_both_sizing_modes():
    fixed = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.fixed_004.yaml")
    risk = apply_weekend_policy_variant(
        load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml"),
        "force_close_friday_20_30", "config/weekend_policy_variants.usdjpy.yaml",
    )
    fixed.execution["slippage_enabled"] = risk.execution["slippage_enabled"] = False

    fixed_trade = execute_signal(_signal(), _ticks(), fixed, 10000)
    risk_trade = execute_signal(_signal(), _ticks(), risk, 10000)

    assert fixed_trade.exit_timestamp_utc == risk_trade.exit_timestamp_utc
    assert fixed_trade.exit_reason == risk_trade.exit_reason == "weekend_force_close"
    assert fixed_trade.held_over_weekend is False
