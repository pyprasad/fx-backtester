from src.stress.stress_score import calculate_stress_score


def test_strong_and_weak_scores():
    distribution = {
        "p5_return_percent": 10, "probability_of_loss_percent": 0,
        "p95_max_drawdown_percent": 5, "p99_max_drawdown_percent": 7,
        "probability_drawdown_above_15_percent": 0, "median_profit_factor": 2,
    }
    assert calculate_stress_score(distribution, [{"scenario_name": "x", "total_return_percent": 1}],
                                  [], [], [])["verdict"] == "STRONG_STRESS_RESILIENCE"
    distribution["p5_return_percent"] = -1
    assert calculate_stress_score(distribution, [], [], [], [])["stress_score"] < 100


def test_execution_tail_warning_prevents_strong_verdict():
    distribution = {
        "p5_return_percent": 10, "probability_of_loss_percent": 0,
        "p95_max_drawdown_percent": 5, "p99_max_drawdown_percent": 7,
        "probability_drawdown_above_15_percent": 0, "median_profit_factor": 2,
    }
    score = calculate_stress_score(distribution, [{
        "scenario_name": "slippage_1.0_both", "total_return_percent": 20,
        "profit_factor": 1.5, "worst_trade_r": -6,
    }], [], [], [])
    assert score["verdict"] == "PASS"
    assert score["execution_tail_warning"]
