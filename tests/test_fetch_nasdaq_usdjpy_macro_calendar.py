from datetime import date, time

from scripts.fetch_nasdaq_usdjpy_macro_calendar import normalise_rows, parse_gmt_time


def test_parse_gmt_time_accepts_hh_mm():
    assert parse_gmt_time("08:30") == time(8, 30)


def test_parse_gmt_time_skips_non_fixed_time():
    assert parse_gmt_time("Tentative") is None
    assert parse_gmt_time("All Day") is None


def test_normalise_rows_filters_usdjpy_high_impact_events():
    rows = [
        {
            "gmt": "12:30",
            "country": "United States",
            "eventName": "Consumer Price Index",
            "actual": "3.3%",
            "consensus": "3.4%",
            "previous": "3.4%",
        },
        {
            "gmt": "01:30",
            "country": "Japan",
            "eventName": "Tokyo Core CPI",
            "actual": "2.1%",
            "consensus": "2.0%",
            "previous": "2.0%",
        },
        {
            "gmt": "10:00",
            "country": "Germany",
            "eventName": "German Factory Orders",
        },
        {
            "gmt": "11:00",
            "country": "United States",
            "eventName": "Low Relevance Survey",
        },
    ]

    events = normalise_rows(date(2024, 6, 12), rows)

    assert [event.currency for event in events] == ["USD", "JPY"]
    assert [event.impact for event in events] == ["HIGH", "HIGH"]
    assert events[0].event_time_utc.isoformat() == "2024-06-12T12:30:00+00:00"
