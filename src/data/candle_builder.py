from pathlib import Path

import polars as pl

from src.utils.logging import get_logger, timed_stage

TIMEFRAMES = {"1M": "1m", "5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}
logger = get_logger(__name__)


def build_candles(ticks: pl.DataFrame | pl.LazyFrame, timeframe: str) -> pl.DataFrame:
    every = TIMEFRAMES[timeframe]
    aggregations = [pl.first("symbol").alias("symbol")]
    for price in ("mid", "bid", "ask"):
        aggregations += [
            pl.first(price).alias(f"{price}_open"), pl.max(price).alias(f"{price}_high"),
            pl.min(price).alias(f"{price}_low"), pl.last(price).alias(f"{price}_close"),
        ]
    aggregations += [
        pl.first("spread").alias("spread_open"), pl.max("spread").alias("spread_high"),
        pl.min("spread").alias("spread_low"), pl.last("spread").alias("spread_close"),
        pl.mean("spread").alias("spread_avg"), pl.median("spread").alias("spread_median"),
        pl.max("spread").alias("spread_max"), pl.len().alias("tick_count"),
        pl.sum("bid_vol").alias("bid_vol_sum"), pl.sum("ask_vol").alias("ask_vol_sum"),
    ]
    result = (
        ticks.sort("timestamp_utc")
        .group_by_dynamic("timestamp_utc", every=every, label="left", closed="left")
        .agg(aggregations)
        .rename({"timestamp_utc": "timestamp"})
        .with_columns(pl.col("timestamp").dt.convert_time_zone("Europe/London").alias("timestamp_london"))
    )
    return result.collect(engine="streaming") if isinstance(result, pl.LazyFrame) else result


def build_and_save_all(ticks: pl.DataFrame | pl.LazyFrame, output_dir: str | Path, timeframes: list[str]) -> dict[str, pl.DataFrame]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for timeframe in timeframes:
        output = output_dir / f"USDJPY_{timeframe}.parquet"
        with timed_stage(logger, f"build {timeframe} candles", output=output):
            result[timeframe] = build_candles(ticks, timeframe)
            result[timeframe].write_parquet(output)
        logger.info("%s candles written | count=%s", timeframe, f"{result[timeframe].height:,}")
    return result
