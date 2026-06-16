from datetime import datetime, timezone
from types import SimpleNamespace

import polars as pl

from src.broker.ig.ig_candle_cache import CandleCachePaths, load_cached_candles, refresh_candle_cache
from src.broker.ig.ig_rest_client import IGRateLimitError


def _price(timestamp):
    return {
        "snapshotTimeUTC": timestamp,
        "openPrice": {"bid": 16000, "ask": 16001},
        "closePrice": {"bid": 16010, "ask": 16011},
        "highPrice": {"bid": 16012, "ask": 16013},
        "lowPrice": {"bid": 15990, "ask": 15991},
    }


def test_refresh_candle_cache_merges_deduplicates_and_keeps_last(tmp_path):
    paths = CandleCachePaths(tmp_path)
    existing = pl.DataFrame({
        "timestamp": [
            datetime(2026, 6, 15, 7, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 8, tzinfo=timezone.utc),
        ],
        "symbol": ["USDJPY", "USDJPY"],
        "bid_close": [160.1, 160.2],
    })
    existing.write_parquet(paths.path("HOUR"))

    client = SimpleNamespace()
    client.get_historical_prices = lambda epic, resolution, points: {
        "prices": [
            _price("2026-06-15T08:00:00"),
            _price("2026-06-15T09:00:00"),
            _price("2026-06-15T10:00:00"),
        ]
    }

    summary = refresh_candle_cache(
        client=client,
        epic="CS.D.USDJPY.TODAY.IP",
        paths=paths,
        scale_divisor=100,
        history_points=3,
        keep_last=2,
    )
    hour, four_hour = load_cached_candles(paths)

    assert summary["timeframes"]["HOUR"]["rows"] == 2
    assert hour["timestamp"].to_list() == [
        datetime(2026, 6, 15, 9, tzinfo=timezone.utc),
        datetime(2026, 6, 15, 10, tzinfo=timezone.utc),
    ]
    assert four_hour.height == 2


def test_refresh_candle_cache_uses_existing_cache_when_historical_allowance_exceeded(tmp_path):
    paths = CandleCachePaths(tmp_path)
    existing = pl.DataFrame({
        "timestamp": [datetime(2026, 6, 15, 8, tzinfo=timezone.utc)],
        "timestamp_london": [datetime(2026, 6, 15, 9, tzinfo=timezone.utc)],
        "symbol": ["USDJPY"],
        "bid_close": [160.2],
    })
    existing.write_parquet(paths.path("HOUR"))
    existing.write_parquet(paths.path("HOUR_4"))

    client = SimpleNamespace()

    def blocked(*_args):
        raise IGRateLimitError("allowance exceeded")

    client.get_historical_prices = blocked

    summary = refresh_candle_cache(
        client=client,
        epic="CS.D.USDJPY.TODAY.IP",
        paths=paths,
        scale_divisor=100,
        history_points=10,
        keep_last=1000,
    )
    hour, four_hour = load_cached_candles(paths)

    assert hour.height == 1
    assert four_hour.height == 1
    assert summary["timeframes"]["HOUR"]["rate_limited_using_existing_cache"] is True
