from src.robustness.robustness_score import calculate_robustness_score


def test_strong_robustness_score():
    row = {
        "run_status": "SUCCESS", "variant_name": "baseline_original", "profitable_flag": True,
        "pass_flag": True, "profit_factor": 1.7, "average_r": 0.3,
        "max_drawdown_percent": 2, "total_trades": 100, "total_return_percent": 20,
        "worst_trade_r": -2,
    }
    score = calculate_robustness_score([row] * 3, [], [], {
        "baseline_isolated_flag": False, "neighbourhood_pass_percent": 100,
    })
    assert score["verdict"] == "STRONG_ROBUSTNESS"
