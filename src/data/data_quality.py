import csv
import html
import json
from dataclasses import asdict, dataclass
import polars as pl

from src.config.config_loader import resolve
from src.config.schemas import DataQualityConfig
from src.utils.logging import get_logger, timed_stage

logger = get_logger(__name__)


@dataclass
class DataQualityReport:
    symbol: str
    start_timestamp: object
    end_timestamp: object
    total_ticks: int
    duplicate_timestamp_count: int
    out_of_order_count: int
    bid_greater_than_ask_count: int
    negative_or_zero_price_count: int
    negative_spread_count: int
    zero_spread_count: int
    mid_mismatch_count: int
    warning_spread_count: int
    extreme_spread_count: int
    max_spread_pips: float
    avg_spread_pips: float
    median_spread_pips: float
    p95_spread_pips: float
    p99_spread_pips: float
    max_gap_seconds: float
    warning_gap_count: int
    extreme_gap_count: int
    weekend_tick_count: int
    sunday_open_tick_count: int
    ticks_by_year: dict
    ticks_by_month: dict
    ticks_by_day_of_week: dict
    ticks_by_hour_utc: dict
    status: str


def analyze_data_quality(ticks: pl.DataFrame | pl.LazyFrame, config: DataQualityConfig) -> DataQualityReport:
    original = ticks.lazy() if isinstance(ticks, pl.DataFrame) else ticks
    with timed_stage(logger, "quality ordering and duplicate scan"):
        ordering = original.select(
            pl.col("timestamp_utc").is_duplicated().sum().alias("duplicates"),
            (pl.col("timestamp_utc").cast(pl.Int64).diff() < 0).sum().alias("out_of_order"),
        ).collect(engine="streaming").row(0, named=True)
    df = original.sort("timestamp_utc").with_columns(
        pl.col("timestamp_utc").diff().dt.total_seconds().alias("gap_seconds"),
        pl.col("timestamp_utc").dt.weekday().alias("weekday"),
        pl.col("timestamp_utc").dt.hour().alias("hour"),
    )
    s, g, p = config.spread, config.gaps, config.price
    with timed_stage(logger, "quality aggregate metrics scan"):
        describe = df.select(
        pl.len().alias("total_ticks"),
        pl.col("timestamp_utc").min().alias("start"),
        pl.col("timestamp_utc").max().alias("end"),
        (pl.col("bid") > pl.col("ask")).sum().alias("crossed"),
        ((pl.col("bid") <= 0) | (pl.col("ask") <= 0)).sum().alias("invalid_prices"),
        (pl.col("spread_pips") < 0).sum().alias("negative_spreads"),
        (pl.col("spread_pips") == 0).sum().alias("zero_spreads"),
        (pl.col("mid_diff") > p["mid_tolerance"]).sum().alias("mid_mismatches"),
        (pl.col("spread_pips") > s["warning_spread_pips"]).sum().alias("warning_spreads"),
        (pl.col("spread_pips") > s["extreme_spread_pips"]).sum().alias("extreme_spreads"),
        pl.col("spread_pips").max().alias("max"),
        pl.col("spread_pips").mean().alias("avg"),
        pl.col("spread_pips").median().alias("median"),
        pl.col("spread_pips").quantile(0.95).alias("p95"),
        pl.col("spread_pips").quantile(0.99).alias("p99"),
        pl.col("gap_seconds").max().fill_null(0).alias("max_gap"),
        (pl.col("gap_seconds") > g["warning_gap_seconds"]).sum().alias("warning_gaps"),
        (pl.col("gap_seconds") > g["extreme_gap_seconds"]).sum().alias("extreme_gaps"),
        pl.col("weekday").is_in([6, 7]).sum().alias("weekend"),
        ((pl.col("weekday") == 7) & (pl.col("hour") >= 21)).sum().alias("sunday_open"),
        ).collect(engine="streaming").to_dicts()[0]
    structural = describe["crossed"] + describe["invalid_prices"] + ordering["out_of_order"]

    def grouped(expr: pl.Expr) -> dict:
        return dict(
            df.group_by(expr.alias("key")).len().sort("key").collect(engine="streaming").iter_rows()
        )

    with timed_stage(logger, "quality grouped distribution scans"):
        years = grouped(pl.col("timestamp_utc").dt.year())
        months = grouped(pl.col("timestamp_utc").dt.strftime("%Y-%m"))
        weekdays = grouped(pl.col("weekday"))
        hours = grouped(pl.col("hour"))

    return DataQualityReport(
        config.market.symbol, describe["start"], describe["end"], describe["total_ticks"],
        ordering["duplicates"], ordering["out_of_order"], describe["crossed"],
        describe["invalid_prices"], describe["negative_spreads"], describe["zero_spreads"],
        describe["mid_mismatches"], describe["warning_spreads"], describe["extreme_spreads"],
        round(describe["max"], 3), round(describe["avg"], 3), round(describe["median"], 3),
        round(describe["p95"], 3), round(describe["p99"], 3),
        describe["max_gap"], describe["warning_gaps"], describe["extreme_gaps"],
        describe["weekend"], describe["sunday_open"],
        years, months, weekdays, hours,
        "FAIL" if structural else ("WARNING" if describe["max"] > s["warning_spread_pips"] else "PASS"),
    )


def write_quality_reports(
    report: DataQualityReport, ticks: pl.DataFrame | pl.LazyFrame, config: DataQualityConfig
) -> None:
    summary_path = resolve(config, config.output["summary_csv_path"])
    html_path = resolve(config, config.output["report_path"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    flat = asdict(report)
    with summary_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=flat.keys())
        writer.writeheader()
        writer.writerow({k: json.dumps(v, default=str) if isinstance(v, dict) else v for k, v in flat.items()})
    lazy = ticks.lazy() if isinstance(ticks, pl.DataFrame) else ticks
    top_gaps = lazy.sort("timestamp_utc").with_columns(
        pl.col("timestamp_utc").diff().dt.total_seconds().alias("gap_seconds")
    ).top_k(50, by="gap_seconds").select("timestamp_utc", "gap_seconds").collect(engine="streaming").to_dicts()
    top_spreads = lazy.top_k(50, by="spread_pips").select(
        "timestamp_utc", "bid", "ask", "spread_pips"
    ).collect(engine="streaming").to_dicts()
    cards = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in flat.items())
    html_path.write_text(
        f"<html><body><h1>USDJPY Data Quality: {report.status}</h1><table>{cards}</table>"
        f"<h2>Top gaps</h2><pre>{html.escape(json.dumps(top_gaps, default=str, indent=2))}</pre>"
        f"<h2>Widest spreads</h2><pre>{html.escape(json.dumps(top_spreads, default=str, indent=2))}</pre>"
        "<p>Wide spreads are warnings; structural price and timestamp errors fail validation.</p></body></html>"
    )
