from datetime import datetime, timezone
from types import SimpleNamespace

import polars as pl

from src.broker.ig.ig_candle_cache import (
    CandleCachePaths,
    derive_four_hour_from_hour,
    load_cached_candles,
    refresh_candle_cache,
    required_hour_points,
)
from src.broker.ig.ig_rest_client import IGAPIError, IGRateLimitError


def _price(timestamp):
    return {
        "snapshotTimeUTC": timestamp,
        "openPrice": {"bid": 16000, "ask": 16001},
        "closePrice": {"bid": 16010, "ask": 16011},
        "highPrice": {"bid": 16012, "ask": 16013},
        "lowPrice": {"bid": 15990, "ask": 15991},
    }


def _hour_frame(timestamps):
    rows = []
    for index, timestamp in enumerate(timestamps):
        base = 160 + index * 0.01
        rows.append({
            "timestamp": timestamp,
            "timestamp_london": timestamp,
            "symbol": "USDJPY",
            "bid_open": base,
            "ask_open": base + 0.01,
            "mid_open": base + 0.005,
            "bid_high": base + 0.02,
            "ask_high": base + 0.03,
            "mid_high": base + 0.025,
            "bid_low": base - 0.02,
            "ask_low": base - 0.01,
            "mid_low": base - 0.015,
            "bid_close": base + 0.005,
            "ask_close": base + 0.015,
            "mid_close": base + 0.01,
            "spread_open": 0.01,
            "spread_high": 0.01,
            "spread_low": 0.01,
            "spread_close": 0.01,
            "spread_avg": 0.01,
            "spread_median": 0.01,
            "spread_max": 0.01,
            "tick_count": 1,
            "bid_vol_sum": 0,
            "ask_vol_sum": 0,
        })
    return pl.DataFrame(rows)


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
    assert four_hour["timestamp"].to_list() == [datetime(2026, 6, 15, 8, tzinfo=timezone.utc)]


def test_refresh_candle_cache_skips_partial_bid_ask_prices(tmp_path):
    paths = CandleCachePaths(tmp_path)
    client = SimpleNamespace()
    client.get_historical_prices = lambda epic, resolution, points: {
        "prices": [
            {
                "snapshotTimeUTC": "2026-06-15T08:00:00",
                "openPrice": {"bid": 16000, "ask": 16001},
                "closePrice": {"bid": 16010, "ask": None},
                "highPrice": {"bid": 16012, "ask": 16013},
                "lowPrice": {"bid": 15990, "ask": 15991},
            },
            _price("2026-06-15T09:00:00"),
        ]
    }

    summary = refresh_candle_cache(
        client=client,
        epic="CS.D.USDJPY.TODAY.IP",
        paths=paths,
        scale_divisor=100,
        history_points=2,
        keep_last=1000,
    )
    hour, four_hour = load_cached_candles(paths)

    assert hour["timestamp"].to_list() == [datetime(2026, 6, 15, 9, tzinfo=timezone.utc)]
    assert four_hour.height == 1
    assert summary["timeframes"]["HOUR"]["incoming_rows"] == 1
    assert summary["timeframes"]["HOUR"]["conversion_quality"] == {
        "total_prices": 2,
        "valid_prices": 1,
        "skipped_missing_bid_ask": 1,
    }


def test_refresh_candle_cache_uses_existing_cache_when_historical_allowance_exceeded(tmp_path):
    paths = CandleCachePaths(tmp_path)
    existing = _hour_frame([datetime(2026, 6, 15, 8, tzinfo=timezone.utc)])
    existing.write_parquet(paths.path("HOUR"))

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
    assert summary["timeframes"]["HOUR"]["used_existing_cache"] is True
    assert summary["timeframes"]["HOUR_4"]["source"] == "derived_from_cached_hour_utc_anchor"


def test_refresh_candle_cache_uses_existing_cache_when_ig_history_has_transient_error(tmp_path):
    paths = CandleCachePaths(tmp_path)
    existing = _hour_frame([datetime(2026, 6, 15, 8, tzinfo=timezone.utc)])
    existing.write_parquet(paths.path("HOUR"))

    client = SimpleNamespace()

    def blocked(*_args):
        raise IGAPIError('IG REST error (500): {"errorCode":"error.price-history.io-error"}')

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
    assert summary["timeframes"]["HOUR"]["used_existing_cache"] is True
    assert summary["timeframes"]["HOUR"]["rate_limited_using_existing_cache"] is False
    assert summary["timeframes"]["HOUR"]["fallback_reason"].startswith(
        "IG_HISTORY_REFRESH_FAILED"
    )


def test_derive_four_hour_from_hour_uses_backtest_utc_anchor():
    hour = _hour_frame([
        datetime(2026, 6, 16, hour, tzinfo=timezone.utc)
        for hour in range(3, 15)
    ])

    four_hour = derive_four_hour_from_hour(hour)

    assert four_hour["timestamp"].to_list() == [
        datetime(2026, 6, 16, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 16, 4, tzinfo=timezone.utc),
        datetime(2026, 6, 16, 8, tzinfo=timezone.utc),
        datetime(2026, 6, 16, 12, tzinfo=timezone.utc),
    ]


def test_required_hour_points_requests_only_missing_plus_overlap():
    existing = _hour_frame([datetime(2026, 6, 16, 10, tzinfo=timezone.utc)])

    points, plan = required_hour_points(
        existing,
        requested_points=1000,
        now=datetime(2026, 6, 16, 15, 30, tzinfo=timezone.utc),
        overlap_hours=2,
    )

    assert points == 6
    assert plan["target_closed_hour"] == "2026-06-16T14:00:00+00:00"
    assert plan["missing_hours_estimate"] == 4


def test_required_hour_points_requests_overlap_when_cache_is_current():
    existing = _hour_frame([datetime(2026, 6, 16, 14, tzinfo=timezone.utc)])

    points, plan = required_hour_points(
        existing,
        requested_points=1000,
        now=datetime(2026, 6, 16, 15, 30, tzinfo=timezone.utc),
        overlap_hours=2,
    )

    assert points == 2
    assert plan["missing_hours_estimate"] == 0
