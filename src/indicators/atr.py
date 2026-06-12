import polars as pl


def atr(high: pl.Series, low: pl.Series, close: pl.Series, period: int = 14) -> pl.Series:
    previous = close.shift(1)
    true_range = pl.DataFrame(
        {"hl": high - low, "hc": (high - previous).abs(), "lc": (low - previous).abs()}
    ).select(pl.max_horizontal("hl", "hc", "lc").alias("true_range"))["true_range"]
    return true_range.ewm_mean(alpha=1 / period, adjust=False, min_samples=period)
