from src.stress.stress_metrics import distribution_metrics


def test_distribution_percentiles_and_probabilities():
    paths = [
        {"total_return_percent": value, "max_drawdown_percent": dd, "profit_factor": 2, "ruin_flag": False}
        for value, dd in [(-1, 16), (1, 11), (2, 5), (3, 4)]
    ]
    result = distribution_metrics(paths)
    assert result["probability_of_loss_percent"] == 25
    assert result["probability_drawdown_above_10_percent"] == 50
