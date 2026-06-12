from pathlib import Path

import polars as pl

from src.utils.logging import format_bytes, get_logger

REQUIRED_COLUMNS = ["timestamp", "bid", "ask", "mid", "bid_vol", "ask_vol"]
logger = get_logger(__name__)


def scan_ticks(
    path: str | Path, pattern: str = "*.csv", symbol: str = "USDJPY", sort: bool = True
) -> pl.LazyFrame:
    files = sorted(Path(path).glob(pattern))
    if not files:
        raise FileNotFoundError(f"No tick files matched {Path(path) / pattern}")
    logger.info(
        "Tick input selected | files=%d, total_size=%s, pattern=%s",
        len(files),
        format_bytes(sum(file.stat().st_size for file in files)),
        str(Path(path) / pattern),
    )
    for file in files:
        logger.info("Tick input file | path=%s, size=%s", file, format_bytes(file.stat().st_size))
    raw = pl.scan_csv([str(file) for file in files], try_parse_dates=False, low_memory=True)
    missing = set(REQUIRED_COLUMNS) - set(raw.collect_schema().names())
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    ticks = raw.with_columns(
        pl.col("timestamp").str.to_datetime(time_zone="UTC", strict=True).alias("timestamp_utc"),
        *[pl.col(c).cast(pl.Float64, strict=True) for c in REQUIRED_COLUMNS[1:]],
    )
    result = (
        ticks.with_columns(
            pl.lit(symbol).alias("symbol"),
            (pl.col("ask") - pl.col("bid")).round(6).alias("spread"),
            (((pl.col("ask") - pl.col("bid")) / 0.01).round(6)).alias("spread_pips"),
            ((pl.col("bid") + pl.col("ask")) / 2).alias("calculated_mid"),
        )
        .with_columns((pl.col("mid") - pl.col("calculated_mid")).abs().alias("mid_diff"))
        .select(
            "timestamp_utc",
            "symbol",
            "bid",
            "ask",
            "mid",
            "calculated_mid",
            "mid_diff",
            "spread",
            "spread_pips",
            "bid_vol",
            "ask_vol",
        )
    )
    return result.sort("timestamp_utc") if sort else result


def load_ticks(path: str | Path, pattern: str = "*.csv", symbol: str = "USDJPY") -> pl.DataFrame:
    ticks = scan_ticks(path, pattern, symbol).collect(engine="streaming")
    if ticks["timestamp_utc"].null_count():
        raise ValueError("Invalid or missing timestamps")
    return ticks


def validate_structural(ticks: pl.DataFrame) -> None:
    if ticks.filter((pl.col("bid") <= 0) | (pl.col("ask") <= 0)).height:
        raise ValueError("Negative or zero prices found")
    if ticks.filter(pl.col("bid") > pl.col("ask")).height:
        raise ValueError("Bid greater than ask found")


def validate_structural_lazy(ticks: pl.LazyFrame) -> None:
    result = ticks.select(
        pl.col("timestamp_utc").null_count().alias("invalid_timestamps"),
        ((pl.col("bid") <= 0) | (pl.col("ask") <= 0)).sum().alias("invalid_prices"),
        (pl.col("bid") > pl.col("ask")).sum().alias("crossed_prices"),
        (pl.col("timestamp_utc").cast(pl.Int64).diff() < 0).sum().alias("out_of_order"),
    ).collect(engine="streaming").row(0, named=True)
    if result["invalid_timestamps"]:
        raise ValueError("Invalid or missing timestamps")
    if result["invalid_prices"]:
        raise ValueError("Negative or zero prices found")
    if result["crossed_prices"]:
        raise ValueError("Bid greater than ask found")
    if result["out_of_order"]:
        raise ValueError("Out-of-order timestamps found")
