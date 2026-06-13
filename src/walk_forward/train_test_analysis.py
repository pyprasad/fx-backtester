from statistics import median

import polars as pl

from src.stability.period_analysis import metrics_for_trades, prepare_trades


def filter_trades(trades: pl.DataFrame, start, end) -> pl.DataFrame:
    return prepare_trades(trades).filter(
        (pl.col("entry_timestamp_utc") >= start) & (pl.col("entry_timestamp_utc") <= end)
    )


def calculate_period_metrics(
    trades: pl.DataFrame, period_start, period_end, starting_balance: float, minimum_trades: int
) -> dict:
    trades = prepare_trades(trades)
    base = metrics_for_trades(trades, starting_balance)
    pnl = trades["net_pnl"].to_list() if trades.height else []
    durations = trades["duration_days"].to_list() if "duration_days" in trades.columns else []
    entry_spreads = trades["spread_pips_at_entry"].to_list() if "spread_pips_at_entry" in trades.columns else []
    exit_spreads = trades["spread_pips_at_exit"].to_list() if "spread_pips_at_exit" in trades.columns else []
    return {
        "period_start": period_start, "period_end": period_end,
        **base,
        "gross_profit": round(sum(value for value in pnl if value > 0), 2),
        "gross_loss": round(sum(value for value in pnl if value <= 0), 2),
        "median_trade_duration_days": round(median(durations), 4) if durations else 0,
        "average_spread_pips_at_entry": round(sum(entry_spreads) / len(entry_spreads), 4) if entry_spreads else 0,
        "average_spread_pips_at_exit": round(sum(exit_spreads) / len(exit_spreads), 4) if exit_spreads else 0,
        "low_sample_warning": trades.height < minimum_trades,
        "return_calculation_method": "period_pnl_divided_by_fixed_starting_balance",
        "drawdown_calculation_method": "reconstructed_from_trade_exit_order",
    }


def decay_percent(train_value: float, test_value: float) -> float:
    if train_value <= 0:
        return 0
    return round((train_value - test_value) / train_value * 100, 4)
