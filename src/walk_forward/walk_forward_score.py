import polars as pl


def calculate_walk_forward_score(anchored: pl.DataFrame, rolling_details: pl.DataFrame, rolling_summary: pl.DataFrame) -> dict:
    score = 100
    all_tests = (
        pl.concat([anchored, rolling_details], how="diagonal_relaxed")
        if rolling_details.height else anchored
    )
    rolling_positive = (
        rolling_details["test_positive_flag"].sum() / rolling_details.height * 100
        if rolling_details.height else 0
    )
    pf_decay_majority = (
        all_tests.filter(pl.col("profit_factor_decay_percent") > 50).height > all_tests.height / 2
        if all_tests.height else False
    )
    r_decay_majority = (
        all_tests.filter(pl.col("average_r_decay_percent") > 60).height > all_tests.height / 2
        if all_tests.height else False
    )
    test_profits = all_tests["test_return_percent"].clip(lower_bound=0) if all_tests.height else pl.Series()
    concentration = (
        float(test_profits.max() / test_profits.sum() * 100) if test_profits.len() and test_profits.sum() > 0 else 0
    )
    deductions = {
        "negative_anchored_test": 20 if anchored.height and not anchored["test_positive_flag"].all() else 0,
        "rolling_positive_below_70_percent": 15 if rolling_positive < 70 else 0,
        "rolling_average_profit_factor_below_1_3": 10 if rolling_summary.height and rolling_summary["avg_test_profit_factor"].min() < 1.3 else 0,
        "test_worst_trade_below_minus_2_5r": 10 if all_tests.height and all_tests["test_worst_trade_r"].min() < -2.5 else 0,
        "test_drawdown_above_10_percent": 10 if all_tests.height and all_tests["test_max_drawdown_percent"].max() > 10 else 0,
        "profit_factor_decay": 10 if pf_decay_majority else 0,
        "average_r_decay": 10 if r_decay_majority else 0,
        "anchored_low_sample": 5 if anchored.height and anchored["low_test_sample_warning"].any() else 0,
        "rolling_low_sample": 5 if rolling_summary.height and rolling_summary["low_sample_warning"].any() else 0,
        "single_window_concentration": 5 if concentration > 50 else 0,
    }
    additions = {
        "all_anchored_tests_positive": 5 if anchored.height and anchored["test_positive_flag"].all() else 0,
        "all_rolling_definitions_pass": 5 if rolling_summary.height and rolling_summary["verdict"].is_in(["PASS", "STRONG"]).all() else 0,
        "worst_test_trade_at_least_minus_2_5r": 5 if all_tests.height and all_tests["test_worst_trade_r"].min() >= -2.5 else 0,
        "average_test_profit_factor_at_least_1_5": 5 if all_tests.height and all_tests["test_profit_factor"].mean() >= 1.5 else 0,
    }
    score = max(0, min(100, score - sum(deductions.values()) + sum(additions.values())))
    verdict = "STRONG_WALK_FORWARD" if score >= 85 else "PASS" if score >= 70 else "WARNING" if score >= 50 else "FAIL"
    return {
        "walk_forward_score": score, "verdict": verdict,
        "rolling_positive_test_window_percent": round(float(rolling_positive), 4),
        "largest_positive_test_window_contribution_percent": round(concentration, 4),
        "deductions": deductions, "additions": additions,
    }
