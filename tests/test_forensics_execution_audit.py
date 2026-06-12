from datetime import datetime, timedelta, timezone

import polars as pl

from src.forensics.execution_audit import audit_execution


def test_entry_alignment_and_wrong_short_sides_are_detected():
    signal = datetime(2025, 1, 1, 10, tzinfo=timezone.utc)
    entry, exit_ = signal + timedelta(seconds=1), signal + timedelta(seconds=2)
    ticks = pl.DataFrame({
        "timestamp_utc": [entry, exit_], "bid": [150.0, 149.8], "ask": [150.02, 149.82],
        "spread_pips": [2.0, 2.0],
    })
    trade = {
        "trade_id": "t", "direction": "SHORT", "entry_timestamp_utc": entry,
        "exit_timestamp_utc": exit_, "entry_price": 150.02, "exit_price": 149.8,
        "spread_pips_at_entry": 2.0, "spread_pips_at_exit": 2.0,
    }
    result = audit_execution(trade, ticks, signal)
    assert result["entry_after_signal_close"]
    assert result["entry_is_first_tick_after_signal"]
    assert not result["entry_side_matches"]
    assert not result["exit_side_matches"]


def test_entry_before_signal_fails():
    signal = datetime(2025, 1, 1, 10, tzinfo=timezone.utc)
    entry = signal - timedelta(seconds=1)
    ticks = pl.DataFrame({"timestamp_utc": [entry], "bid": [150.0], "ask": [150.02], "spread_pips": [2.0]})
    trade = {"trade_id": "t", "direction": "SHORT", "entry_timestamp_utc": entry, "exit_timestamp_utc": entry,
             "entry_price": 150.0, "exit_price": 150.02, "spread_pips_at_entry": 2.0, "spread_pips_at_exit": 2.0}
    assert audit_execution(trade, ticks, signal)["entry_after_signal_close"] is False
