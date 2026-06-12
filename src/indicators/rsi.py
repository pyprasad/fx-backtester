import polars as pl


def rsi(values: pl.Series, period: int = 14) -> pl.Series:
    delta = values.diff()
    gain = delta.clip(lower_bound=0).ewm_mean(alpha=1 / period, adjust=False, min_samples=period)
    loss = (-delta.clip(upper_bound=0)).ewm_mean(alpha=1 / period, adjust=False, min_samples=period)
    return 100 - (100 / (1 + gain / loss))
