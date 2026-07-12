#!/usr/bin/env python3
import argparse
import json
import lzma
import struct
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import polars as pl


BASE_URL = "https://datafeed.dukascopy.com/datafeed"
PRICE_DIVISOR = 1000
RECORD_SIZE = 20


@dataclass
class FetchStats:
    requested_hours: int = 0
    downloaded_hours: int = 0
    cached_hours: int = 0
    missing_hours: int = 0
    failed_hours: int = 0
    ticks: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)


def record_failure(stats: FetchStats, reason: str) -> None:
    stats.failed_hours += 1
    stats.failure_reasons[reason] = stats.failure_reasons.get(reason, 0) + 1


def dukascopy_hour_url(symbol: str, timestamp: datetime) -> str:
    return (
        f"{BASE_URL}/{symbol.upper()}/"
        f"{timestamp.year}/{timestamp.month - 1:02d}/{timestamp.day:02d}/"
        f"{timestamp.hour:02d}h_ticks.bi5"
    )


def hour_range(start: datetime, end: datetime):
    current = start.replace(minute=0, second=0, microsecond=0)
    final = end.replace(minute=0, second=0, microsecond=0)
    while current <= final:
        yield current
        current += timedelta(hours=1)


def decode_bi5_ticks(content: bytes, day_hour: datetime, symbol: str) -> list[dict]:
    raw = lzma.decompress(content)
    rows = []
    for index in range(0, len(raw), RECORD_SIZE):
        chunk = raw[index:index + RECORD_SIZE]
        if len(chunk) != RECORD_SIZE:
            continue
        millis, ask, bid, ask_vol, bid_vol = struct.unpack(">IIIff", chunk)
        timestamp = day_hour + timedelta(milliseconds=millis)
        bid_price = bid / PRICE_DIVISOR
        ask_price = ask / PRICE_DIVISOR
        spread = ask_price - bid_price
        rows.append({
            "timestamp_utc": timestamp,
            "symbol": symbol.upper(),
            "bid": bid_price,
            "ask": ask_price,
            "mid": (bid_price + ask_price) / 2,
            "calculated_mid": (bid_price + ask_price) / 2,
            "mid_diff": 0.0,
            "spread": spread,
            "spread_pips": spread / 0.01,
            "bid_vol": bid_vol,
            "ask_vol": ask_vol,
        })
    return rows


def fetch_hour(url: str, timeout: int, retries: int, retry_sleep_seconds: float) -> tuple[bytes | None, str | None]:
    headers = {"User-Agent": "fx-backtester-research/1.0"}
    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=timeout) as response:
                return response.read(), None
        except HTTPError as exc:
            if exc.code == 404:
                return None, "HTTP_404"
            if attempt == retries:
                return None, f"HTTP_{exc.code}"
        except TimeoutError:
            if attempt == retries:
                return None, "TIMEOUT"
        except URLError as exc:
            if attempt == retries:
                reason = getattr(exc, "reason", exc)
                return None, f"URL_ERROR_{type(reason).__name__}"
        time.sleep(retry_sleep_seconds * attempt)
    return None, "UNKNOWN_FETCH_FAILURE"


def load_or_fetch_hour(
    symbol: str,
    hour: datetime,
    cache_dir: Path,
    timeout: int,
    retries: int,
    retry_sleep_seconds: float,
    refresh_cache: bool,
    stats: FetchStats,
) -> list[dict]:
    stats.requested_hours += 1
    cache_path = (
        cache_dir / symbol.upper() / f"{hour.year}" / f"{hour.month - 1:02d}" /
        f"{hour.day:02d}" / f"{hour.hour:02d}h_ticks.bi5"
    )
    if cache_path.exists() and not refresh_cache:
        stats.cached_hours += 1
        content = cache_path.read_bytes()
    else:
        url = dukascopy_hour_url(symbol, hour)
        try:
            content, failure_reason = fetch_hour(url, timeout, retries, retry_sleep_seconds)
        except Exception as exc:
            record_failure(stats, f"UNEXPECTED_{type(exc).__name__}")
            return []
        if failure_reason == "HTTP_404":
            stats.missing_hours += 1
            return []
        if content is None:
            record_failure(stats, failure_reason or "EMPTY_RESPONSE")
            return []
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        stats.downloaded_hours += 1

    try:
        rows = decode_bi5_ticks(content, hour, symbol)
    except lzma.LZMAError:
        record_failure(stats, "LZMA_DECODE_ERROR")
        return []
    stats.ticks += len(rows)
    return rows


def build_dukascopy_hourly(ticks: list[dict]) -> pl.DataFrame:
    if not ticks:
        return pl.DataFrame()
    return (
        pl.DataFrame(ticks)
        .sort("timestamp_utc")
        .group_by_dynamic("timestamp_utc", every="1h", label="left", closed="left")
        .agg([
            pl.first("symbol").alias("symbol"),
            pl.first("bid").alias("bid_open"),
            pl.max("bid").alias("bid_high"),
            pl.min("bid").alias("bid_low"),
            pl.last("bid").alias("bid_close"),
            pl.first("ask").alias("ask_open"),
            pl.max("ask").alias("ask_high"),
            pl.min("ask").alias("ask_low"),
            pl.last("ask").alias("ask_close"),
            pl.first("mid").alias("mid_open"),
            pl.max("mid").alias("mid_high"),
            pl.min("mid").alias("mid_low"),
            pl.last("mid").alias("mid_close"),
            pl.first("spread").alias("spread_open"),
            pl.max("spread").alias("spread_high"),
            pl.min("spread").alias("spread_low"),
            pl.last("spread").alias("spread_close"),
            pl.mean("spread").alias("spread_avg"),
            pl.median("spread").alias("spread_median"),
            pl.len().alias("tick_count"),
        ])
        .rename({"timestamp_utc": "timestamp"})
        .with_columns(pl.col("timestamp").dt.convert_time_zone("Europe/London").alias("timestamp_london"))
    )


