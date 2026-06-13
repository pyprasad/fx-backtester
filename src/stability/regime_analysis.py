import polars as pl

from .period_analysis import metrics_for_trades, prepare_trades


def join_trade_regimes(trades: pl.DataFrame, labels: pl.DataFrame) -> pl.DataFrame:
    return prepare_trades(trades).with_columns(
        pl.col("entry_timestamp_utc").dt.date().alias("entry_date")
    ).join(labels, left_on="entry_date", right_on="date", how="left")


def analyze_regime(trades: pl.DataFrame, column: str, regime_type: str, starting_balance: float) -> pl.DataFrame:
    rows = []
    if column not in trades.columns:
        return pl.DataFrame()
    for name in trades[column].drop_nulls().unique().sort():
        subset = trades.filter(pl.col(column) == name)
        metrics = metrics_for_trades(subset, starting_balance)
        if metrics["total_trades"] < 20:
            verdict = "WARNING_LOW_SAMPLE"
        elif metrics["average_r"] < 0:
            verdict = "FAIL"
        elif metrics["profit_factor"] >= 1.5 and metrics["average_r"] > 0.25:
            verdict = "STRONG"
        elif metrics["profit_factor"] >= 1.2 and metrics["average_r"] > 0:
            verdict = "PASS"
        else:
            verdict = "WARNING"
        rows.append({
            "regime_type": regime_type, "regime_name": name, "total_trades": metrics["total_trades"],
            "net_profit": metrics["net_profit"], "return_contribution": metrics["return_percent"],
            **{key: metrics[key] for key in (
                "win_rate", "profit_factor", "average_r", "expectancy_r", "average_win_r",
                "average_loss_r", "best_trade_r", "worst_trade_r", "max_drawdown_percent",
                "stop_loss_exit_count", "take_profit_exit_count", "trailing_stop_exit_count",
                "weekend_force_close_exit_count",
            )},
            "verdict": verdict,
        })
    return pl.DataFrame(rows)


def regime_analysis(trades: pl.DataFrame, labels: pl.DataFrame, starting_balance: float) -> dict[str, pl.DataFrame]:
    joined = join_trade_regimes(trades, labels)
    frames = {
        "volatility_regime_performance.csv": analyze_regime(joined, "volatility_regime", "volatility", starting_balance),
        "trend_regime_performance.csv": analyze_regime(joined, "trend_regime", "trend", starting_balance),
        "price_location_regime_performance.csv": analyze_regime(joined, "price_location_regime", "price_location", starting_balance),
    }
    if "session" in joined.columns:
        frames["session_regime_performance.csv"] = analyze_regime(joined, "session", "session", starting_balance)
    non_empty = [frame for frame in frames.values() if frame.height]
    frames["regime_performance.csv"] = pl.concat(non_empty, how="diagonal") if non_empty else pl.DataFrame()
    total_profit = float(trades["net_pnl"].sum()) if trades.height else 0
    if total_profit:
        frames = {
            name: frame.with_columns(
                (pl.col("net_profit") / total_profit * 100).round(4).alias("return_contribution")
            ) if frame.height else frame
            for name, frame in frames.items()
        }
    return frames
