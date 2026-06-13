import polars as pl

from src.stability.stability_score import calculate_stability_score


def test_stability_score_rewards_strong_result():
    yearly = pl.DataFrame({"net_profit": [100, 200], "positive_year_flag": [True, True], "total_trades": [40, 40]})
    monthly = pl.DataFrame({"positive_month_flag": [True, True, False]})
    score = calculate_stability_score(
        {"worst_trade_r": -2, "max_drawdown_percent": 2, "profit_factor": 2},
        yearly, monthly, pl.DataFrame(), {
            "top_3_month_profit_contribution_percent": 50,
            "top_10_trade_profit_contribution_percent": 40,
        }, pl.DataFrame(),
    )
    assert score["verdict"] == "STRONG_STABILITY"


def test_stability_score_penalises_tail_loss():
    yearly = pl.DataFrame({"net_profit": [-10], "positive_year_flag": [False], "total_trades": [10]})
    monthly = pl.DataFrame({"positive_month_flag": [False]})
    score = calculate_stability_score(
        {"worst_trade_r": -4, "max_drawdown_percent": 12, "profit_factor": 1},
        yearly, monthly, pl.DataFrame(), {
            "top_3_month_profit_contribution_percent": 80,
            "top_10_trade_profit_contribution_percent": 80,
        }, pl.DataFrame(),
    )
    assert score["stability_score"] < 70
