import polars as pl

from .atr import atr
from .ema import ema
from .rsi import rsi


def add_indicators(candles: pl.DataFrame, pip_size: float = 0.01) -> pl.DataFrame:
    atr_values = atr(candles["mid_high"], candles["mid_low"], candles["mid_close"], 14)
    return candles.with_columns(
        ema(candles["mid_close"], 20).alias("ema_20"),
        ema(candles["mid_close"], 50).alias("ema_50"),
        ema(candles["mid_close"], 200).alias("ema_200"),
        rsi(candles["mid_close"], 14).alias("rsi_14"),
        atr_values.alias("atr_14"),
        (atr_values / pip_size).alias("atr_14_pips"),
    )
