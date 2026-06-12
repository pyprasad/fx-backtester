import polars as pl

from src.config.config_loader import resolve
from src.config.schemas import DataQualityConfig
from src.utils.logging import format_bytes, get_logger, timed_stage

from .tick_loader import scan_ticks, validate_structural_lazy

logger = get_logger(__name__)


def normalize_ticks(config: DataQualityConfig, overwrite: bool = False) -> tuple[None, dict]:
    output = resolve(config, config.input["normalised_output_path"])
    if output.exists() and not overwrite:
        raise FileExistsError(f"{output} exists; pass --overwrite to replace it")
    with timed_stage(logger, "scan tick CSV metadata"):
        ticks = scan_ticks(
            resolve(config, config.input["raw_tick_path"]),
            config.input["file_pattern"],
            config.market.symbol,
            sort=False,
        )
    with timed_stage(logger, "validate structural tick data"):
        validate_structural_lazy(ticks)
    ticks = ticks.sort("timestamp_utc")
    output.parent.mkdir(parents=True, exist_ok=True)
    with timed_stage(logger, "normalize and write Parquet", output=output):
        ticks.sink_parquet(output, compression="zstd", statistics=True, mkdir=True, engine="streaming")
    logger.info("Normalized Parquet written | path=%s, size=%s", output, format_bytes(output.stat().st_size))
    with timed_stage(logger, "calculate normalization summary"):
        summary = normalization_summary(pl.scan_parquet(output))
    logger.info(
        "Normalization summary | ticks=%s, start=%s, end=%s",
        f"{summary['total_ticks']:,}",
        summary["start_timestamp"],
        summary["end_timestamp"],
    )
    return None, summary


def normalization_summary(ticks: pl.DataFrame | pl.LazyFrame) -> dict:
    row = ticks.select(
        pl.col("timestamp_utc").min().alias("start_timestamp"),
        pl.col("timestamp_utc").max().alias("end_timestamp"),
        pl.len().alias("total_ticks"),
        pl.col("bid").min().alias("min_bid"),
        pl.col("bid").max().alias("max_bid"),
        pl.col("spread_pips").mean().alias("average_spread_pips"),
        pl.col("spread_pips").max().alias("max_spread_pips"),
    )
    if isinstance(row, pl.LazyFrame):
        row = row.collect(engine="streaming")
    row = row.to_dicts()[0]
    return {
        key: round(value, 6) if isinstance(value, float) else value
        for key, value in row.items()
    }
