import polars as pl

from .atr import atr
from .ema import ema
from .rsi import rsi


def add_indicators(
    candles: pl.DataFrame, pip_size: float = 0.01, parameters: dict | None = None
) -> pl.DataFrame:
    parameters = parameters or {}
    ema_fast = int(parameters.get("ema_fast", 20))
    ema_mid = int(parameters.get("ema_mid", 50))
    ema_slow = int(parameters.get("ema_slow", 200))
    rsi_period = int(parameters.get("rsi_period", 14))
    atr_period = int(parameters.get("atr_period", 14))
    atr_values = atr(candles["mid_high"], candles["mid_low"], candles["mid_close"], atr_period)
    result = candles.with_columns(
        ema(candles["mid_close"], ema_fast).alias("ema_fast"),
        ema(candles["mid_close"], ema_mid).alias("ema_mid"),
        ema(candles["mid_close"], ema_slow).alias("ema_slow"),
        rsi(candles["mid_close"], rsi_period).alias("rsi"),
        atr_values.alias("atr"),
        (atr_values / pip_size).alias("atr_pips"),
    )
    # Preserve the established baseline column names for existing reports and integrations.
    return result.with_columns(
        pl.col("ema_fast").alias(f"ema_{ema_fast}"),
        pl.col("ema_mid").alias(f"ema_{ema_mid}"),
        pl.col("ema_slow").alias(f"ema_{ema_slow}"),
        pl.col("rsi").alias(f"rsi_{rsi_period}"),
        pl.col("atr").alias(f"atr_{atr_period}"),
        pl.col("atr_pips").alias(f"atr_{atr_period}_pips"),
    )
