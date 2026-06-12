import polars as pl

from src.indicators.indicator_engine import add_indicators


def test_indicators_have_expected_length_and_warmup():
    values = [100 + i * 0.01 for i in range(220)]
    candles = pl.DataFrame({
        "mid_open": values, "mid_high": [v + 0.02 for v in values],
        "mid_low": [v - 0.02 for v in values], "mid_close": values,
    })
    result = add_indicators(candles)
    assert result.height == 220
    assert result["ema_200"].null_count() > 0
    assert result["ema_200"][-1] is not None
    assert result["atr_14"][-1] is not None
