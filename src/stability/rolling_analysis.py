import polars as pl

from .period_analysis import metrics_for_trades, prepare_trades


def _add_months(value, months: int):
    month_index = value.year * 12 + value.month - 1 + months
    return value.replace(year=month_index // 12, month=month_index % 12 + 1)


def rolling_analysis(trades: pl.DataFrame, starting_balance: float, months: int, name: str) -> pl.DataFrame:
    trades = prepare_trades(trades)
    if not trades.height:
        return pl.DataFrame()
    first = trades["exit_timestamp_utc"].min().replace(day=1)
    last = trades["exit_timestamp_utc"].max().replace(day=1)
    month_starts = pl.datetime_range(first, last, "1mo", eager=True).to_list()
    rows = []
    for index in range(len(month_starts) - months + 1):
        start = month_starts[index]
        end = _add_months(start, months)
        subset = trades.filter(
            (pl.col("exit_timestamp_utc") >= start) & (pl.col("exit_timestamp_utc") < end)
        )
        metrics = metrics_for_trades(subset, starting_balance)
        if metrics["max_drawdown_percent"] > 10 or metrics["return_percent"] < -7.5:
            verdict = "FAIL"
        elif metrics["return_percent"] > 0 and metrics["profit_factor"] >= 1.2:
            verdict = "PASS"
        else:
            verdict = "WARNING"
        rows.append({
            "window_name": name, "start_date": start.date(), "end_date": end.date(),
            **{key: metrics[key] for key in (
                "total_trades", "net_profit", "return_percent", "profit_factor", "average_r",
                "win_rate", "worst_trade_r", "max_drawdown_percent",
            )},
            "positive_window_flag": metrics["net_profit"] > 0, "verdict": verdict,
        })
    return pl.DataFrame(rows)
