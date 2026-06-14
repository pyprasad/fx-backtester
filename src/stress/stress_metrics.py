import numpy as np


def distribution_metrics(paths: list[dict], baseline: dict | None = None) -> dict:
    baseline = baseline or {}
    def values(key):
        return np.asarray([row[key] for row in paths], dtype=float)

    returns, drawdowns, factors = values("total_return_percent"), values("max_drawdown_percent"), values("profit_factor")

    def percentile(array, level):
        return round(float(np.percentile(array, level)), 4)

    return {
        "iterations": len(paths), "median_return_percent": percentile(returns, 50),
        "mean_return_percent": round(float(returns.mean()), 4), "p5_return_percent": percentile(returns, 5),
        "p1_return_percent": percentile(returns, 1), "p95_return_percent": percentile(returns, 95),
        "median_max_drawdown_percent": percentile(drawdowns, 50),
        "p95_max_drawdown_percent": percentile(drawdowns, 95),
        "p99_max_drawdown_percent": percentile(drawdowns, 99),
        "median_profit_factor": percentile(factors, 50), "p5_profit_factor": percentile(factors, 5),
        "probability_of_loss_percent": round(float((returns < 0).mean() * 100), 4),
        "probability_drawdown_above_10_percent": round(float((drawdowns > 10).mean() * 100), 4),
        "probability_drawdown_above_15_percent": round(float((drawdowns > 15).mean() * 100), 4),
        "probability_ruin_percent": round(sum(row["ruin_flag"] for row in paths) / len(paths) * 100, 4),
        "worst_path_return_percent": round(float(returns.min()), 4),
        "worst_path_drawdown_percent": round(float(drawdowns.max()), 4),
        "best_path_return_percent": round(float(returns.max()), 4),
        "baseline_return_percent": baseline.get("total_return_percent", 0),
        "baseline_drawdown_percent": baseline.get("max_drawdown_percent", 0),
    }
