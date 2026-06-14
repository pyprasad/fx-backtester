from datetime import datetime, timezone

from src.broker_guardrails.time_guard import validate_entry_time


def test_time_guard_is_inclusive_and_respects_bst(strategy_config):
    settings = strategy_config.broker_execution_guardrails
    assert validate_entry_time(datetime(2025, 1, 1, 21, 29, tzinfo=timezone.utc), settings).accepted
    assert not validate_entry_time(datetime(2025, 1, 1, 21, 30, tzinfo=timezone.utc), settings).accepted
    # During BST, 20:30 UTC is 21:30 UK and is blocked.
    assert not validate_entry_time(datetime(2025, 7, 1, 20, 30, tzinfo=timezone.utc), settings).accepted
