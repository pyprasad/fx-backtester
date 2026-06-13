from datetime import datetime, timezone

from src.risk.weekend_policy import WeekendPolicy
from src.strategies.fx_swing_trend_reclaim import generate_signals


def _policy():
    return WeekendPolicy({
        "enabled": True, "policy_name": "test",
        "block_new_trades_after_friday": {"enabled": True, "cutoff_utc": "17:00"},
        "block_sunday_open_entries": {"enabled": True, "minutes_after_week_open": 60},
        "force_close_on_friday": {"enabled": True, "close_time_utc": "20:30", "close_reason": "weekend_force_close"},
        "close_only_if_losing_on_friday": {"enabled": True, "close_time_utc": "20:30", "close_reason": "weekend_losing_trade_close"},
        "close_only_if_not_in_profit_threshold": {"enabled": True, "close_time_utc": "20:30", "min_open_trade_r_to_keep": 1.0, "close_reason": "weekend_profit_threshold_close"},
        "reduce_position_before_weekend": {"enabled": True, "close_time_utc": "20:30", "close_percent": 50, "min_open_trade_r_to_apply": 0.0, "close_reason": "weekend_partial_reduce"},
        "tighten_stop_before_weekend": {"enabled": True, "apply_time_utc": "20:30", "min_open_trade_r_to_apply": 0.5, "reason": "weekend_stop_tighten"},
    })


def test_friday_cutoff_and_sunday_open():
    policy = _policy()
    assert policy.should_block_new_entry(datetime(2025, 1, 3, 17, 1, tzinfo=timezone.utc))[0]
    assert not policy.should_block_new_entry(datetime(2025, 1, 3, 16, 59, tzinfo=timezone.utc))[0]
    opened = datetime(2025, 1, 5, 21, tzinfo=timezone.utc)
    assert policy.should_block_sunday_open_entry(opened.replace(minute=30), opened)[0]
    assert not policy.should_block_sunday_open_entry(opened.replace(hour=22, minute=15), opened)[0]


def test_conditional_weekend_decisions():
    policy = _policy()
    friday = datetime(2025, 1, 3, 20, 30, tzinfo=timezone.utc)
    assert policy.should_force_close_trade({}, friday)[0]
    assert policy.should_close_losing_trade({}, friday, -0.1)[0]
    assert not policy.should_close_losing_trade({}, friday, 0.1)[0]
    assert policy.should_close_below_profit_threshold({}, friday, 0.5)[0]
    assert not policy.should_close_below_profit_threshold({}, friday, 1.2)[0]
    assert policy.should_reduce_position({}, friday, 0.2)[:2] == (True, 50)
    assert policy.should_tighten_stop({}, friday, 0.5)[0]


def test_policy_does_not_log_rejection_for_non_signal_candle(strategy_config):
    import polars as pl

    friday = datetime(2025, 1, 3, 18, tzinfo=timezone.utc)
    strategy_config.weekend_policy["enabled"] = True
    strategy_config.weekend_policy["block_new_trades_after_friday"]["enabled"] = True
    entry = pl.DataFrame({
        "timestamp": [friday], "timestamp_london": [friday], "symbol": ["USDJPY"],
        "mid_open": [150.0], "mid_high": [150.1], "mid_low": [149.9], "mid_close": [150.1],
        "spread_avg": [0.001], "ema_20": [150.0], "ema_50": [149.9], "rsi_14": [60.0],
        "atr_14": [0.1], "atr_14_pips": [10.0],
    })
    trend = pl.DataFrame({"timestamp": [friday], "mid_close": [150.0], "ema_200": [149.0]})
    signals, rejected = generate_signals(entry, trend, strategy_config)
    assert not signals
    assert not any(item["reason"].startswith("REJECT_WEEKEND_POLICY") for item in rejected)
