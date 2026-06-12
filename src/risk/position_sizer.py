def position_size(balance: float, risk_percent: float, entry: float, stop: float) -> tuple[float, float]:
    """Return simplified price-unit exposure; exact GBP/JPY conversion is a future enhancement."""
    risk_amount = balance * risk_percent / 100
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("Stop must differ from entry")
    return risk_amount / distance, risk_amount
