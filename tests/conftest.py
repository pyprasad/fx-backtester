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
