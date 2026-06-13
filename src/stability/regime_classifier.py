import polars as pl


def classify_regimes(candles: pl.DataFrame, config: dict | None = None) -> pl.DataFrame:
    config = config or {}
    trend = config.get("trend_regimes", {})
    fast = trend.get("ema_fast", 50)
    slow = trend.get("ema_slow", 200)
    slope_days = trend.get("slope_lookback_days", 20)
    location_days = config.get("price_location_regimes", {}).get("lookback_days", 60)
    frame = candles.sort("timestamp").with_columns(
        pl.col("timestamp").dt.date().alias("date"),
        pl.max_horizontal(
            pl.col("mid_high") - pl.col("mid_low"),
            (pl.col("mid_high") - pl.col("mid_close").shift(1)).abs(),
            (pl.col("mid_low") - pl.col("mid_close").shift(1)).abs(),
        ).alias("true_range"),
    ).with_columns(
        pl.col("true_range").rolling_mean(window_size=14, min_samples=1).alias("atr_14"),
        pl.col("mid_close").ewm_mean(span=fast, adjust=False).alias("ema_50"),
        pl.col("mid_close").ewm_mean(span=slow, adjust=False).alias("ema_200"),
        pl.col("mid_high").rolling_max(window_size=location_days, min_samples=1).alias("rolling_60d_high"),
        pl.col("mid_low").rolling_min(window_size=location_days, min_samples=1).alias("rolling_60d_low"),
    ).with_columns(
        (pl.col("atr_14").rank("average") / pl.len() * 100).alias("atr_percentile"),
        (pl.col("ema_200") - pl.col("ema_200").shift(slope_days)).alias("ema_200_slope"),
    ).with_columns(
        pl.when(pl.col("atr_percentile") <= 33).then(pl.lit("low"))
        .when(pl.col("atr_percentile") <= 66).then(pl.lit("medium"))
        .otherwise(pl.lit("high")).alias("volatility_regime"),
        pl.when(
            (pl.col("mid_close") < pl.col("ema_200")) & (pl.col("ema_50") < pl.col("ema_200"))
            & (pl.col("ema_200_slope") < 0)
        ).then(pl.lit("strong_downtrend"))
        .when(
            (pl.col("mid_close") > pl.col("ema_200")) & (pl.col("ema_50") > pl.col("ema_200"))
            & (pl.col("ema_200_slope") > 0)
        ).then(pl.lit("strong_uptrend"))
        .when(
            (pl.col("mid_close") < pl.col("ema_200")) & (pl.col("ema_50") < pl.col("ema_200"))
        ).then(pl.lit("weak_downtrend"))
        .when(
            (pl.col("mid_close") > pl.col("ema_200")) & (pl.col("ema_50") > pl.col("ema_200"))
        ).then(pl.lit("weak_uptrend"))
        .otherwise(pl.lit("range")).alias("trend_regime"),
        pl.when(
            pl.col("mid_close") <= pl.col("rolling_60d_low")
            + (pl.col("rolling_60d_high") - pl.col("rolling_60d_low")) * 0.25
        ).then(pl.lit("near_60d_low"))
        .when(
            pl.col("mid_close") >= pl.col("rolling_60d_low")
            + (pl.col("rolling_60d_high") - pl.col("rolling_60d_low")) * 0.75
        ).then(pl.lit("near_60d_high"))
        .otherwise(pl.lit("middle_range")).alias("price_location_regime"),
    )
    return frame.select(
        "date", "mid_close", "atr_14", "atr_percentile", "volatility_regime", "ema_50",
        "ema_200", "ema_200_slope", "trend_regime", "rolling_60d_high", "rolling_60d_low",
        "price_location_regime",
    )
