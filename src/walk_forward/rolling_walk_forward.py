from statistics import median

import polars as pl

from .anchored_walk_forward import analyze_windows


def analyze_rolling(windows, runner) -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
    details = {}
    summaries = []
    for definition in sorted({window.name for window in windows}):
        frame = analyze_windows([window for window in windows if window.name == definition], runner)
        details[definition] = frame.with_columns(pl.lit(definition).alias("rolling_definition"))
        positive = int(frame["test_positive_flag"].sum())
        positive_percent = positive / frame.height * 100 if frame.height else 0
        avg_pf = float(frame["test_profit_factor"].mean()) if frame.height else 0
        worst = float(frame["test_worst_trade_r"].min()) if frame.height else 0
        low_sample = bool(frame["low_test_sample_warning"].any()) if frame.height else True
        if positive_percent >= 85 and avg_pf >= 1.5 and worst >= -2.5:
            verdict = "STRONG"
        elif positive_percent >= 70 and avg_pf >= 1.3 and worst >= -2.5:
            verdict = "PASS"
        elif positive_percent >= 60 or low_sample:
            verdict = "WARNING"
        else:
            verdict = "FAIL"
        summaries.append({
            "rolling_definition": definition, "total_windows": frame.height,
            "positive_test_windows": positive, "positive_test_window_percent": round(positive_percent, 4),
            "pass_windows": frame.filter(pl.col("verdict").is_in(["PASS", "STRONG"])).height,
            "warning_windows": frame.filter(pl.col("verdict") == "WARNING").height,
            "fail_windows": frame.filter(pl.col("verdict") == "FAIL").height,
            "avg_test_return_percent": round(float(frame["test_return_percent"].mean()), 4),
            "median_test_return_percent": round(median(frame["test_return_percent"].to_list()), 4),
            "avg_test_profit_factor": round(avg_pf, 4),
            "median_test_profit_factor": round(median(frame["test_profit_factor"].to_list()), 4),
            "avg_test_average_r": round(float(frame["test_average_r"].mean()), 4),
            "worst_test_trade_r": worst,
            "max_test_drawdown_percent": float(frame["test_max_drawdown_percent"].max()),
            "min_test_profit_factor": float(frame["test_profit_factor"].min()),
            "low_sample_warning": low_sample, "verdict": verdict,
        })
    return details, pl.DataFrame(summaries)
