import polars as pl

from .train_test_analysis import decay_percent


def window_verdict(test: dict) -> str:
    if test["net_profit"] <= 0 or test["worst_trade_r"] < -2.5 or test["max_drawdown_percent"] > 10:
        return "FAIL"
    if test["low_sample_warning"]:
        return "WARNING"
    if (
        test["profit_factor"] >= 1.5 and test["average_r"] > 0.2
        and test["worst_trade_r"] >= -2.5 and test["max_drawdown_percent"] < 5
    ):
        return "STRONG"
    if test["profit_factor"] >= 1.3 and test["average_r"] > 0:
        return "PASS"
    return "WARNING"


def analyze_windows(windows, runner) -> pl.DataFrame:
    rows = []
    for window in windows:
        train, test = runner.run_window(window)
        rows.append({
            "window_id": window.window_id, "name": window.name,
            "train_start": window.train_start, "train_end": window.train_end,
            "test_start": window.test_start, "test_end": window.test_end,
            "train_trades": train["total_trades"],
            "test_trades": test["total_trades"],
            **{f"train_{key}": train[key] for key in (
                "return_percent", "profit_factor", "average_r",
                "max_drawdown_percent", "worst_trade_r",
            )},
            **{f"test_{key}": test[key] for key in (
                "return_percent", "profit_factor", "average_r",
                "max_drawdown_percent", "worst_trade_r",
            )},
            "profit_factor_decay_percent": decay_percent(train["profit_factor"], test["profit_factor"]),
            "average_r_decay_percent": decay_percent(train["average_r"], test["average_r"]),
            "test_positive_flag": test["net_profit"] > 0,
            "low_train_sample_warning": train["low_sample_warning"],
            "low_test_sample_warning": test["low_sample_warning"],
            "verdict": window_verdict(test),
        })
    return pl.DataFrame(rows)
