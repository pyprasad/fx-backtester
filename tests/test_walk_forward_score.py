import polars as pl

from src.walk_forward.walk_forward_score import calculate_walk_forward_score


def test_strong_and_penalised_scores():
    anchored = pl.DataFrame({
        "test_positive_flag": [True, True], "test_return_percent": [2.0, 3.0],
        "test_profit_factor": [2.0, 2.0], "test_worst_trade_r": [-1.0, -1.0],
        "test_max_drawdown_percent": [2.0, 2.0], "low_test_sample_warning": [False, False],
        "profit_factor_decay_percent": [0.0, 0.0], "average_r_decay_percent": [0.0, 0.0],
    })
    rolling = anchored.drop("profit_factor_decay_percent", "average_r_decay_percent")
    summary = pl.DataFrame({"avg_test_profit_factor": [2.0], "low_sample_warning": [False],
                            "verdict": ["STRONG"]})
    assert calculate_walk_forward_score(anchored, rolling, summary)["verdict"] == "STRONG_WALK_FORWARD"
    weak = anchored.with_columns(pl.lit(False).alias("test_positive_flag"),
                                 pl.lit(-3.0).alias("test_worst_trade_r"))
    assert calculate_walk_forward_score(weak, rolling, summary)["walk_forward_score"] < 100
