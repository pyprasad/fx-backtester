from datetime import datetime, timezone

import polars as pl

from src.forensics.weekend_gap_audit import audit_weekend_gap


def test_weekend_gap_against_short_is_detected():
    friday = datetime(2025, 1, 3, 20, 29, tzinfo=timezone.utc)
    sunday = datetime(2025, 1, 5, 21, 1, tzinfo=timezone.utc)
    ticks = pl.DataFrame({
        "timestamp_utc": [friday, sunday], "bid": [149.98, 150.48],
        "ask": [150.0, 150.5], "spread_pips": [2.0, 2.0],
    })
    trade = {
        "trade_id": "t", "direction": "SHORT", "entry_timestamp_utc": friday,
        "exit_timestamp_utc": sunday, "entry_price": 150.0, "initial_stop": 150.1,
    }
    result = audit_weekend_gap(trade, ticks)
    assert result["held_over_weekend"]
    assert round(result["price_gap_against_position_pips"], 6) == 50.0
