from datetime import time
from uuid import uuid4

import polars as pl

from src.config.schemas import StrategyConfig

from .signal import Signal


def _session(timestamp, windows: list[dict]) -> str | None:
    current = timestamp.time()
    for window in windows:
        start, end = time.fromisoformat(window["start"]), time.fromisoformat(window["end"])
        if start <= current <= end:
            return window["name"]
    return None


def generate_signals(entry: pl.DataFrame, trend: pl.DataFrame, config: StrategyConfig) -> tuple[list[Signal], list[dict]]:
    trend_view = trend.select("timestamp", pl.col("mid_close").alias("trend_close"), "ema_200")
    joined = entry.sort("timestamp").join_asof(trend_view.sort("timestamp"), on="timestamp", strategy="backward")
    signals, rejected = [], []
    rows = joined.with_columns(pl.col("rsi_14").shift(1).alias("previous_rsi")).to_dicts()
    for row in rows:
        if any(row.get(k) is None for k in ("atr_14", "ema_20", "ema_50", "rsi_14", "ema_200")):
            continue
        london = row["timestamp_london"]
        session = _session(london, config.session_filter["entry_windows"])
        spread_pips = row["spread_avg"] / 0.01
        common_reason = None
        if not session:
            common_reason = "outside_session"
        elif config.market_open_filter.get("avoid_sunday_open") and london.weekday() == 6:
            common_reason = "sunday_open"
        elif spread_pips > config.spread_filter["max_spread_pips"]:
            common_reason = "spread_too_high"
        if common_reason:
            rejected.append({"timestamp": row["timestamp"], "reason": common_reason})
            continue
        bearish = row["mid_close"] < row["mid_open"]
        near_ema = min(abs(row["mid_close"] - row["ema_20"]), abs(row["mid_close"] - row["ema_50"])) <= (
            config.entry["short"]["max_pullback_atr"] * row["atr_14"]
        )
        rsi_down = row["rsi_14"] < 50 and row["previous_rsi"] is not None and row["rsi_14"] < row["previous_rsi"]
        if config.entry["short"]["enabled"] and row["trend_close"] < row["ema_200"] and row["mid_close"] < row["ema_50"] and near_ema and rsi_down and bearish:
            stop = max(row["mid_high"], row["mid_close"] + config.stop_loss["atr_multiplier"] * row["atr_14"])
            risk = stop - row["mid_close"]
            signals.append(Signal(
                str(uuid4()), row["timestamp"], london, row["symbol"], "SHORT",
                "market_on_next_tick_after_signal_close", row["mid_close"], "4H", "1H",
                ["trend_below_ema200", "pullback", "rsi_rejection", "bearish_close"],
                {k: row[k] for k in ("ema_20", "ema_50", "ema_200", "rsi_14", "atr_14", "atr_14_pips")},
                stop, row["mid_close"] - config.exit["runner"]["final_target_r"] * risk, spread_pips, session,
            ))
        if config.entry["long"]["enabled"]:
            bullish = row["mid_close"] > row["mid_open"]
            rsi_up = row["rsi_14"] > 50 and row["previous_rsi"] is not None and row["rsi_14"] > row["previous_rsi"]
            if row["trend_close"] > row["ema_200"] and row["mid_close"] > row["ema_50"] and near_ema and rsi_up and bullish:
                stop = min(row["mid_low"], row["mid_close"] - config.stop_loss["atr_multiplier"] * row["atr_14"])
                risk = row["mid_close"] - stop
                signals.append(Signal(
                    str(uuid4()), row["timestamp"], london, row["symbol"], "LONG",
                    "market_on_next_tick_after_signal_close", row["mid_close"], "4H", "1H",
                    ["trend_above_ema200", "pullback", "rsi_reclaim", "bullish_close"],
                    {k: row[k] for k in ("ema_20", "ema_50", "ema_200", "rsi_14", "atr_14", "atr_14_pips")},
                    stop, row["mid_close"] + config.exit["runner"]["final_target_r"] * risk, spread_pips, session,
                ))
    return signals, rejected
