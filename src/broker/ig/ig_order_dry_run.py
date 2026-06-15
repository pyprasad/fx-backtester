from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from .models import DryRunOrder, InternalTick


def build_dry_run_order(*, signal: dict, market_rules, strategy: dict, latest_tick: InternalTick,
                        size: float, open_positions: int = 0) -> DryRunOrder:
    direction = str(signal.get("direction", "")).upper()
    entry = latest_tick.bid if direction == "SELL" else latest_tick.ask
    stop = float(signal.get("stop_price", 0))
    target = float(signal.get("target_price", 0))
    pip_size = float(strategy["strategy"]["pip_size"])
    risk_pips = abs(stop - entry) / pip_size
    limit_pips = abs(entry - target) / pip_size
    spread_ratio = latest_tick.spread_pips / risk_pips if risk_pips else float("inf")
    errors, warnings = [], []
    if direction != "SELL" or strategy["strategy"]["direction_mode"] != "short_only":
        errors.append("ONLY_SELL_ALLOWED")
    if direction == "SELL" and stop <= entry:
        errors.append("SHORT_STOP_MUST_BE_ABOVE_ENTRY")
    if direction == "SELL" and target >= entry:
        errors.append("SHORT_TARGET_MUST_BE_BELOW_ENTRY")
    minimum = float(strategy["broker_guardrails"]["min_initial_risk_pips"])
    if risk_pips < minimum:
        errors.append("INITIAL_RISK_BELOW_SELECTED_MINIMUM")
    broker_min = market_rules.min_stop_distance_pips
    if broker_min is not None and risk_pips < broker_min:
        errors.append("STOP_DISTANCE_BELOW_BROKER_MINIMUM")
    if market_rules.min_limit_distance_pips is not None and limit_pips < market_rules.min_limit_distance_pips:
        errors.append("LIMIT_DISTANCE_BELOW_BROKER_MINIMUM")
    local = latest_tick.timestamp_utc.astimezone(ZoneInfo(strategy["time_guards"]["broker_timezone"]))
    cutoff = datetime.strptime(strategy["time_guards"]["block_new_entries_after"], "%H:%M").time()
    if local.time() >= cutoff:
        errors.append("ENTRY_AFTER_UK_CUTOFF")
    if latest_tick.delayed:
        errors.append("DELAYED_PRICE")
    if not latest_tick.raw.get("normalization_price_scale_divisor"):
        errors.append("PRICE_SCALING_UNCONFIRMED")
    if market_rules.status.upper() != "TRADEABLE":
        errors.append("MARKET_NOT_TRADEABLE")
    max_entry_spread = strategy["spread_guardrails"].get("signal_spread_reject_above_pips")
    if max_entry_spread is not None and latest_tick.spread_pips > float(max_entry_spread):
        errors.append("ENTRY_SPREAD_ABOVE_STRATEGY_MAXIMUM")
    if open_positions >= int(strategy["execution"]["max_open_positions"]):
        errors.append("MAX_OPEN_POSITIONS_REACHED")
    warning_ratio = float(strategy["spread_guardrails"]["warn_spread_to_risk_ratio_above"])
    if spread_ratio > warning_ratio:
        warnings.append("SPREAD_TO_RISK_RATIO_ABOVE_WARNING")
    if size <= 0:
        errors.append("INVALID_SIZE")
    order = DryRunOrder(
        deal_reference=f"dry-{uuid4().hex[:25]}", epic=market_rules.epic, direction=direction, size=size,
        order_type="MARKET", level=None, stop_distance=round(risk_pips, 8), stop_level=stop,
        limit_distance=round(limit_pips, 8), limit_level=target, currency=market_rules.currency or "JPY",
        force_open=True, guaranteed_stop=False, time_in_force="FILL_OR_KILL",
        expiry=market_rules.expiry or "-", validation_errors=errors, validation_warnings=warnings,
    )
    order.validation_status = "READY_FOR_DEMO_DRY_RUN" if not errors else "NOT_READY"
    return order


def write_dry_run_report(path, order: DryRunOrder):
    import json
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "payload": order.payload(), "validation_status": order.validation_status,
        "validation_errors": order.validation_errors, "validation_warnings": order.validation_warnings,
        "order_sent": False,
    }, indent=2, default=str))
    return path
