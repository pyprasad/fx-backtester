import polars as pl

from src.stability.concentration_analysis import concentration_analysis


def test_concentration_and_non_positive_profit(stability_trades):
    summary, frames = concentration_analysis(stability_trades)
    assert summary["top_3_month_profit_contribution_percent"] > 0
    assert frames["top_winning_trades.csv"].height == 4
    zero = stability_trades.with_columns(pl.lit(0.0).alias("net_pnl"))
    assert concentration_analysis(zero)[0]["top_10_trade_profit_contribution_percent"] == 0
