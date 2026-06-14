import csv
import json
from dataclasses import asdict
from pathlib import Path
from collections import defaultdict

from src.broker_guardrails.funding_model import calculate_trade_funding
from src.broker_guardrails.guardrail_metrics import funding_summary


def write_csv_reports(output: Path, trades: list, metrics: dict, rejections: list[dict]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_strategy_summary(output, metrics)
    _write(output / "trade_log.csv", [asdict(t) for t in trades])
    _write(output / "signal_rejection_log.csv", rejections)
    balance = metrics["starting_balance"]
    curve = []
    for trade in trades:
        balance += trade.net_pnl
        curve.append({"timestamp": trade.exit_timestamp_utc, "balance": balance})
    _write(output / "equity_curve.csv", curve)
    _write(output / "monthly_performance.csv", _period_rows(trades, "%Y-%m"))
    _write(output / "yearly_performance.csv", _period_rows(trades, "%Y"))
    peak, balance, drawdowns = metrics["starting_balance"], metrics["starting_balance"], []
    for trade in trades:
        balance += trade.net_pnl
        peak = max(peak, balance)
        drawdowns.append({"timestamp": trade.exit_timestamp_utc, "balance": balance, "drawdown": peak - balance})
    _write(output / "drawdown_report.csv", drawdowns)
    _write(output / "long_short_breakdown.csv", _group_rows(trades, lambda t: t.direction, "direction"))
    _write(output / "session_breakdown.csv", _group_rows(trades, lambda t: t.session or "unknown", "session"))
    if metrics.get("position_sizing_mode") == "fixed_spread_bet_stake":
        fixed_keys = [
            "starting_balance", "ending_balance", "total_return_percent", "net_profit_gbp",
            "total_pips", "gross_profit_gbp", "gross_loss_gbp", "profit_factor", "total_trades",
            "max_drawdown_gbp", "max_drawdown_percent", "stake_per_pip_gbp",
            "estimated_loss_at_3pip_stop_gbp", "estimated_loss_at_5pip_stop_gbp",
            "estimated_loss_at_10pip_stop_gbp", "estimated_loss_at_20pip_stop_gbp",
        ]
        _write(output / "fixed_stake_summary.csv", [{key: metrics[key] for key in fixed_keys}])
        pips_keys = [
            "total_pips", "average_trade_pips", "average_win_pips", "average_loss_pips",
            "best_trade_pips", "worst_trade_pips",
        ]
        _write(output / "pips_summary.csv", [{key: metrics[key] for key in pips_keys}])


def write_strategy_summary(output: Path, metrics: dict) -> None:
    _write(output / "strategy_summary.csv", [metrics])
    (output / "strategy_summary.json").write_text(json.dumps(metrics, indent=2, default=str))


def write_weekend_policy_reports(output: Path, trades: list, rejections: list[dict], policy: dict) -> dict:
    events = [event for trade in trades for event in trade.weekend_policy_events]
    reason_map = {
        "REJECT_WEEKEND_POLICY_FRIDAY_CUTOFF": "SIGNAL_REJECTED_FRIDAY_CUTOFF",
        "REJECT_WEEKEND_POLICY_LATE_FRIDAY": "SIGNAL_REJECTED_LATE_FRIDAY",
        "REJECT_WEEKEND_POLICY_SUNDAY_OPEN": "SIGNAL_REJECTED_SUNDAY_OPEN",
    }
    for rejected in rejections:
        if rejected.get("reason") in reason_map:
            events.append({
                "event_id": "", "policy_name": policy.get("policy_name", ""), "timestamp_utc": rejected.get("timestamp"),
                "symbol": "USDJPY", "event_type": reason_map[rejected["reason"]], "trade_id": "",
                "signal_id": "", "direction": "", "price": "", "open_r_before_event": "",
                "position_percent_affected": "", "old_stop": "", "new_stop": "",
                "reason": rejected["reason"], "notes": "",
            })
    _write(output / "weekend_policy_events.csv", events)
    summary = {
        "policy_name": policy.get("policy_name", "baseline_allow_weekend"),
        "weekend_policy_enabled": policy.get("enabled", False),
        "friday_cutoff_signal_rejections": sum(e.get("event_type") in {"SIGNAL_REJECTED_FRIDAY_CUTOFF", "SIGNAL_REJECTED_LATE_FRIDAY"} for e in events),
        "sunday_open_signal_rejections": sum(e.get("event_type") == "SIGNAL_REJECTED_SUNDAY_OPEN" for e in events),
        "weekend_force_closes": sum(e.get("event_type") == "TRADE_FORCE_CLOSED_FRIDAY" for e in events),
        "weekend_partial_reductions": sum(e.get("event_type") == "TRADE_PARTIALLY_REDUCED_FRIDAY" for e in events),
        "weekend_stop_tightens": sum(e.get("event_type") == "TRADE_STOP_TIGHTENED_FRIDAY" for e in events),
        "weekend_held_trades": sum(t.held_over_weekend for t in trades),
        "weekend_held_losses": sum(t.held_over_weekend and t.pnl_r < 0 for t in trades),
        "worst_trade_r": min((t.pnl_r for t in trades), default=0),
        "trades_beyond_2_5r": sum(t.pnl_r < -2.5 for t in trades),
        "trades_beyond_5r": sum(t.pnl_r < -5 for t in trades),
    }
    _write(output / "weekend_policy_summary.csv", [summary])
    return summary


def write_funding_reports(output: Path, trades: list, metrics: dict, settings: dict) -> dict:
    daily_pips = float(settings["overnight_funding"]["default_daily_funding_pips"])
    adjusted, events = [], []
    for trade in trades:
        row, trade_events = calculate_trade_funding(trade, settings["overnight_funding"], daily_pips)
        adjusted.append(row)
        events.extend(trade_events)
    summary = funding_summary(adjusted, metrics, float(metrics["starting_balance"]))
    _write(output / "funding_adjusted_trade_log.csv", adjusted)
    _write(output / "funding_events.csv", events)
    _write(output / "funding_summary.csv", [summary])
    return summary


def _period_rows(trades: list, pattern: str) -> list[dict]:
    return _group_rows(trades, lambda t: t.exit_timestamp_utc.strftime(pattern), "period")


def _group_rows(trades: list, key_fn, key_name: str) -> list[dict]:
    groups = defaultdict(list)
    for trade in trades:
        groups[key_fn(trade)].append(trade)
    return [{key_name: key, "trades": len(group), "net_pnl": sum(t.net_pnl for t in group),
             "average_r": sum(t.pnl_r for t in group) / len(group),
             "win_rate": sum(t.net_pnl > 0 for t in group) / len(group) * 100}
            for key, group in sorted(groups.items())]


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        if not rows:
            handle.write("")
            return
        # Rejection and event logs can contain several valid row types with
        # different optional fields. Preserve first-seen column order while
        # ensuring later row types are represented.
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
