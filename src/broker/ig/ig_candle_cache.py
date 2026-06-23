import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from .ig_live_signal import closed_candles, convert_prices_to_candles, derive_four_hour_from_hour
from .ig_rest_client import IGRateLimitError


@dataclass(frozen=True)
class CandleCachePaths:
    root: Path
    symbol: str = "usdjpy"

    def path(self, resolution: str) -> Path:
        return self.root / f"{self.symbol}_{resolution.lower()}.parquet"

    def metadata_path(self) -> Path:
        return self.root / f"{self.symbol}_metadata.json"

    def exists(self) -> bool:
        return self.path("HOUR").exists() and self.path("HOUR_4").exists()


def _merge(existing: pl.DataFrame | None, incoming: pl.DataFrame, keep_last: int) -> pl.DataFrame:
    if incoming.height == 0 and existing is not None and existing.height:
        return existing.sort("timestamp").tail(keep_last)
    if existing is not None and existing.height:
        frame = pl.concat([existing, incoming], how="diagonal_relaxed")
    else:
        frame = incoming
    return (
        frame.unique(subset=["timestamp"], keep="last")
        .sort("timestamp")
        .tail(keep_last)
    )


def required_hour_points(existing: pl.DataFrame | None, requested_points: int,
                         now: datetime | None = None, overlap_hours: int = 2) -> tuple[int, dict]:
    if existing is None or not existing.height:
        return requested_points, {
            "reason": "bootstrap_no_existing_cache",
            "latest_cached_timestamp": None,
            "target_closed_hour": None,
            "missing_hours_estimate": None,
            "overlap_hours": overlap_hours,
        }
    now = now or datetime.now(timezone.utc)
    target = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    latest = existing["timestamp"].max()
    missing = max(0, int((target - latest).total_seconds() // 3600))
    points = min(requested_points, max(1, missing + overlap_hours))
    return points, {
        "reason": "incremental_from_existing_cache",
        "latest_cached_timestamp": latest.isoformat(),
        "target_closed_hour": target.isoformat(),
        "missing_hours_estimate": missing,
        "overlap_hours": overlap_hours,
    }


def refresh_candle_cache(*, client, epic: str, paths: CandleCachePaths,
                         scale_divisor: float | None, history_points: int = 1000,
                         keep_last: int = 1000, overlap_hours: int = 2) -> dict:
    paths.root.mkdir(parents=True, exist_ok=True)
    summary = {
        "epic": epic,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "history_points": history_points,
        "keep_last": keep_last,
        "timeframes": {},
    }
    path = paths.path("HOUR")
    existing = pl.read_parquet(path) if path.exists() else None
    request_points, request_plan = required_hour_points(existing, history_points, overlap_hours=overlap_hours)
    conversion = None
    try:
        conversion = convert_prices_to_candles(
            client.get_historical_prices(epic, "HOUR", request_points),
            scale_divisor=scale_divisor,
        )
        incoming = closed_candles(conversion.candles, 1)
        rate_limited = False
    except IGRateLimitError:
        if existing is None or not existing.height:
            raise
        incoming = pl.DataFrame()
        rate_limited = True
    hour = _merge(existing, incoming, keep_last)
    hour.write_parquet(path)
    summary["timeframes"]["HOUR"] = {
        "path": str(path),
        "rows": hour.height,
        "latest_timestamp": hour["timestamp"].max().isoformat() if hour.height else None,
        "rate_limited_using_existing_cache": rate_limited,
        "request_points": request_points,
        "request_plan": request_plan,
        "incoming_rows": incoming.height,
        "conversion_quality": conversion.quality_summary() if conversion else None,
    }

    four_hour = derive_four_hour_from_hour(hour, keep_last)
    four_hour_path = paths.path("HOUR_4")
    four_hour.write_parquet(four_hour_path)
    summary["timeframes"]["HOUR_4"] = {
        "path": str(four_hour_path),
        "rows": four_hour.height,
        "latest_timestamp": four_hour["timestamp"].max().isoformat() if four_hour.height else None,
        "source": "derived_from_cached_hour_utc_anchor",
        "anchor_utc_hours": [0, 4, 8, 12, 16, 20],
    }
    paths.metadata_path().write_text(json.dumps(summary, indent=2, default=str))
    return summary


def load_cached_candles(paths: CandleCachePaths) -> tuple[pl.DataFrame, pl.DataFrame]:
    return pl.read_parquet(paths.path("HOUR")), pl.read_parquet(paths.path("HOUR_4"))
