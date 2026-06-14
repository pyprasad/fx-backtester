from src.stress.stress_report import write_stress_report


def test_stress_report(tmp_path):
    distribution = {"p5_return_percent": 1, "p95_max_drawdown_percent": 2,
                    "probability_of_loss_percent": 0, "probability_drawdown_above_10_percent": 0}
    path = write_stress_report(tmp_path, {}, {"stress_score": 90, "verdict": "STRONG_STRESS_RESILIENCE"},
                               distribution, [], [], [], [], [])
    assert "Executive Summary" in path.read_text()
    assert "does not make the strategy production-ready" in path.read_text()
