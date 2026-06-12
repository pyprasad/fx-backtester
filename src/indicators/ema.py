import polars as pl


def ema(values: pl.Series, period: int) -> pl.Series:
    return values.ewm_mean(span=period, adjust=False, min_samples=period)
