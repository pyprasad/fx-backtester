from datetime import datetime, timedelta, timezone

import polars as pl

from src.stability.regime_classifier import classify_regimes


def test_regime_classifier_assigns_all_regime_types():
    dates = [datetime(2022, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(260)]
    closes = [100 + i * 0.1 for i in range(260)]
    candles = pl.DataFrame({
        "timestamp": dates, "mid_close": closes, "mid_high": [v + 0.2 for v in closes],
        "mid_low": [v - 0.2 for v in closes],
    })
    labels = classify_regimes(candles)
    assert labels["volatility_regime"].drop_nulls().is_in(["low", "medium", "high"]).all()
    assert labels[-1, "trend_regime"] == "strong_uptrend"
    assert labels[-1, "price_location_regime"] == "near_60d_high"


def test_mixed_ema_alignment_is_range():
    dates = [datetime(2022, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(260)]
    closes = [100 + i * 0.1 for i in range(220)] + [121.9 - i * 0.5 for i in range(40)]
    candles = pl.DataFrame({
        "timestamp": dates, "mid_close": closes, "mid_high": [v + 0.2 for v in closes],
        "mid_low": [v - 0.2 for v in closes],
    })
    labels = classify_regimes(candles)
    assert "range" in labels["trend_regime"].to_list()
