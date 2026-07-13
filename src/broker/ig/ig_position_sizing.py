from decimal import Decimal, ROUND_DOWN


def active_account(accounts: dict, account_id: str) -> dict | None:
    return next((item for item in accounts.get("accounts", []) if item.get("accountId") == account_id), None)


def account_balance(account: dict) -> float:
    balance = account.get("balance", {})
    for key in ("available", "balance", "deposit"):
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


def fixed_deal_size(*, deal_size: float, min_deal_size: float | None,
                    instrument_unit: str) -> tuple[float, dict]:
    if deal_size <= 0:
        raise ValueError("Fixed deal size must be positive")
    if instrument_unit and instrument_unit != "AMOUNT":
        raise ValueError(f"Unsupported IG sizing unit for fixed sizing: {instrument_unit}")
    precision = _precision_from_minimum(min_deal_size)
    rounded = _round_down(deal_size, precision)
    adjusted = rounded
    minimum_applied = False
    if min_deal_size is not None and adjusted < min_deal_size:
        adjusted = float(min_deal_size)
        minimum_applied = True
    return adjusted, {
        "sizing_mode": "fixed_deal_size",
        "requested_deal_size": deal_size,
        "instrument_unit": instrument_unit,
        "min_deal_size": min_deal_size,
        "deal_size": adjusted,
        "size_precision": precision,
        "minimum_applied": minimum_applied,
    }


def deal_size_from_contract(*, contract: dict, balance: float, stop_distance_pips: float,
                            min_deal_size: float | None, instrument_unit: str) -> tuple[float, dict]:
    sizing = contract.get("position_sizing") or {}
    mode = str(sizing.get("mode") or "dynamic_risk_percent").lower()
    if mode == "fixed_deal_size":
        return fixed_deal_size(
            deal_size=float(sizing["fixed_deal_size"]),
            min_deal_size=min_deal_size,
            instrument_unit=instrument_unit,
        )
    if mode != "dynamic_risk_percent":
        raise ValueError(f"Unsupported position sizing mode: {mode}")
    return dynamic_deal_size(
        balance=balance,
        risk_percent=float(contract["risk_management"]["risk_per_trade_percent"]),
        stop_distance_pips=stop_distance_pips,
        min_deal_size=min_deal_size,
        instrument_unit=instrument_unit,
    )
