import csv

from src.bakeoff.candidate_metrics import collect_candidate_metrics


def _write(path, row):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)


def test_collect_metrics_marks_missing_validation_layers(tmp_path):
    _write(tmp_path / "strategy_summary.csv", {
        "total_trades": 10, "total_return_percent": 5, "profit_factor": 2,
        "average_r": .4, "max_drawdown_percent": 1, "worst_trade_r": -2,
        "best_trade_r": 3, "win_rate": 50, "trades_per_month": 2,
    })
    _write(tmp_path / "funding_summary.csv", {
        "return_before_funding": 5, "return_after_funding": 4.9,
        "profit_factor_before_funding": 2, "profit_factor_after_funding": 1.9,
        "average_r_before_funding": .4, "average_r_after_funding": .39,
    })
    candidate = {"name": "ig_min_stop_only", "guardrail_variant_name": "ig_min_stop_only",
                 "description": "simple"}
    row = collect_candidate_metrics(candidate, tmp_path, {"accepted_signals": 10})
    assert row["return_after_funding"] == 4.9
    assert "monte_carlo_stress" in row["missing_validation_layers"]
