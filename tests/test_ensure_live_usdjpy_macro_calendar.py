from datetime import datetime, timezone

import csv

from scripts.ensure_live_usdjpy_macro_calendar import calendar_covers, prune_calendar


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


def test_prune_calendar_uses_utc_retention_buffer(tmp_path):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "old,2026-07-21T20:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
        "recent,2026-07-22T20:00:00Z,United States,USD,FOMC,HIGH,,,,test\n"
        "future,2026-07-29T10:00:00Z,Japan,JPY,CPI,HIGH,,,,test\n"
    )

    result = prune_calendar(
        calendar,
        now_utc=datetime(2026, 7, 22, 21, 52, tzinfo=timezone.utc),
        retention_hours=24,
    )
    rows = list(csv.DictReader(calendar.open()))

    assert result["cutoff_utc"] == "2026-07-21T21:52:00+00:00"
    assert result["rows_before"] == 3
    assert result["rows_after"] == 2
    assert result["rows_pruned"] == 1
    assert [row["event_id"] for row in rows] == ["recent", "future"]
