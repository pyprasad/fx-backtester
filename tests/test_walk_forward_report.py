import polars as pl

from src.walk_forward.walk_forward_report import write_walk_forward_report


def test_walk_forward_report(tmp_path):
    anchored = pl.DataFrame({
        "name": ["test"], "test_profit_factor": [2.0], "test_average_r": [0.5],
        "test_return_percent": [2.0],
        "test_positive_flag": [True], "test_max_drawdown_percent": [1.0],
        "test_worst_trade_r": [-1.0], "profit_factor_decay_percent": [0.0],
        "average_r_decay_percent": [0.0], "low_train_sample_warning": [False],
        "low_test_sample_warning": [False],
    })
    path = write_walk_forward_report(
        tmp_path, {"strategy_name": "s", "market": "USDJPY", "weekend_policy_name": "p",
                   "baseline_run_path": "run"},
        {"walk_forward_score": 90, "verdict": "STRONG_WALK_FORWARD"}, anchored,
        pl.DataFrame({"verdict": ["STRONG"]}), {"rolling": anchored},
    )
    assert "Executive Summary" in path.read_text()
    assert "Rolling Window Summary" in path.read_text()
