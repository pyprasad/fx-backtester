from src.bakeoff.candidate_report import build_recommendation, write_candidate_report


def test_recommendation_and_report(tmp_path):
    row = {
        "rank": 1, "candidate_name": "min_risk_3pips", "overall_score": 90,
        "recommendation": "SELECT", "return_after_funding": 60,
        "profit_factor_after_funding": 2.2, "average_r_after_funding": .4,
        "max_drawdown_percent": 1.5, "worst_trade_r": -2,
        "bootstrap_p5_return": 40, "bootstrap_p95_drawdown": 4,
        "execution_stress_failure_count": 0, "missing_validation_layers": "",
        "hard_fail_flag": False, "return_retention_vs_baseline": 95,
    }
    other = {**row, "rank": 2, "candidate_name": "ig_min_stop_only", "overall_score": 80}
    recommendation = build_recommendation([row, other])
    assert recommendation["recommended_candidate"] == "min_risk_3pips"
    assert recommendation["required_human_confirmation"] is True
    assert recommendation["do_not_auto_modify_baseline"] is True
    report = write_candidate_report(tmp_path, [row, other], [], recommendation, [])
    assert "Executive Summary" in report.read_text()
