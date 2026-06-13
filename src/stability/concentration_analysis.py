import polars as pl

from .period_analysis import prepare_trades


def concentration_analysis(trades: pl.DataFrame) -> tuple[dict, dict[str, pl.DataFrame]]:
    trades = prepare_trades(trades).with_columns(
        pl.col("exit_timestamp_utc").dt.strftime("%Y-%m").alias("year_month")
    )
    months = trades.group_by("year_month").agg(pl.col("net_pnl").sum()).sort("net_pnl", descending=True)
    winners = trades.sort("net_pnl", descending=True)
    losers = trades.sort("net_pnl")
    total = float(trades["net_pnl"].sum())

    def contribution(value: float) -> float:
        return round(value / total * 100, 4) if total > 0 else 0

    best_month = float(months["net_pnl"].max()) if months.height else 0
    worst_month = float(months["net_pnl"].min()) if months.height else 0
    top3 = float(months.head(3)["net_pnl"].sum()) if months.height else 0
    top5 = float(months.head(5)["net_pnl"].sum()) if months.height else 0
    top10_trades = float(winners.head(10)["net_pnl"].sum()) if winners.height else 0
    top5_trades = float(winners.head(5)["net_pnl"].sum()) if winners.height else 0
    top3_pct = contribution(top3)
    top10_pct = contribution(top10_trades)
    verdict = "PASS" if top3_pct <= 60 and top10_pct <= 50 else "WARNING" if top3_pct <= 75 else "FAIL"
    summary = {
        "total_net_profit": round(total, 2),
        "best_month_profit": round(best_month, 2),
        "best_month_profit_contribution_percent": contribution(best_month),
        "top_3_month_profit": round(top3, 2),
        "top_3_month_profit_contribution_percent": top3_pct,
        "top_5_month_profit_contribution_percent": contribution(top5),
        "top_10_trade_profit": round(top10_trades, 2),
        "top_10_trade_profit_contribution_percent": top10_pct,
        "top_5_trade_profit_contribution_percent": contribution(top5_trades),
        "worst_month_loss": round(worst_month, 2),
        "worst_month_loss_percent_of_total_profit": contribution(abs(worst_month)),
        "worst_trade_r": round(float(trades["pnl_r"].min()), 4) if trades.height else 0,
        "best_trade_r": round(float(trades["pnl_r"].max()), 4) if trades.height else 0,
        "verdict": verdict,
    }
    columns = [column for column in (
        "trade_id", "entry_timestamp_utc", "exit_timestamp_utc", "net_pnl", "pnl_r", "exit_reason"
    ) if column in trades.columns]
    return summary, {
        "top_profit_months.csv": months.head(10),
        "top_loss_months.csv": months.sort("net_pnl").head(10),
        "top_winning_trades.csv": winners.select(columns).head(10),
        "top_losing_trades.csv": losers.select(columns).head(10),
    }
