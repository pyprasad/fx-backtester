import csv
from pathlib import Path

import pytest

from src.research.strategy_group import StrategyGroupResearchRunner, parse_strategy_run


def _write_trade_log(path: Path, rows: list[dict]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    fields = [
        "trade_id", "symbol", "direction", "entry_timestamp_utc", "exit_timestamp_utc",
        "net_pnl", "pnl_r", "session", "exit_reason", "signal_timestamp_utc",
    ]
    with (path / "trade_log.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_parse_strategy_run_uses_label_and_resolved_path(tmp_path):
    parsed = parse_strategy_run(f"baseline={tmp_path}")

    assert parsed.label == "baseline"
    assert parsed.path == tmp_path.resolve()


def test_strategy_group_research_writes_attribution_and_overlap_reports(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_trade_log(first, [
        {
            "trade_id": "a1", "symbol": "USDJPY", "direction": "SHORT",
            "entry_timestamp_utc": "2025-01-02T09:00:00+00:00",
            "exit_timestamp_utc": "2025-01-02T12:00:00+00:00",
            "net_pnl": "100", "pnl_r": "1.0", "session": "London morning",
            "exit_reason": "take_profit", "signal_timestamp_utc": "2025-01-02T08:00:00+00:00",
        },
        {
            "trade_id": "a2", "symbol": "USDJPY", "direction": "SHORT",
            "entry_timestamp_utc": "2025-01-03T09:00:00+00:00",
            "exit_timestamp_utc": "2025-01-03T12:00:00+00:00",
            "net_pnl": "-50", "pnl_r": "-0.5", "session": "Tokyo",
            "exit_reason": "stop_loss", "signal_timestamp_utc": "2025-01-03T08:00:00+00:00",
        },
    ])
    _write_trade_log(second, [
        {
            "trade_id": "b1", "symbol": "USDJPY", "direction": "SHORT",
            "entry_timestamp_utc": "2025-01-03T10:00:00+00:00",
            "exit_timestamp_utc": "2025-01-03T13:00:00+00:00",
            "net_pnl": "-75", "pnl_r": "-0.75", "session": "Tokyo",
            "exit_reason": "stop_loss", "signal_timestamp_utc": "2025-01-03T09:00:00+00:00",
        },
    ])

    output = StrategyGroupResearchRunner(
        [parse_strategy_run(f"baseline={first}"), parse_strategy_run(f"atr15={second}")],
        tmp_path / "group",
    ).run()

    assert (output / "strategy_group_report.html").exists()
    attribution = (output / "strategy_attribution.csv").read_text()
    assert "baseline" in attribution
    assert "atr15" in attribution
    overlap = (output / "strategy_overlap_matrix.csv").read_text()
    assert "both_losing_overlap_pairs" in overlap
    duplicate = (output / "duplicate_entry_matrix.csv").read_text()
    assert "exact_signal_entry_duplicates" in duplicate
    deployment = (output / "deployment_risk_summary.csv").read_text()
    assert "deployment_role" in deployment
    conflicts = (output / "overlap_loss_conflicts.csv").read_text()
    assert "combined_pnl" in conflicts
    assert "-125.0" in conflicts


def test_strategy_group_research_requires_trade_logs(tmp_path):
    with pytest.raises(FileNotFoundError):
        StrategyGroupResearchRunner(
            [parse_strategy_run(f"missing={tmp_path / 'missing'}"), parse_strategy_run(f"also_missing={tmp_path / 'x'}")],
            tmp_path / "group",
        ).run()
