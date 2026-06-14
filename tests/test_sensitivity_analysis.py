from src.robustness.sensitivity_analysis import paired_summary, sensitivity_level


def test_sensitivity_levels_and_paired_summary():
    baseline = {"total_return_percent": 10}
    good = {"total_return_percent": 9, "profit_factor": 1.6, "pass_flag": True}
    bad = {**good, "pass_flag": False}
    assert sensitivity_level(baseline, good) == "LOW"
    assert sensitivity_level(baseline, bad) == "CLIFF"
    rows = [{
        "run_status": "SUCCESS", "pass_flag": True, "total_return_percent": 10,
        "profit_factor": 1.5, "average_r": 0.2, "max_drawdown_percent": 2, "worst_trade_r": -2,
    }] * 4
    assert paired_summary("pair", rows)["verdict"] == "STRONG"
