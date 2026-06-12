from datetime import datetime, timedelta, timezone

import polars as pl

from src.forensics.stop_audit import audit_stop_path


def _trade(direction="SHORT"):
    now = datetime(2025, 1, 3, 10, tzinfo=timezone.utc)
    return {
        "trade_id": "t", "direction": direction, "entry_timestamp_utc": now,
        "exit_timestamp_utc": now + timedelta(seconds=2), "entry_price": 150.0,
        "exit_price": 150.1, "initial_stop": 150.1 if direction == "SHORT" else 149.9,
        "final_stop": 150.1 if direction == "SHORT" else 149.9,
        "target_price": 149.8 if direction == "SHORT" else 150.2, "exit_reason": "stop_loss",
    }


def _ticks(rows):
    now = datetime(2025, 1, 3, 10, tzinfo=timezone.utc)
    return pl.DataFrame({
        "timestamp_utc": [now + timedelta(seconds=i) for i in range(len(rows))],
        "bid": [row[0] for row in rows], "ask": [row[1] for row in rows],
        "spread_pips": [(row[1] - row[0]) / 0.01 for row in rows],
    })


def test_short_stop_and_target_use_ask():
    stop = audit_stop_path(_trade(), _ticks([(150.0, 150.02), (150.05, 150.1)]))
    assert stop["was_initial_stop_crossed"]
    target_trade = _trade()
    target_trade["exit_reason"] = "take_profit"
    target = audit_stop_path(target_trade, _ticks([(149.82, 149.84), (149.78, 149.8)]))
    assert target["was_target_crossed"]


def test_long_stop_and_target_use_bid():
    stop = audit_stop_path(_trade("LONG"), _ticks([(150.0, 150.02), (149.9, 149.92)]))
    assert stop["was_initial_stop_crossed"]
    target_trade = _trade("LONG")
    target_trade["exit_reason"] = "take_profit"
    target = audit_stop_path(target_trade, _ticks([(150.1, 150.12), (150.2, 150.22)]))
    assert target["was_target_crossed"]


def test_timestamped_stop_history_replays_active_trailing_stop():
    trade = _trade()
    now = trade["entry_timestamp_utc"]
    trade["initial_stop"] = 150.2
    trade["final_stop"] = 149.95
    trade["exit_reason"] = "trailing_stop"
    trade["stop_history"] = [
        {"timestamp": now, "price": 150.2, "reason": "initial"},
        {"timestamp": now + timedelta(seconds=1), "price": 149.95, "reason": "trailing"},
    ]
    result = audit_stop_path(trade, _ticks([(150.0, 150.02), (149.9, 149.92), (149.94, 149.96)]))
    assert result["expected_exit_reason_if_first_barrier_wins"] == "trailing_stop"
    assert result["exit_reason_matches_tick_path"]


def test_breakeven_stop_exit_matches_engine_trailing_stop_reason():
    trade = _trade()
    now = trade["entry_timestamp_utc"]
    trade["initial_stop"] = 150.2
    trade["final_stop"] = 150.0
    trade["exit_reason"] = "trailing_stop"
    trade["stop_history"] = [
        {"timestamp": now, "price": 150.2, "reason": "initial"},
        {"timestamp": now + timedelta(seconds=1), "price": 150.0, "reason": "breakeven"},
    ]
    result = audit_stop_path(trade, _ticks([(149.9, 149.92), (149.95, 149.97), (149.99, 150.01)]))
    assert result["expected_exit_reason_if_first_barrier_wins"] == "trailing_stop"
    assert result["exit_reason_matches_tick_path"]
