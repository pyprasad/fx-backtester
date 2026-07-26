from datetime import datetime, timedelta, timezone

import polars as pl

from src.strategies.fx_swing_trend_reclaim import generate_signals


def _use_candle_close_timing(strategy_config):
    strategy_config.execution["signal_timing_mode"] = "candle_close_timestamp"


def test_signal_session_uses_configured_timezone(strategy_config):
    _use_candle_close_timing(strategy_config)
    strategy_config.session_filter = {
        "timezone": "Asia/Tokyo",
        "entry_windows": [{"name": "Tokyo", "start": "09:00", "end": "18:00"}],
    }
    strategy_config.broker_execution_guardrails["enabled"] = False
    times = [
        datetime(2025, 1, 6, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 6, 1, tzinfo=timezone.utc),
    ]
    entry = pl.DataFrame({
        "timestamp": times,
        "timestamp_london": times,
        "symbol": ["USDJPY"] * 2,
        "mid_open": [150.1, 150.1],
        "mid_high": [150.2, 150.2],
        "mid_low": [149.9, 149.9],
        "mid_close": [150.0, 150.0],
        "spread_avg": [.001, .001],
        "ema_20": [150.0, 150.0],
        "ema_50": [150.1, 150.1],
        "ema_200": [151.0, 151.0],
        "rsi_14": [45.0, 40.0],
        "atr_14": [.1, .1],
        "atr_14_pips": [10.0, 10.0],
    })
    trend_times = [value - timedelta(hours=3) for value in times]
    trend = pl.DataFrame({
        "timestamp": trend_times,
        "mid_close": [149.0, 149.0],
        "ema_200": [150.0, 150.0],
    })

    signals, _rejected = generate_signals(entry, trend, strategy_config)

    assert len(signals) == 1
    assert signals[0].timestamp_utc == datetime(2025, 1, 6, 2, tzinfo=timezone.utc)
    assert signals[0].session == "Tokyo"
    assert signals[0].timestamp_london.tzinfo.key == "Asia/Tokyo"


def test_signal_session_supports_per_window_timezones(strategy_config):
    _use_candle_close_timing(strategy_config)
    strategy_config.session_filter = {
        "timezone": "UTC",
        "entry_windows": [
            {"name": "London", "start": "07:00", "end": "11:30", "timezone": "Europe/London"},
            {"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
        ],
    }
    strategy_config.broker_execution_guardrails["enabled"] = False
    times = [
        datetime(2025, 1, 6, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 6, 1, tzinfo=timezone.utc),
    ]
    entry = pl.DataFrame({
        "timestamp": times, "timestamp_london": times, "symbol": ["USDJPY"] * 2,
        "mid_open": [150.1, 150.1], "mid_high": [150.2, 150.2],
        "mid_low": [149.9, 149.9], "mid_close": [150.0, 150.0],
        "spread_avg": [.001, .001], "ema_20": [150.0, 150.0], "ema_50": [150.1, 150.1],
        "ema_200": [151.0, 151.0], "rsi_14": [45.0, 40.0],
        "atr_14": [.1, .1], "atr_14_pips": [10.0, 10.0],
    })
    trend_times = [value - timedelta(hours=3) for value in times]
    trend = pl.DataFrame({"timestamp": trend_times, "mid_close": [149.0, 149.0], "ema_200": [150.0, 150.0]})

    signals, _rejected = generate_signals(entry, trend, strategy_config)

    assert signals[0].session == "Tokyo"
    assert signals[0].timestamp_london.tzinfo.key == "Asia/Tokyo"


def test_news_guard_blocks_valid_signal_and_logs_event(strategy_config, tmp_path):
    _use_candle_close_timing(strategy_config)
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "us-cpi,2025-01-06T01:00:00Z,United States,USD,CPI YoY,HIGH,,,,manual\n"
    )
    strategy_config.base_dir = tmp_path
    strategy_config.session_filter = {
        "timezone": "Asia/Tokyo",
        "entry_windows": [{"name": "Tokyo", "start": "09:00", "end": "18:00"}],
    }
    strategy_config.broker_execution_guardrails["enabled"] = False
    strategy_config.news_guard = {
        "enabled": True,
        "calendar_file": "events.csv",
        "affected_currencies": ["USD", "JPY"],
        "impact_levels": ["HIGH"],
        "before_minutes": 60,
        "after_minutes": 60,
        "block_new_entries": True,
        "log_skipped_signals": True,
    }
    times = [
        datetime(2025, 1, 6, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 6, 1, tzinfo=timezone.utc),
    ]
    entry = pl.DataFrame({
        "timestamp": times, "timestamp_london": times, "symbol": ["USDJPY"] * 2,
        "mid_open": [150.1, 150.1], "mid_high": [150.2, 150.2],
        "mid_low": [149.9, 149.9], "mid_close": [150.0, 150.0],
        "spread_avg": [.001, .001], "ema_20": [150.0, 150.0], "ema_50": [150.1, 150.1],
        "ema_200": [151.0, 151.0], "rsi_14": [45.0, 40.0],
        "atr_14": [.1, .1], "atr_14_pips": [10.0, 10.0],
    })
    trend_times = [value - timedelta(hours=3) for value in times]
    trend = pl.DataFrame({"timestamp": trend_times, "mid_close": [149.0, 149.0], "ema_200": [150.0, 150.0]})

    signals, rejected = generate_signals(entry, trend, strategy_config)

    assert signals == []
    news = [row for row in rejected if row["reason"] == "NEWS_BLACKOUT"]
    assert len(news) == 1
    assert news[0]["event_id"] == "us-cpi"
    assert news[0]["event_currency"] == "USD"


