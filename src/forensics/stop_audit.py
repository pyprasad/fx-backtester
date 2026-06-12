import re
from datetime import datetime, timezone
from typing import Any

import polars as pl


def _stop_history(value: Any) -> list[dict]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    pattern = (
        r"'timestamp': datetime\.datetime\((\d+), (\d+), (\d+), (\d+), (\d+), (\d+), "
        r"(\d+), tzinfo=zoneinfo\.ZoneInfo\(key='UTC'\)\), 'price': ([0-9.]+), "
        r"'reason': '([^']+)'"
    )
    return [
        {
            "timestamp": datetime(
                int(year), int(month), int(day), int(hour), int(minute), int(second),
                int(microsecond), tzinfo=timezone.utc,
            ),
            "price": float(price),
            "reason": reason,
        }
        for year, month, day, hour, minute, second, microsecond, price, reason
        in re.findall(pattern, str(value))
    ]


def audit_stop_path(trade: dict[str, Any], ticks: pl.DataFrame, tolerance: float = 0.000001) -> dict:
    """Replay executable-side ticks. If stop and target coincide, the stop wins."""
    direction = trade["direction"]
    side = "bid" if direction == "LONG" else "ask"
    stop, final_stop, target = trade["initial_stop"], trade.get("final_stop"), trade["target_price"]
    history = _stop_history(trade.get("stop_history"))
    active_stop, active_reason, history_index = stop, "initial", 0
    initial_cross = final_cross = target_cross = first_barrier = None
    for row in ticks.sort("timestamp_utc").iter_rows(named=True):
        while history_index < len(history) and history[history_index]["timestamp"] <= row["timestamp_utc"]:
            active_stop = history[history_index]["price"]
            active_reason = history[history_index]["reason"]
            history_index += 1
        price = row[side]
        initial_hit = price <= stop + tolerance if direction == "LONG" else price >= stop - tolerance
        final_hit = (
            price <= final_stop + tolerance if direction == "LONG" else price >= final_stop - tolerance
        ) if final_stop is not None else False
        active_hit = (
            price <= active_stop + tolerance if direction == "LONG" else price >= active_stop - tolerance
        )
        target_hit = price >= target - tolerance if direction == "LONG" else price <= target + tolerance
        item = {"timestamp": row["timestamp_utc"], "price": price, "spread_pips": row["spread_pips"]}
        initial_cross = initial_cross or (item if initial_hit else None)
        final_cross = final_cross or (item if final_hit else None)
        target_cross = target_cross or (item if target_hit else None)
        stop_barrier_hit = active_hit if history else initial_hit
        if first_barrier is None and (stop_barrier_hit or target_hit):
            reason = (
                "trailing_stop" if stop_barrier_hit and active_reason != "initial"
                else ("stop_loss" if stop_barrier_hit else "take_profit")
            )
            first_barrier = {**item, "reason": reason}
    expected = first_barrier["reason"] if first_barrier else None
    actual = trade["exit_reason"]
    stop_before_exit = bool(initial_cross and initial_cross["timestamp"] < trade["exit_timestamp_utc"])
    target_before_exit = bool(target_cross and target_cross["timestamp"] < trade["exit_timestamp_utc"])
    return {
        "trade_id": trade["trade_id"],
        "was_initial_stop_crossed": bool(initial_cross),
        "initial_stop_first_cross_timestamp": initial_cross["timestamp"] if initial_cross else None,
        "initial_stop_first_cross_price": initial_cross["price"] if initial_cross else None,
        "was_final_stop_crossed": bool(final_cross),
        "final_stop_first_cross_timestamp": final_cross["timestamp"] if final_cross else None,
        "was_target_crossed": bool(target_cross),
        "target_first_cross_timestamp": target_cross["timestamp"] if target_cross else None,
        "did_stop_cross_before_recorded_exit": stop_before_exit,
        "did_target_cross_before_recorded_exit": target_before_exit,
        "first_barrier_timestamp": first_barrier["timestamp"] if first_barrier else None,
        "first_barrier_price": first_barrier["price"] if first_barrier else None,
        "expected_exit_reason_if_first_barrier_wins": expected,
        "expected_exit_price": first_barrier["price"] if first_barrier else None,
        "actual_exit_reason": actual,
        "actual_exit_price": trade["exit_price"],
        "spread_at_stop_cross_pips": initial_cross["spread_pips"] if initial_cross else None,
        "exit_reason_matches_tick_path": expected in {None, actual} or (
            expected == "trailing_stop" and actual == "stop_loss"
        ),
    }
