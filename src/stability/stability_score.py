import polars as pl


def calculate_stability_score(
    summary: dict,
    yearly: pl.DataFrame,
    monthly: pl.DataFrame,
    rolling_6_month: pl.DataFrame,
    concentration: dict,
    regimes: pl.DataFrame,
) -> dict:
    score = 100
    negative_year = yearly.height > 0 and yearly["net_profit"].min() <= 0
    all_years_positive = yearly.height > 0 and not negative_year
    positive_month_percent = (
        monthly["positive_month_flag"].sum() / monthly.height * 100 if monthly.height else 0
    )
    year_profit_pct = (
        yearly["net_profit"].max() / yearly["net_profit"].sum() * 100
        if yearly.height and yearly["net_profit"].sum() > 0 else 0
    )
    deductions = {
        "negative_year": 15 if negative_year else 0,
        "positive_months_below_50_percent": 10 if positive_month_percent < 50 else 0,
        "top_3_month_concentration": 10 if concentration["top_3_month_profit_contribution_percent"] > 60 else 0,
        "top_10_trade_concentration": 10 if concentration["top_10_trade_profit_contribution_percent"] > 50 else 0,
        "worst_trade_below_minus_2_5r": 10 if summary["worst_trade_r"] < -2.5 else 0,
        "negative_rolling_6_month": 10 if rolling_6_month.height and rolling_6_month["return_percent"].min() < -5 else 0,
        "drawdown_above_10_percent": 10 if summary["max_drawdown_percent"] > 10 else 0,
        "negative_major_regime": 5 if regimes.height and regimes.filter(
            (pl.col("total_trades") >= 20) & (pl.col("average_r") < 0)
        ).height else 0,
        "year_below_30_trades": 5 if yearly.height and yearly["total_trades"].min() < 30 else 0,
        "single_year_profit_concentration": 5 if year_profit_pct > 60 else 0,
    }
    additions = {
        "all_years_positive": 5 if all_years_positive else 0,
        "profit_factor_at_least_1_8": 5 if summary["profit_factor"] >= 1.8 else 0,
        "drawdown_below_5_percent": 5 if summary["max_drawdown_percent"] < 5 else 0,
        "worst_trade_at_least_minus_2_5r": 5 if summary["worst_trade_r"] >= -2.5 else 0,
    }
    score = max(0, min(100, score - sum(deductions.values()) + sum(additions.values())))
    verdict = (
        "STRONG_STABILITY" if score >= 85 else "PASS" if score >= 70
        else "WARNING" if score >= 50 else "FAIL"
    )
    return {
        "stability_score": score,
        "verdict": verdict,
        "positive_years_percent": round(yearly["positive_year_flag"].sum() / yearly.height * 100, 4) if yearly.height else 0,
        "positive_months_percent": round(positive_month_percent, 4),
        "largest_year_profit_contribution_percent": round(year_profit_pct, 4),
        "deductions": deductions,
        "additions": additions,
    }
