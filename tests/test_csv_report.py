import csv

from src.reporting.csv_report import _write, write_csv_reports


def test_write_supports_rows_with_different_fields(tmp_path):
    path = tmp_path / "heterogeneous.csv"

    _write(path, [
        {"timestamp": "first", "reason": "ordinary_rejection"},
        {
            "timestamp": "second",
            "reason": "guardrail_rejection",
            "rejection_group": "MIN_RISK",
            "initial_risk_pips": 1.5,
        },
    ])

    with path.open() as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "timestamp": "first",
            "reason": "ordinary_rejection",
            "rejection_group": "",
            "initial_risk_pips": "",
        },
        {
            "timestamp": "second",
            "reason": "guardrail_rejection",
            "rejection_group": "MIN_RISK",
            "initial_risk_pips": "1.5",
        },
    ]


def test_write_csv_reports_writes_news_guard_skipped_signals(tmp_path):
    write_csv_reports(tmp_path, [], {"starting_balance": 10000}, [
        {"timestamp": "ordinary", "reason": "outside_session"},
        {"timestamp": "news", "reason": "NEWS_BLACKOUT", "event_id": "nfp"},
    ])

    with (tmp_path / "news_guard_skipped_signals.csv").open() as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [{"timestamp": "news", "reason": "NEWS_BLACKOUT", "event_id": "nfp"}]
