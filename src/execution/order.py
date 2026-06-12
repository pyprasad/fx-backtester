from dataclasses import dataclass


@dataclass
class Order:
    symbol: str
    direction: str
    size: float
