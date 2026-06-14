from datetime import timedelta
from uuid import uuid4

import polars as pl

from src.config.schemas import StrategyConfig
from src.risk.position_sizer import position_size
from src.risk.weekend_policy import WeekendPolicy
from src.strategies.signal import Signal

from .trade import Trade


def execute_signal(signal: Signal, ticks: pl.DataFrame, config: StrategyConfig, balance: float) -> Trade | None:
    future = ticks.filter(pl.col("timestamp_utc") > signal.timestamp_utc)
    if future.is_empty():
        return None
    first = future.row(0, named=True)
    slip = config.execution["default_slippage_points"] if config.execution.get("slippage_enabled") else 0
    is_long = signal.direction == "LONG"
    entry = first["ask"] + slip if is_long else first["bid"] - slip
    stop = signal.proposed_stop
    initial_risk = abs(entry - stop)
    if initial_risk <= 0:
        return None
    size, risk_amount = position_size(balance, config.risk["risk_per_trade_percent"], entry, stop)
    partial_cfg = config.exit["partial_take_profit"]
    be_cfg = config.exit["move_stop_to_breakeven"]
    final_r = config.exit["runner"]["final_target_r"]
    price_tolerance = config.forensics.get("stop_audit", {}).get("tolerance_price", 0.000001)
    weekend = WeekendPolicy(config.weekend_policy)
    target = entry + (initial_risk * final_r * (1 if is_long else -1))
    remaining, realized, partials = 1.0, 0.0, []
    stop_history = [{"timestamp": first["timestamp_utc"], "price": stop, "reason": "initial"}]
    trailing_history = []
    breakeven_timestamp = None
    weekend_events, weekend_reduced, weekend_tightened = [], False, False
    final_stop, reason, exit_row, exit_price = stop, "end_of_data", future.row(-1, named=True), None
    mfe = mae = 0.0
    last_friday_row = None
    deadline = signal.timestamp_utc + timedelta(days=config.max_trade_duration_days)
    for row in future.iter_rows(named=True):
        force_section = config.weekend_policy.get("force_close_on_friday", {})
        if (
            weekend.enabled and force_section.get("enabled") and last_friday_row is not None
            and row["timestamp_utc"].weekday() != 4
            and last_friday_row["timestamp_utc"].time().isoformat() < force_section["close_time_utc"]
        ):
            close_side = last_friday_row["bid"] if is_long else last_friday_row["ask"]
            reason = force_section.get("close_reason", "weekend_force_close")
            exit_row, exit_price = last_friday_row, close_side - slip if is_long else close_side + slip
            weekend_events.append(weekend.event(
                "TRADE_FORCE_CLOSED_FRIDAY", last_friday_row["timestamp_utc"],
                signal_id=signal.signal_id, direction=signal.direction, price=exit_price,
                percent=remaining * 100, reason=reason,
            ))
            weekend_events.append(weekend.event(
                "WEEKEND_CLOSE_USED_LAST_AVAILABLE_FRIDAY_TICK", last_friday_row["timestamp_utc"],
                signal_id=signal.signal_id, direction=signal.direction, price=exit_price,
                percent=remaining * 100, reason=reason,
                notes="No suitable tick at or after configured Friday close time.",
            ))
            break
        if row["timestamp_utc"].weekday() == 4:
            last_friday_row = row
        close_side = row["bid"] if is_long else row["ask"]
        move = (close_side - entry) * (1 if is_long else -1)
        mfe, mae = max(mfe, move), min(mae, move)
        if be_cfg["enabled"] and move >= initial_risk * be_cfg["after_r"]:
            candidate = max(final_stop, entry) if is_long else min(final_stop, entry)
            if candidate != final_stop:
                final_stop = candidate
                breakeven_timestamp = row["timestamp_utc"]
                stop_history.append({"timestamp": row["timestamp_utc"], "price": final_stop, "reason": "breakeven"})
        if partial_cfg["enabled"] and remaining == 1.0 and move >= initial_risk * partial_cfg["at_r"]:
            fraction = partial_cfg["close_percent"] / 100
            realized += move * size * fraction
            remaining -= fraction
            partials.append({"timestamp": row["timestamp_utc"], "price": close_side, "fraction": fraction})
        if config.exit["runner"]["enabled"] and remaining < 1.0:
            trail_distance = signal.indicator_snapshot.get(
                "atr", signal.indicator_snapshot.get("atr_14", initial_risk)
            ) * config.exit["runner"]["trailing_stop"]["atr_multiplier"]
            candidate = close_side - trail_distance if is_long else close_side + trail_distance
            candidate = max(final_stop, candidate) if is_long else min(final_stop, candidate)
            if candidate != final_stop:
                final_stop = candidate
                trailing_history.append({"timestamp": row["timestamp_utc"], "price": final_stop})
                stop_history.append({"timestamp": row["timestamp_utc"], "price": final_stop, "reason": "trailing"})
        stop_hit = (
            close_side <= final_stop + price_tolerance
            if is_long else close_side >= final_stop - price_tolerance
        )
        target_hit = (
            close_side >= target - price_tolerance
            if is_long else close_side <= target + price_tolerance
        )
        if stop_hit or target_hit or row["timestamp_utc"] >= deadline:
            reason = ("trailing_stop" if stop_hit and final_stop != stop else "stop_loss") if stop_hit else ("take_profit" if target_hit else "max_duration")
            exit_row, exit_price = row, close_side - slip if is_long else close_side + slip
            break
        open_r = move / initial_risk
        policy_trade = {"trade_id": None, "signal_id": signal.signal_id, "direction": signal.direction}
        force, policy_reason = weekend.should_force_close_trade(policy_trade, row["timestamp_utc"])
        losing, losing_reason = weekend.should_close_losing_trade(policy_trade, row["timestamp_utc"], open_r)
        threshold, threshold_reason = weekend.should_close_below_profit_threshold(policy_trade, row["timestamp_utc"], open_r)
        if force or losing or threshold:
            reason = policy_reason or losing_reason or threshold_reason
            event_type = (
                "TRADE_FORCE_CLOSED_FRIDAY" if force else
                ("TRADE_CLOSED_LOSING_FRIDAY" if losing else "TRADE_CLOSED_BELOW_PROFIT_THRESHOLD")
            )
            exit_row, exit_price = row, close_side - slip if is_long else close_side + slip
            weekend_events.append(weekend.event(
                event_type, row["timestamp_utc"], signal_id=signal.signal_id, direction=signal.direction,
                price=exit_price, open_r=open_r, percent=remaining * 100, reason=reason,
            ))
            break
        reduce, close_percent, reduce_reason = weekend.should_reduce_position(policy_trade, row["timestamp_utc"], open_r)
        if reduce and not weekend_reduced:
            fraction = min(remaining, close_percent / 100)
            contribution = move * size * fraction
            realized += contribution
            remaining -= fraction
            weekend_reduced = True
            partials.append({
                "timestamp": row["timestamp_utc"], "price": close_side, "fraction": fraction,
                "percent_closed": fraction * 100, "reason": reduce_reason,
                "pnl_r_contribution": contribution / risk_amount,
            })
            weekend_events.append(weekend.event(
                "TRADE_PARTIALLY_REDUCED_FRIDAY", row["timestamp_utc"], signal_id=signal.signal_id,
                direction=signal.direction, price=close_side, open_r=open_r,
                percent=fraction * 100, reason=reduce_reason,
            ))
        tighten, tighten_reason = weekend.should_tighten_stop(policy_trade, row["timestamp_utc"], open_r)
        if tighten and not weekend_tightened:
            candidate = max(final_stop, entry) if is_long else min(final_stop, entry)
            weekend_tightened = True
            if candidate != final_stop:
                old_stop, final_stop = final_stop, candidate
                stop_history.append({
                    "timestamp": row["timestamp_utc"], "old_stop": old_stop, "price": final_stop,
                    "new_stop": final_stop, "reason": tighten_reason,
                })
                weekend_events.append(weekend.event(
                    "TRADE_STOP_TIGHTENED_FRIDAY", row["timestamp_utc"], signal_id=signal.signal_id,
                    direction=signal.direction, open_r=open_r, old_stop=old_stop,
                    new_stop=final_stop, reason=tighten_reason,
                ))
    if exit_price is None:
        exit_price = exit_row["bid"] if is_long else exit_row["ask"]
    realized += (exit_price - entry) * (1 if is_long else -1) * size * remaining
    duration = (exit_row["timestamp_utc"] - first["timestamp_utc"]).total_seconds()
    trade = Trade(
        str(uuid4()), signal.signal_id, signal.symbol, signal.direction, first["timestamp_utc"],
        exit_row["timestamp_utc"], entry, exit_price, stop, final_stop, target, size, risk_amount,
        realized, realized, realized / risk_amount, mfe, mae, duration, duration / 3600,
        duration / 86400, reason, first["spread_pips"], exit_row["spread_pips"], partials,
        session=signal.session,
        signal_timestamp_utc=signal.timestamp_utc,
        initial_risk_price_distance=initial_risk,
        initial_risk_pips=initial_risk / 0.01,
        max_favourable_excursion_r=mfe / initial_risk,
        max_adverse_excursion_r=mae / initial_risk,
        held_over_weekend=weekend.is_held_over_weekend(first["timestamp_utc"], exit_row["timestamp_utc"]),
        stop_history=stop_history,
        target_history=[{"timestamp": first["timestamp_utc"], "price": target}],
        trailing_history=trailing_history,
        breakeven_moved=breakeven_timestamp is not None,
        breakeven_timestamp_utc=breakeven_timestamp,
        weekend_policy_events=weekend_events,
        notes=f"weekend_policy={weekend.policy_name}" if weekend.enabled else "",
    )
    for event in trade.weekend_policy_events:
        event["trade_id"] = trade.trade_id
    return trade
