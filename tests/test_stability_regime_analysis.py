import polars as pl

from src.stability.regime_analysis import join_trade_regimes, regime_analysis


def test_regime_join_and_analysis(stability_trades):
    labels = pl.DataFrame({
        "date": [value.date() for value in stability_trades["entry_timestamp_utc"]],
        "volatility_regime": ["low", "low", "high", "high"],
        "trend_regime": ["range", "range", "strong_downtrend", "strong_downtrend"],
        "price_location_regime": ["middle_range"] * 4,
    })
    assert join_trade_regimes(stability_trades, labels)["volatility_regime"].null_count() == 0
    results = regime_analysis(stability_trades, labels, 10_000)
    assert results["regime_performance.csv"].height >= 5
    volatility = results["volatility_regime_performance.csv"]
    assert round(volatility["return_contribution"].sum(), 4) == 100
