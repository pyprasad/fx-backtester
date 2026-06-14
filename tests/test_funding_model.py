from datetime import datetime, timezone
from types import SimpleNamespace

from src.broker_guardrails.funding_model import calculate_trade_funding, funding_cutoffs


def _settings():
    return {"timezone": "Europe/London", "cutoff_time": "22:00",
            "apply_wednesday_triple_rollover": True}


def test_funding_events_and_wednesday_triple():
    monday = funding_cutoffs(
        datetime(2025, 1, 6, 21, tzinfo=timezone.utc),
        datetime(2025, 1, 6, 23, tzinfo=timezone.utc), _settings(),
    )
    wednesday = funding_cutoffs(
        datetime(2025, 1, 8, 21, tzinfo=timezone.utc),
        datetime(2025, 1, 8, 23, tzinfo=timezone.utc), _settings(),
    )
    assert len(monday) == len(wednesday) == 1
    trade = SimpleNamespace(
        trade_id="x", entry_timestamp_utc=datetime(2025, 1, 8, 21, tzinfo=timezone.utc),
        exit_timestamp_utc=datetime(2025, 1, 8, 23, tzinfo=timezone.utc),
        initial_risk_pips=10, pnl_r=1, net_pnl=25, risk_amount=25,
    )
    row, events = calculate_trade_funding(trade, _settings(), .1)
    assert row["funding_days"] == 3
    assert row["estimated_funding_r"] == .03
    assert events[0]["funding_days"] == 3


def test_no_cutoff_and_zero_risk_are_safe():
    trade = SimpleNamespace(
        trade_id="x", entry_timestamp_utc=datetime(2025, 1, 6, 10, tzinfo=timezone.utc),
        exit_timestamp_utc=datetime(2025, 1, 6, 11, tzinfo=timezone.utc),
        initial_risk_pips=0, pnl_r=1, net_pnl=25, risk_amount=25,
    )
    row, events = calculate_trade_funding(trade, _settings(), .1)
    assert not events
    assert row["estimated_funding_r"] == 0
