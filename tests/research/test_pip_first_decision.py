import csv

from src.research.pip_first_decision import score_candidate, write_pip_first_decision_report


def test_score_candidate_flags_fragile_high_drawdown_candidate():
    summary = {
        "label": "aggressive",
        "total_trades": "100",
        "net_pips": "5000",
        "max_pip_drawdown": "450",
        "return_over_pip_drawdown": "11",
    }
    stress_rows = [
        {
            "label": "aggressive",
            "method": "bootstrap",
            "slippage_pips_per_execution": "0",
            "missed_trade_rate": "0",
            "p05_net_pips": "3000",
        },
        {
            "label": "aggressive",
            "method": "bootstrap",
            "slippage_pips_per_execution": "1",
            "missed_trade_rate": "0.1",
            "p05_net_pips": "1000",
        },
        {
            "label": "aggressive",
            "method": "miss_best",
            "slippage_pips_per_execution": "1",
            "missed_trade_rate": "0.1",
            "median_net_pips": "-4500",
        },
    ]

    row = score_candidate(summary, stress_rows)

    assert "HIGH_PIP_DRAWDOWN" in row["hard_flags"]
    assert "MISS_BEST_10_WITH_1PIP_SLIPPAGE_FRAGILE" in row["hard_flags"]


def test_write_pip_first_decision_report_selects_clean_candidate(tmp_path):
    comparison = tmp_path / "comparison.csv"
    stress = tmp_path / "stress.csv"
    comparison.write_text(
        "label,total_trades,net_pips,max_pip_drawdown,return_over_pip_drawdown\n"
        "clean,10,3000,150,20\n"
        "fragile,10,5000,450,12\n"
    )
    stress.write_text(
        "label,method,slippage_pips_per_execution,missed_trade_rate,p05_net_pips,median_net_pips\n"
        "clean,bootstrap,0,0,2500,3000\n"
        "clean,bootstrap,1,0.1,800,1500\n"
        "clean,miss_best,1,0.1,-1000,-1000\n"
        "fragile,bootstrap,0,0,3500,5000\n"
        "fragile,bootstrap,1,0.1,1000,2500\n"
        "fragile,miss_best,1,0.1,-4500,-4500\n"
    )

    output = write_pip_first_decision_report(
        comparison_summary_path=comparison,
        stress_summary_path=stress,
        output_path=tmp_path / "decision",
    )

    with (output / "pip_first_decision_summary.csv").open() as handle:
        rows = list(csv.DictReader(handle))

    selected = next(row for row in rows if row["recommendation"])
    assert selected["label"] == "clean"
    assert (output / "pip_first_decision_report.html").exists()
