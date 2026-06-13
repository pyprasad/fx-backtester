from src.stability.period_analysis import monthly_analysis, quarterly_analysis, yearly_analysis
from src.stability.rolling_analysis import rolling_analysis


def test_period_and_rolling_analysis(stability_trades):
    yearly = yearly_analysis(stability_trades, 10_000)
    monthly = monthly_analysis(stability_trades, 10_000)
    quarterly = quarterly_analysis(stability_trades, 10_000)
    assert yearly["year"].to_list() == ["2022", "2023"]
    assert yearly["net_profit"].to_list() == [60.0, 100.0]
    assert monthly.height == 4  # Months with no trades are intentionally omitted.
    assert quarterly["year_quarter"].to_list() == ["2022-Q1", "2023-Q2"]
    assert rolling_analysis(stability_trades, 10_000, 3, "rolling_3_month").height > 0


def test_all_winning_period_has_unlimited_profit_factor(stability_trades):
    winners = stability_trades.filter(stability_trades["net_pnl"] > 0)
    yearly = yearly_analysis(winners, 10_000)
    assert yearly["profit_factor"].is_infinite().all()
