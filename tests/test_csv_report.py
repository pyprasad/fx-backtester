import csv

from src.reporting.csv_report import _write


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