def test_trend_filter_uses_4h_ema_not_entry_ema(strategy_config):
    _use_candle_close_timing(strategy_config)
    strategy_config.session_filter = {
        "timezone": "Asia/Tokyo",
        "entry_windows": [{"name": "Tokyo", "start": "09:00", "end": "18:00"}],
    }
    strategy_config.broker_execution_guardrails["enabled"] = False
    times = [
        datetime(2025, 1, 6, 0, tzinfo=timezone.utc),
        datetime(2025, 1, 6, 1, tzinfo=timezone.utc),
    ]
    entry = pl.DataFrame({
        "timestamp": times, "timestamp_london": times, "symbol": ["USDJPY"] * 2,
        "mid_open": [150.1, 150.1], "mid_high": [150.2, 150.2],
        "mid_low": [149.9, 149.9], "mid_close": [150.0, 150.0],
        "spread_avg": [.001, .001],
        "ema_20": [150.0, 150.0],
        "ema_50": [150.1, 150.1],
        "ema_200": [151.0, 151.0],
        "rsi_14": [45.0, 40.0],
        "atr_14": [.1, .1],
        "atr_14_pips": [10.0, 10.0],
    })
    trend_times = [value - timedelta(hours=3) for value in times]
    trend_above_4h_ema = pl.DataFrame({
        "timestamp": trend_times,
        "mid_close": [150.5, 150.5],
        "ema_200": [149.0, 149.0],
    })
    trend_below_4h_ema = pl.DataFrame({
        "timestamp": trend_times,
        "mid_close": [148.5, 148.5],
        "ema_200": [149.0, 149.0],
    })

    blocked, _ = generate_signals(entry, trend_above_4h_ema, strategy_config)
    allowed, _ = generate_signals(entry, trend_below_4h_ema, strategy_config)

    assert blocked == []
    assert len(allowed) == 1


def test_signal_uses_entry_candle_close_and_closed_4h_context(strategy_config):
    _use_candle_close_timing(strategy_config)
    strategy_config.session_filter = {
        "timezone": "UTC",
        "entry_windows": [{"name": "London", "start": "07:00", "end": "11:30"}],
    }
    strategy_config.broker_execution_guardrails["enabled"] = False
    entry_times = [
        datetime(2025, 1, 6, 5, tzinfo=timezone.utc),
        datetime(2025, 1, 6, 6, tzinfo=timezone.utc),
    ]
    entry = pl.DataFrame({
        "timestamp": entry_times, "timestamp_london": entry_times, "symbol": ["USDJPY"] * 2,
        "mid_open": [150.1, 150.1], "mid_high": [150.2, 150.2],
        "mid_low": [149.9, 149.9], "mid_close": [150.0, 150.0],
        "spread_avg": [.001, .001], "ema_20": [150.0, 150.0], "ema_50": [150.1, 150.1],
        "ema_200": [151.0, 151.0], "rsi_14": [45.0, 40.0],
        "atr_14": [.1, .1], "atr_14_pips": [10.0, 10.0],
    })
    trend = pl.DataFrame({
        "timestamp": [
            datetime(2025, 1, 6, 2, tzinfo=timezone.utc),
            datetime(2025, 1, 6, 6, tzinfo=timezone.utc),
        ],
        "mid_close": [149.0, 160.0],
        "ema_200": [150.0, 150.0],
    })

    signals, _ = generate_signals(entry, trend, strategy_config)

    assert len(signals) == 1
    assert signals[0].timestamp_utc == datetime(2025, 1, 6, 7, tzinfo=timezone.utc)
    assert signals[0].session == "London"


def test_legacy_signal_timing_uses_entry_candle_open_and_legacy_4h_context(strategy_config):
    strategy_config.execution["signal_timing_mode"] = "legacy_open_timestamp"
    strategy_config.session_filter = {
        "timezone": "UTC",
        "entry_windows": [{"name": "London", "start": "06:00", "end": "11:30"}],
    }
    strategy_config.broker_execution_guardrails["enabled"] = False
    entry_times = [
        datetime(2025, 1, 6, 5, tzinfo=timezone.utc),
        datetime(2025, 1, 6, 6, tzinfo=timezone.utc),
    ]
    entry = pl.DataFrame({
        "timestamp": entry_times, "timestamp_london": entry_times, "symbol": ["USDJPY"] * 2,
        "mid_open": [150.1, 150.1], "mid_high": [150.2, 150.2],
        "mid_low": [149.9, 149.9], "mid_close": [150.0, 150.0],
        "spread_avg": [.001, .001], "ema_20": [150.0, 150.0], "ema_50": [150.1, 150.1],
        "ema_200": [151.0, 151.0], "rsi_14": [45.0, 40.0],
        "atr_14": [.1, .1], "atr_14_pips": [10.0, 10.0],
    })
    trend = pl.DataFrame({
        "timestamp": [
            datetime(2025, 1, 6, 2, tzinfo=timezone.utc),
            datetime(2025, 1, 6, 6, tzinfo=timezone.utc),
        ],
        "mid_close": [160.0, 149.0],
        "ema_200": [150.0, 150.0],
    })

    signals, _ = generate_signals(entry, trend, strategy_config)

    assert len(signals) == 1
    assert signals[0].timestamp_utc == datetime(2025, 1, 6, 6, tzinfo=timezone.utc)
    assert signals[0].session == "London"
