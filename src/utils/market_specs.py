from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSpec:
    symbol: str = "USDJPY"
    pip_size: float = 0.01
    price_decimals: int = 3


USDJPY = MarketSpec()
