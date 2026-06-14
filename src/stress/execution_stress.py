import polars as pl


def _cost(trades: pl.DataFrame, pips: pl.Expr) -> pl.DataFrame:
    return trades.with_columns(
        (pl.col("pnl_r") - pips / pl.col("initial_risk_pips")).alias("pnl_r")
    )


def apply_slippage(trades: pl.DataFrame, slippage_pips: float, apply_to="both") -> pl.DataFrame:
    sides = 2 if apply_to == "both" else 1
    return _cost(trades, pl.lit(slippage_pips * sides))


def apply_spread_multiplier(trades: pl.DataFrame, multiplier: float, apply_to="both") -> pl.DataFrame:
    entry = pl.col("spread_pips_at_entry") if apply_to in {"entry", "both"} else pl.lit(0)
    exit_ = pl.col("spread_pips_at_exit") if apply_to in {"exit", "both"} else pl.lit(0)
    return _cost(trades, (entry + exit_) * (multiplier - 1))


def apply_friday_close_slippage(trades: pl.DataFrame, slippage_pips: float) -> pl.DataFrame:
    return trades.with_columns(
        pl.when(pl.col("exit_reason") == "weekend_force_close")
        .then(pl.col("pnl_r") - slippage_pips / pl.col("initial_risk_pips"))
        .otherwise(pl.col("pnl_r")).alias("pnl_r")
    )


def apply_delayed_execution(trades: pl.DataFrame, entry_ticks=0, exit_ticks=0) -> pl.DataFrame:
    # R-based approximation until true delayed tick replay is implemented.
    return _cost(trades, pl.lit((entry_ticks + exit_ticks) * 0.1))
