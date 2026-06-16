import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from .ig_live_signal import closed_candles, prices_to_candles
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


def refresh_candle_cache(*, client, epic: str, paths: CandleCachePaths,
                         scale_divisor: float | None, history_points: int = 1000,
                         keep_last: int = 1000) -> dict:
    paths.root.mkdir(parents=True, exist_ok=True)
    summary = {
        "epic": epic,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "history_points": history_points,
        "keep_last": keep_last,
        "timeframes": {},
    }
    for resolution, close_hours in (("HOUR", 1), ("HOUR_4", 4)):
        path = paths.path(resolution)
        existing = pl.read_parquet(path) if path.exists() else None
        try:
            incoming = closed_candles(
                prices_to_candles(
                    client.get_historical_prices(epic, resolution, history_points),
                    scale_divisor=scale_divisor,
                ),
                close_hours,
            )
            rate_limited = False
        except IGRateLimitError:
            if existing is None or not existing.height:
                raise
            incoming = pl.DataFrame()
            rate_limited = True
        merged = _merge(existing, incoming, keep_last)
        merged.write_parquet(path)
        summary["timeframes"][resolution] = {
            "path": str(path),
            "rows": merged.height,
            "latest_timestamp": merged["timestamp"].max().isoformat() if merged.height else None,
            "rate_limited_using_existing_cache": rate_limited,
        }
    paths.metadata_path().write_text(json.dumps(summary, indent=2, default=str))
    return summary


def load_cached_candles(paths: CandleCachePaths) -> tuple[pl.DataFrame, pl.DataFrame]:
    return pl.read_parquet(paths.path("HOUR")), pl.read_parquet(paths.path("HOUR_4"))
