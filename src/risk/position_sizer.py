def position_size(balance: float, risk_percent: float, entry: float, stop: float) -> tuple[float, float]:
    """Return simplified price-unit exposure; exact GBP/JPY conversion is a future enhancement."""
    risk_amount = balance * risk_percent / 100
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("Stop must differ from entry")
    return risk_amount / distance, risk_amount


def fixed_stake_position_size(
    stake_per_pip: float, pip_size: float, entry: float, stop: float
) -> tuple[float, float]:
    """Return price-unit exposure and planned loss for a fixed monetary stake per pip."""
    if stake_per_pip <= 0 or pip_size <= 0:
        raise ValueError("Stake per pip and pip size must be greater than zero")
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("Stop must differ from entry")
    initial_risk_pips = distance / pip_size
    return stake_per_pip / pip_size, initial_risk_pips * stake_per_pip


def pnl_pips(entry: float, exit_price: float, direction: str, pip_size: float) -> float:
    if pip_size <= 0:
        raise ValueError("Pip size must be greater than zero")
    movement = entry - exit_price if direction.upper() == "SHORT" else exit_price - entry
    return movement / pip_size
