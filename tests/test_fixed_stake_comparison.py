import csv

from src.reporting.fixed_stake_comparison import write_fixed_stake_comparison


def _write(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def test_comparison_confirms_strategy_logic_and_writes_all_formats(tmp_path):
    baseline, fixed = tmp_path / "baseline", tmp_path / "fixed"
    common = {
        "entry_timestamp_utc": "2025-01-01T10:00:00+00:00",
        "exit_timestamp_utc": "2025-01-01T11:00:00+00:00",
        "exit_reason": "take_profit",
    }
    _write(baseline / "trade_log.csv", {**common, "net_pnl": 20, "size": 100})
    _write(fixed / "trade_log.csv", {**common, "pnl_pips": 20, "planned_loss_gbp": 0.2})
    _write(baseline / "strategy_summary.csv", {"total_return_percent": 65, "worst_trade_r": -2})
    _write(fixed / "strategy_summary.csv", {
        "total_return_percent": 0.01, "net_profit_gbp": 0.8, "total_pips": 20,
        "max_drawdown_gbp": 0, "worst_trade_r": -2,
    })

    result = write_fixed_stake_comparison(baseline, fixed, tmp_path / "comparison")

    assert result["strategy_logic_matches"] is True
    assert (tmp_path / "comparison.csv").exists()
    assert (tmp_path / "comparison.json").exists()
    assert (tmp_path / "comparison.html").exists()
