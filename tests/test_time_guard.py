from datetime import datetime, timezone

from src.broker_guardrails.time_guard import validate_entry_time, weekend_market_hibernate_window


def test_time_guard_is_inclusive_and_respects_bst(strategy_config):
    settings = strategy_config.broker_execution_guardrails
    assert validate_entry_time(datetime(2025, 1, 1, 21, 29, tzinfo=timezone.utc), settings).accepted
    assert not validate_entry_time(datetime(2025, 1, 1, 21, 30, tzinfo=timezone.utc), settings).accepted
    # During BST, 20:30 UTC is 21:30 UK and is blocked.
    assert not validate_entry_time(datetime(2025, 7, 1, 20, 30, tzinfo=timezone.utc), settings).accepted


def test_weekend_hibernate_blocks_saturday_tokyo_session_and_resumes_sunday_uk_time():
    saturday_tokyo_open = weekend_market_hibernate_window(
        datetime(2026, 7, 25, 0, 0, 1, tzinfo=timezone.utc)
    )
    before_sunday_resume = weekend_market_hibernate_window(
        datetime(2026, 7, 26, 21, 59, tzinfo=timezone.utc)
    )
    after_sunday_resume = weekend_market_hibernate_window(
        datetime(2026, 7, 26, 22, 0, tzinfo=timezone.utc)
    )

    assert saturday_tokyo_open.enabled
    assert saturday_tokyo_open.resume_at_local.isoformat() == "2026-07-26T23:00:00+01:00"
    assert saturday_tokyo_open.resume_at_utc.isoformat() == "2026-07-26T22:00:00+00:00"
    assert before_sunday_resume.enabled
    assert not after_sunday_resume.enabled


def test_weekend_hibernate_starts_after_friday_uk_close():
    before_close = weekend_market_hibernate_window(
        datetime(2026, 7, 24, 20, 59, tzinfo=timezone.utc)
    )
    after_close = weekend_market_hibernate_window(
        datetime(2026, 7, 24, 21, 0, tzinfo=timezone.utc)
    )

    assert not before_close.enabled
    assert after_close.enabled
    assert after_close.resume_at_local.isoformat() == "2026-07-26T23:00:00+01:00"
