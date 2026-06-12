from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    direction: str
    size: float
    entry_price: float
