from typing import Any


def weighted_partial_r(entry: float, direction: str, risk_distance: float, partial_exits: list[dict], exit_price: float, remaining: float = 1.0) -> float:
    sign = 1 if direction == "LONG" else -1
    total = 0.0
    for item in partial_exits:
        fraction = float(item["fraction"])
        total += ((float(item["price"]) - entry) * sign / risk_distance) * fraction
        remaining -= fraction
    return total + ((exit_price - entry) * sign / risk_distance) * remaining


def audit_r_multiple(trade: dict[str, Any], partial_exits: list[dict] | None = None, tolerance: float = 0.0001) -> dict:
    distance = abs(trade["entry_price"] - trade["initial_stop"])
    sign = 1 if trade["direction"] == "LONG" else -1
    price_r = ((trade["exit_price"] - trade["entry_price"]) * sign / distance) if distance else None
    partials = partial_exits or []
    weighted_r = weighted_partial_r(
        trade["entry_price"], trade["direction"], distance, partials, trade["exit_price"]
    ) if distance else None
    reported = trade["pnl_r"]
    calculated = weighted_r if partials else (
        trade["net_pnl"] / trade["risk_amount"] if trade.get("risk_amount") else price_r
    )
    level = "FAIL" if reported < -5 else ("WARNING" if reported < -2.5 else "PASS")
    return {
        "trade_id": trade["trade_id"],
        "initial_risk_price_distance": distance,
        "initial_risk_pips": distance / 0.01,
        "expected_loss_at_stop_r": -1.0,
        "price_only_pnl_r": price_r,
        "weighted_partial_pnl_r": weighted_r,
        "calculated_pnl_r": calculated,
        "reported_pnl_r": reported,
        "r_difference": calculated - reported if calculated is not None else None,
        "r_matches": calculated is not None and abs(calculated - reported) <= tolerance,
        "loss_threshold_status": level,
        "partial_exit_r_mismatch": bool(partials and abs(weighted_r - reported) > tolerance),
    }
