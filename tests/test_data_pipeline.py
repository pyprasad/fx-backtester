from datetime import timedelta

import polars as pl

from src.data.candle_builder import build_candles
from src.data.data_quality import analyze_data_quality
from src.data.tick_loader import load_ticks


def test_candle_builder_uses_sorted_ohlc_and_counts_ticks(ticks):
    candle = build_candles(ticks, "1M").row(0, named=True)
    assert candle["bid_open"] == 103.10
    assert candle["bid_close"] == 103.12
    assert candle["mid_high"] == 103.13
    assert candle["tick_count"] == 3
    assert round(candle["spread_avg"], 3) == 0.02


def test_quality_detects_duplicate_mismatch_wide_spread_and_gap(ticks, quality_config):
    bad = pl.concat([ticks, ticks.slice(0, 1)]).with_columns(
        pl.when(pl.arange(0, pl.len()) == 0).then(1.0).otherwise(pl.col("mid_diff")).alias("mid_diff"),
        pl.when(pl.arange(0, pl.len()) == 1).then(8.0).otherwise(pl.col("spread_pips")).alias("spread_pips"),
        pl.when(pl.arange(0, pl.len()) == 2)
        .then(pl.col("timestamp_utc") + timedelta(hours=2))
        .otherwise(pl.col("timestamp_utc")).alias("timestamp_utc"),
    )
    report = analyze_data_quality(bad, quality_config)
    assert report.duplicate_timestamp_count > 0
    assert report.mid_mismatch_count > 0
    assert report.extreme_spread_count > 0
    assert report.extreme_gap_count > 0


def test_loaded_spread_pips_do_not_contain_float_noise(tmp_path):
    path = tmp_path / "ticks.csv"
    path.write_text(
        "timestamp,bid,ask,mid,bid_vol,ask_vol\n"
        "2021-01-04T09:00:00+00:00,103.100,103.102,103.101,1,1\n"
    )
    loaded = load_ticks(tmp_path)
    assert loaded["spread_pips"][0] == 0.2
