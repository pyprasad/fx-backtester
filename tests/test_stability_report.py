import polars as pl

from src.stability.stability_report import write_stability_report


def test_html_report_contains_key_sections(tmp_path):
    frame = pl.DataFrame({"net_profit": [1], "positive_year_flag": [True]})
    regimes = pl.DataFrame({"regime_name": ["low"], "net_profit": [1], "average_r": [1]})
    path = write_stability_report(
        tmp_path, "strategy", "USDJPY", "policy", {"profit_factor": 2},
        {"stability_score": 90, "verdict": "STRONG_STABILITY", "positive_months_percent": 60},
        frame, pl.DataFrame({"year_month": ["2022-01"]}), frame, {}, {"verdict": "PASS",
        "top_3_month_profit_contribution_percent": 50, "top_10_trade_profit_contribution_percent": 40},
        {name: pl.DataFrame() for name in ("top_profit_months.csv", "top_loss_months.csv",
        "top_winning_trades.csv", "top_losing_trades.csv")},
        {name: regimes for name in ("regime_performance.csv", "volatility_regime_performance.csv",
        "trend_regime_performance.csv", "price_location_regime_performance.csv")},
    )
    content = path.read_text()
    assert "Executive Summary" in content
    assert "walk-forward validation" in content
