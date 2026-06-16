from decimal import Decimal, ROUND_DOWN


def active_account(accounts: dict, account_id: str) -> dict | None:
    return next((item for item in accounts.get("accounts", []) if item.get("accountId") == account_id), None)


def account_balance(account: dict) -> float:
    balance = account.get("balance", {})
    for key in ("balance", "available", "deposit"):
        value = balance.get(key)
        if value is not None:
            return float(value)
    raise ValueError("Unable to resolve active IG account balance")


def _precision_from_minimum(minimum: float | None) -> int:
    if minimum is None:
        return 2
    decimal = Decimal(str(minimum)).normalize()
    return max(0, -decimal.as_tuple().exponent)


def _round_down(value: float, precision: int) -> float:
    quantum = Decimal("1").scaleb(-precision)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_DOWN))


def dynamic_deal_size(*, balance: float, risk_percent: float, stop_distance_pips: float,
                      min_deal_size: float | None, instrument_unit: str) -> tuple[float, dict]:
    if stop_distance_pips <= 0:
        raise ValueError("Stop distance must be positive")
    risk_amount = balance * risk_percent / 100
    if instrument_unit and instrument_unit != "AMOUNT":
        raise ValueError(f"Unsupported IG sizing unit for dynamic sizing: {instrument_unit}")
    raw_deal_size = risk_amount / stop_distance_pips
    precision = _precision_from_minimum(min_deal_size)
    deal_size = _round_down(raw_deal_size, precision)
    if min_deal_size is not None and deal_size < min_deal_size:
        deal_size = float(min_deal_size)
    return deal_size, {
        "sizing_mode": "dynamic_risk_percent",
        "account_balance": balance,
        "risk_percent": risk_percent,
        "risk_amount": risk_amount,
        "stop_distance_pips": stop_distance_pips,
        "instrument_unit": instrument_unit,
        "min_deal_size": min_deal_size,
        "raw_deal_size": raw_deal_size,
        "deal_size": deal_size,
        "size_precision": precision,
    }
