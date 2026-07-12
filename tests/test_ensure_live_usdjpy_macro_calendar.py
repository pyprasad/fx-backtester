from datetime import datetime, timezone

from scripts.ensure_live_usdjpy_macro_calendar import calendar_covers


def test_calendar_covers_future_window(tmp_path):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "future,2026-07-22T10:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
    )

    assert calendar_covers(
        calendar,
        now_utc=datetime(2026, 7, 12, tzinfo=timezone.utc),
        min_forward_days=7,
    )


def test_calendar_does_not_cover_when_latest_event_is_too_old(tmp_path):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "old,2026-07-13T10:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
    )

    assert not calendar_covers(
        calendar,
        now_utc=datetime(2026, 7, 12, tzinfo=timezone.utc),
        min_forward_days=7,
    )


def test_calendar_does_not_cover_missing_file(tmp_path):
    assert not calendar_covers(
        tmp_path / "missing.csv",
        now_utc=datetime(2026, 7, 12, tzinfo=timezone.utc),
        min_forward_days=7,
    )
