from datetime import datetime, timezone

from src.news_guard.blackout import is_news_blackout
from src.news_guard.models import EconomicEvent


def _event():
    return EconomicEvent(
        "nfp",
        datetime(2024, 7, 5, 12, 30, tzinfo=timezone.utc),
        "United States",
        "USD",
        "Non Farm Payrolls",
        "HIGH",
    )


def test_news_blackout_includes_before_at_and_after_boundaries():
    event = _event()
    for timestamp in (
        datetime(2024, 7, 5, 11, 30, tzinfo=timezone.utc),
        datetime(2024, 7, 5, 12, 30, tzinfo=timezone.utc),
        datetime(2024, 7, 5, 13, 30, tzinfo=timezone.utc),
    ):
        blocked, matched = is_news_blackout(timestamp, [event], 60, 60)
        assert blocked is True
        assert matched == event


def test_news_blackout_false_outside_window_and_handles_naive_utc():
    event = _event()

    assert is_news_blackout(datetime(2024, 7, 5, 11, 29, tzinfo=timezone.utc), [event], 60, 60) == (False, None)
    assert is_news_blackout(datetime(2024, 7, 5, 13, 31), [event], 60, 60) == (False, None)
