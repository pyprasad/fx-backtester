from typing import Any

import polars as pl


def audit_execution(
    trade: dict[str, Any],
    ticks: pl.DataFrame,
    signal_timestamp=None,
    tolerance: float = 0.000001,
    slippage: float = 0.0,
) -> dict:
    entry_tick = ticks.filter(pl.col("timestamp_utc") == trade["entry_timestamp_utc"])
    exit_tick = ticks.filter(pl.col("timestamp_utc") == trade["exit_timestamp_utc"])
    entry = entry_tick.row(0, named=True) if entry_tick.height else None
    exit_ = exit_tick.row(0, named=True) if exit_tick.height else None
    is_long = trade["direction"] == "LONG"
    expected_entry = (entry["ask"] + slippage if is_long else entry["bid"] - slippage) if entry else None
    expected_exit = (exit_["bid"] - slippage if is_long else exit_["ask"] + slippage) if exit_ else None
    first_after = None
    if signal_timestamp is not None:
        after = ticks.filter(pl.col("timestamp_utc") > signal_timestamp).head(1)
        first_after = after.row(0, named=True) if after.height else None
    return {
        "trade_id": trade["trade_id"],
        "entry_tick_found": entry is not None,
        "exit_tick_found": exit_ is not None,
        "expected_entry_side": "ask" if is_long else "bid",
        "expected_exit_side": "bid" if is_long else "ask",
        "expected_entry_price": expected_entry,
        "expected_exit_price": expected_exit,
        "entry_side_matches": entry is not None and abs(trade["entry_price"] - expected_entry) <= tolerance,
        "exit_side_matches": exit_ is not None and abs(trade["exit_price"] - expected_exit) <= tolerance,
        "first_tick_after_signal_timestamp": first_after["timestamp_utc"] if first_after else None,
        "entry_delay_seconds": (
            (trade["entry_timestamp_utc"] - signal_timestamp).total_seconds()
            if signal_timestamp is not None else None
        ),
        "entry_after_signal_close": (
            trade["entry_timestamp_utc"] > signal_timestamp if signal_timestamp is not None else None
        ),
        "entry_is_first_tick_after_signal": (
            first_after is not None and first_after["timestamp_utc"] == trade["entry_timestamp_utc"]
            if signal_timestamp is not None else None
        ),
        "entry_spread_matches": (
            entry is not None and abs(trade["spread_pips_at_entry"] - entry["spread_pips"]) <= tolerance
        ),
        "exit_spread_matches": (
            exit_ is not None and abs(trade["spread_pips_at_exit"] - exit_["spread_pips"]) <= tolerance
        ),
    }
