from statistics import median


def calculate_robustness_score(rows: list[dict], one_factor: list[dict], paired: list[dict],
                               neighbourhood: dict) -> dict:
    successful = [row for row in rows if row["run_status"] == "SUCCESS"]

    def percent(key):
        return sum(bool(row[key]) for row in rows) / len(rows) * 100 if rows else 0

    profitable, passed = percent("profitable_flag"), percent("pass_flag")

    def med(key):
        return median(row[key] for row in successful) if successful else 0

    median_pf, median_r, median_dd, median_trades = (
        med("profit_factor"), med("average_r"), med("max_drawdown_percent"), med("total_trades")
    )
    cliffs = sum(row["sensitivity_level"] == "CLIFF" for row in one_factor)
    baseline = next((row for row in successful if row["variant_name"] == "baseline_original"), None)
    rank_percentile = 100
    if baseline and successful:
        rank = 1 + sum(row["total_return_percent"] > baseline["total_return_percent"] for row in successful)
        rank_percentile = rank / len(successful) * 100
    deductions = {
        "profitable_variant_percent_below_70": 20 if profitable < 70 else 0,
        "pass_variant_percent_below_60": 20 if passed < 60 else 0,
        "median_profit_factor_below_1_3": 15 if median_pf < 1.3 else 0,
        "median_average_r_not_positive": 10 if median_r <= 0 else 0,
        "median_drawdown_above_10": 10 if median_dd > 10 else 0,
        "otherwise_passing_tail_risk": 15 if any(row.get("worst_trade_r", 0) < -2.5 and row.get("total_return_percent", 0) > 0 for row in successful) else 0,
        "baseline_isolated": 15 if neighbourhood.get("baseline_isolated_flag") else 0,
        "one_factor_cliff": 10 if cliffs else 0,
        "paired_fail": 10 if any(row["verdict"] == "FAIL" for row in paired) else 0,
        "paired_warning": 5 if any(row["verdict"] == "WARNING" for row in paired) else 0,
        "low_median_trade_count": 5 if median_trades < 50 else 0,
        "baseline_top_decile_with_poor_median": 5 if rank_percentile <= 10 and median_pf < 1.3 else 0,
    }
    additions = {
        "profitable_variant_percent_at_least_80": 5 if profitable >= 80 else 0,
        "pass_variant_percent_at_least_70": 5 if passed >= 70 else 0,
        "median_profit_factor_at_least_1_5": 5 if median_pf >= 1.5 else 0,
        "no_cliff_sensitivity": 5 if not cliffs else 0,
        "all_local_neighbourhood_pass": 5 if neighbourhood.get("neighbourhood_pass_percent") == 100 else 0,
    }
    score = max(0, min(100, 100 - sum(deductions.values()) + sum(additions.values())))
    verdict = "STRONG_ROBUSTNESS" if score >= 85 else "PASS" if score >= 70 else "WARNING" if score >= 50 else "FAIL"
    return {
        "robustness_score": score, "verdict": verdict,
        "profitable_variant_percent": round(profitable, 4), "pass_variant_percent": round(passed, 4),
        "median_profit_factor": round(median_pf, 4), "median_average_r": round(median_r, 4),
        "median_drawdown_percent": round(median_dd, 4), "median_trade_count": round(median_trades, 4),
        "baseline_return_rank_percentile": round(rank_percentile, 4),
        "deductions": deductions, "additions": additions,
    }
