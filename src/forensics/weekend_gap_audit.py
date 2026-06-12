from datetime import timedelta
from typing import Any

import polars as pl


def audit_weekend_gap(trade: dict[str, Any], ticks: pl.DataFrame) -> dict:
    entry, exit_ = trade["entry_timestamp_utc"], trade["exit_timestamp_utc"]
    friday = entry + timedelta(days=(4 - entry.weekday()) % 7)
    cutoff = friday.replace(hour=20, minute=30, second=0, microsecond=0)
    sunday = cutoff + timedelta(days=2, minutes=30)
    held = entry <= cutoff and exit_ >= sunday
    before = ticks.filter(pl.col("timestamp_utc") <= cutoff).tail(1)
    after = ticks.filter(pl.col("timestamp_utc") >= sunday).head(1)
    side = "bid" if trade["direction"] == "LONG" else "ask"
    gap = None
    first_tick = None
    if held and before.height and after.height:
        previous, opened = before.row(0, named=True), after.row(0, named=True)
        raw = opened[side] - previous[side]
        gap = (-raw if trade["direction"] == "LONG" else raw) / 0.01
        first_tick = opened["timestamp_utc"]
    risk_pips = abs(trade["entry_price"] - trade["initial_stop"]) / 0.01
    return {
        "trade_id": trade["trade_id"],
        "held_over_weekend": held,
        "entry_weekday": entry.strftime("%A"),
        "exit_weekday": exit_.strftime("%A"),
        "held_friday_close_to_sunday_open": held,
        "first_tick_after_weekend_open": first_tick,
        "weekend_gap_pips": gap,
        "price_gap_against_position_pips": max(gap, 0) if gap is not None else None,
        "weekend_gap_r": gap / risk_pips if gap is not None and risk_pips else None,
    }
