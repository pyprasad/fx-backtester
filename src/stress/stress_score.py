def calculate_stress_score(distribution: dict, execution: list[dict], missed: list[dict],
                           tail: list[dict], sequence: list[dict]) -> dict:
    def find(rows, name):
        return next((row for row in rows if row["scenario_name"] == name), {})

    spread2 = find(execution, "spread_2.0_both")
    slip1 = find(execution, "slippage_1.0_both")
    miss_best = find(missed, "miss_best_trades_10pct")
    tail5 = find(tail, "one_extra_minus_5r")
    worst_first = find(sequence, "worst_trades_first")
    deductions = {
        "negative_p5_return": 20 if distribution["p5_return_percent"] < 0 else 0,
        "probability_of_loss_above_10": 15 if distribution["probability_of_loss_percent"] > 10 else 0,
        "p95_drawdown_above_10": 15 if distribution["p95_max_drawdown_percent"] > 10 else 0,
        "p99_drawdown_above_15": 20 if distribution["p99_max_drawdown_percent"] > 15 else 0,
        "probability_drawdown_above_15_above_5": 15 if distribution["probability_drawdown_above_15_percent"] > 5 else 0,
        "median_profit_factor_below_1_3": 10 if distribution["median_profit_factor"] < 1.3 else 0,
        "negative_execution_stress": 10 if any(row["total_return_percent"] < 0 for row in execution) else 0,
        "execution_tail_loss_below_minus_5r": 10 if any(row.get("worst_trade_r", 0) < -5 for row in execution) else 0,
        "spread_2x_pf_below_1_3": 10 if spread2.get("profit_factor", 99) < 1.3 else 0,
        "slippage_1pip_pf_below_1_3": 10 if slip1.get("profit_factor", 99) < 1.3 else 0,
        "miss_best_10pct_negative": 10 if miss_best.get("median_return_percent", 99) < 0 else 0,
        "extra_minus_5r_drawdown_above_15": 10 if tail5.get("p95_drawdown_percent", 0) > 15 else 0,
        "worst_first_drawdown_above_15": 5 if worst_first.get("max_drawdown_percent", 0) > 15 else 0,
    }
    additions = {
        "positive_p5_return": 5 if distribution["p5_return_percent"] > 0 else 0,
        "p95_drawdown_below_10": 5 if distribution["p95_max_drawdown_percent"] < 10 else 0,
        "probability_of_loss_below_5": 5 if distribution["probability_of_loss_percent"] < 5 else 0,
        "all_execution_profitable": 5 if execution and all(row["total_return_percent"] > 0 for row in execution) else 0,
    }
    execution_tail_warning = any(row.get("worst_trade_r", 0) < -5 for row in execution)
    score = max(0, min(100, 100 - sum(deductions.values()) + sum(additions.values())))
    if execution_tail_warning:
        score = min(score, 84)
    verdict = "STRONG_STRESS_RESILIENCE" if score >= 85 else "PASS" if score >= 70 else "WARNING" if score >= 50 else "FAIL"
    return {
        "stress_score": score, "verdict": verdict, "execution_tail_warning": execution_tail_warning,
        "deductions": deductions, "additions": additions,
    }
