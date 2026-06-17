from pathlib import Path

import pytest

from src.news_guard.calendar_loader import load_economic_events


def test_loads_filters_and_sorts_events_with_z_timestamps(tmp_path: Path):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "medium,2024-06-13T12:30:00Z,United States,USD,Medium Event,MEDIUM,,,,manual\n"
        "jpy,2024-06-12T03:00:00Z,Japan,jpy,BoJ,HIGH,,,,manual\n"
        "eur,2024-06-11T12:30:00Z,EU,EUR,ECB,HIGH,,,,manual\n"
        "usd,2024-06-12T12:30:00Z,United States,usd,CPI,HIGH,3.3,3.4,3.4,manual\n"
    )

    events = load_economic_events(calendar, ["USD", "JPY"], ["HIGH"])

    assert [event.event_id for event in events] == ["jpy", "usd"]
    assert events[0].currency == "JPY"
    assert events[1].impact == "HIGH"
    assert events[1].event_time_utc.isoformat() == "2024-06-12T12:30:00+00:00"


def test_empty_calendar_file_returns_no_events(tmp_path: Path):
    calendar = tmp_path / "events.csv"
    calendar.write_text("")

    assert load_economic_events(calendar, ["USD"], ["HIGH"]) == []


def test_missing_calendar_file_raises_clear_error(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="News guard calendar file not found"):
        load_economic_events(tmp_path / "missing.csv", ["USD"], ["HIGH"])