def compare_spreads(dukascopy_hourly: pl.DataFrame, ig_hourly_path: Path) -> tuple[pl.DataFrame, dict]:
    if dukascopy_hourly.is_empty():
        return pl.DataFrame(), {"matched_hours": 0}
    ig = (
        pl.read_parquet(ig_hourly_path)
        .select([
            "timestamp",
            (pl.col("spread_avg") / 0.01).alias("ig_spread_avg_pips"),
            (pl.col("spread_close") / 0.01).alias("ig_spread_close_pips"),
            pl.col("mid_close").alias("ig_mid_close"),
        ])
    )
    duka = dukascopy_hourly.select([
        "timestamp",
        (pl.col("spread_avg") / 0.01).alias("dukascopy_spread_avg_pips"),
        (pl.col("spread_close") / 0.01).alias("dukascopy_spread_close_pips"),
        pl.col("mid_close").alias("dukascopy_mid_close"),
        "tick_count",
    ])
    joined = (
        ig.join(duka, on="timestamp", how="inner")
        .with_columns([
            (pl.col("ig_spread_avg_pips") - pl.col("dukascopy_spread_avg_pips")).alias("spread_avg_diff_pips"),
            (pl.col("ig_spread_avg_pips") / pl.col("dukascopy_spread_avg_pips")).alias("spread_avg_ratio"),
            (pl.col("ig_mid_close") - pl.col("dukascopy_mid_close")).alias("mid_close_diff"),
        ])
        .sort("timestamp")
    )
    if joined.is_empty():
        return joined, {"matched_hours": 0}
    summary = joined.select([
        pl.len().alias("matched_hours"),
        pl.col("ig_spread_avg_pips").mean().alias("ig_avg_spread_pips"),
        pl.col("dukascopy_spread_avg_pips").mean().alias("dukascopy_avg_spread_pips"),
        pl.col("spread_avg_diff_pips").mean().alias("avg_ig_minus_dukascopy_pips"),
        pl.col("spread_avg_ratio").mean().alias("avg_ig_to_dukascopy_spread_ratio"),
        pl.col("ig_spread_avg_pips").quantile(0.95).alias("ig_spread_p95_pips"),
        pl.col("dukascopy_spread_avg_pips").quantile(0.95).alias("dukascopy_spread_p95_pips"),
        pl.col("mid_close_diff").mean().alias("avg_mid_close_diff"),
    ]).row(0, named=True)
    return joined, {key: round(value, 6) if isinstance(value, float) else value for key, value in summary.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch recent Dukascopy USDJPY ticks and compare spreads with IG cache.")
    parser.add_argument("--symbol", default="USDJPY")
    parser.add_argument("--start", help="UTC start timestamp/date, e.g. 2026-06-10T00:00:00Z or 2026-06-10")
    parser.add_argument("--end", help="UTC end timestamp/date, e.g. 2026-06-12T20:00:00Z or 2026-06-12")
    parser.add_argument("--days", type=int, default=3, help="Use the last N days in the IG cache when start/end are omitted.")
    parser.add_argument("--ig-hourly-path", default="data/live_cache/ig/usdjpy_hour.parquet")
    parser.add_argument("--cache-dir", default=".runtime/dukascopy_cache")
    parser.add_argument("--output-dir", default="reports/dukascopy_ig_spread_compare")
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0)
    parser.add_argument("--refresh-cache", action="store_true")
    return parser.parse_args()


def parse_timestamp(value: str, is_end: bool = False) -> datetime:
    if "T" not in value:
        parsed_date = date.fromisoformat(value)
        return datetime.combine(parsed_date, dt_time(23 if is_end else 0), tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def default_range_from_ig_cache(ig_hourly_path: Path, days: int) -> tuple[datetime, datetime]:
    bounds = pl.read_parquet(ig_hourly_path).select([
        pl.col("timestamp").max().alias("end"),
    ]).row(0, named=True)
    end = bounds["end"].astimezone(timezone.utc)
    start = end - timedelta(days=max(days, 1))
    return start, end


def main() -> None:
    args = parse_args()
    ig_hourly_path = Path(args.ig_hourly_path)
    if args.start and args.end:
        start, end = parse_timestamp(args.start), parse_timestamp(args.end, is_end=True)
    else:
        start, end = default_range_from_ig_cache(ig_hourly_path, args.days)

    stats = FetchStats()
    ticks = []
    cache_dir = Path(args.cache_dir)
    for hour in hour_range(start, end):
        ticks.extend(load_or_fetch_hour(
            args.symbol,
            hour,
            cache_dir,
            args.timeout_seconds,
            args.retries,
            args.retry_sleep_seconds,
            args.refresh_cache,
            stats,
        ))

    duka_hourly = build_dukascopy_hourly(ticks)
    joined, summary = compare_spreads(duka_hourly, ig_hourly_path)
    result = {
        "symbol": args.symbol.upper(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "dukascopy_cache_dir": str(cache_dir),
        "ig_hourly_path": str(ig_hourly_path),
        "fetch": asdict(stats),
        "comparison": summary,
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "dukascopy_ig_spread_summary.json").write_text(json.dumps(result, indent=2, default=str))
    if not joined.is_empty():
        joined.write_csv(output_dir / "dukascopy_ig_spread_comparison.csv")
    if not duka_hourly.is_empty():
        duka_hourly.write_parquet(output_dir / "dukascopy_hourly.parquet")

    print(json.dumps(result, indent=2, default=str))
    print(f"Reports: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
