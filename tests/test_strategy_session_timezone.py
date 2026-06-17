from datetime import datetime, timezone

import polars as pl

from src.strategies.fx_swing_trend_reclaim import generate_signals


def test_signal_session_uses_configured_timezone(strategy_config):
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
        "rsi_14": [45.0, 40.0],
        "atr_14": [.1, .1],
        "atr_14_pips": [10.0, 10.0],
    })
    trend = pl.DataFrame({
        "timestamp": times,
        "mid_close": [149.0, 149.0],
        "ema_200": [150.0, 150.0],
    })

    signals, _rejected = generate_signals(entry, trend, strategy_config)

    assert len(signals) == 1
    assert signals[0].session == "Tokyo"
    assert signals[0].timestamp_london.tzinfo.key == "Asia/Tokyo"


def test_signal_session_supports_per_window_timezones(strategy_config):
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
        "rsi_14": [45.0, 40.0], "atr_14": [.1, .1], "atr_14_pips": [10.0, 10.0],
    })
    trend = pl.DataFrame({"timestamp": times, "mid_close": [149.0, 149.0], "ema_200": [150.0, 150.0]})

    signals, _rejected = generate_signals(entry, trend, strategy_config)

    assert signals[0].session == "Tokyo"
    assert signals[0].timestamp_london.tzinfo.key == "Asia/Tokyo"


def test_news_guard_blocks_valid_signal_and_logs_event(strategy_config, tmp_path):
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
        "rsi_14": [45.0, 40.0], "atr_14": [.1, .1], "atr_14_pips": [10.0, 10.0],
    })
    trend = pl.DataFrame({"timestamp": times, "mid_close": [149.0, 149.0], "ema_200": [150.0, 150.0]})

    signals, rejected = generate_signals(entry, trend, strategy_config)

    assert signals == []
    news = [row for row in rejected if row["reason"] == "NEWS_BLACKOUT"]
    assert len(news) == 1
    assert news[0]["event_id"] == "us-cpi"
    assert news[0]["event_currency"] == "USD"
