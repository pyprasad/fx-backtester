from datetime import datetime, timezone

import polars as pl
import pytest

from src.config.config_loader import load_data_quality_config, load_strategy_config


@pytest.fixture
def ticks():
    return pl.DataFrame({
        "timestamp_utc": [
            datetime(2021, 1, 4, 9, 0, 20, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 0, tzinfo=timezone.utc),
            datetime(2021, 1, 4, 9, 0, 40, tzinfo=timezone.utc),
        ],
        "symbol": ["USDJPY"] * 3,
        "bid": [103.11, 103.10, 103.12], "ask": [103.13, 103.12, 103.14],
        "mid": [103.12, 103.11, 103.13], "calculated_mid": [103.12, 103.11, 103.13],
        "mid_diff": [0.0] * 3, "spread": [0.02] * 3, "spread_pips": [2.0] * 3,
        "bid_vol": [1.0] * 3, "ask_vol": [2.0] * 3,
    })


@pytest.fixture
def quality_config():
    return load_data_quality_config("config/data_quality.usdjpy.yaml")


@pytest.fixture
def strategy_config():
    return load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")


@pytest.fixture
def stability_trades():
    dates = [
        datetime(2022, 1, 10, tzinfo=timezone.utc),
        datetime(2022, 2, 10, tzinfo=timezone.utc),
        datetime(2023, 4, 10, tzinfo=timezone.utc),
        datetime(2023, 5, 10, tzinfo=timezone.utc),
    ]
    return pl.DataFrame({
        "trade_id": ["a", "b", "c", "d"],
        "entry_timestamp_utc": dates,
        "exit_timestamp_utc": dates,
        "net_pnl": [100.0, -40.0, 120.0, -20.0],
        "pnl_r": [1.0, -0.4, 1.2, -0.2],
        "exit_reason": ["take_profit", "stop_loss", "trailing_stop", "weekend_force_close"],
        "duration_days": [1.0, 2.0, 1.5, 0.5],
        "session": ["London morning"] * 4,
    })
