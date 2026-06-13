from __future__ import annotations

from collections.abc import Callable

import polars as pl


def prepare_trades(trades: pl.DataFrame) -> pl.DataFrame:
    conversions = []
    for column in ("entry_timestamp_utc", "exit_timestamp_utc"):
        if column in trades.columns and trades.schema[column] == pl.String:
            conversions.append(pl.col(column).str.to_datetime(time_zone="UTC", strict=False))
    return trades.with_columns(conversions).sort("exit_timestamp_utc")


def _longest(values: list[float], winning: bool) -> int:
    best = current = 0
    for value in values:
        matched = value > 0 if winning else value <= 0
        current = current + 1 if matched else 0
        best = max(best, current)
    return best


def metrics_for_trades(trades: pl.DataFrame, starting_balance: float) -> dict:
    pnl = trades["net_pnl"].to_list() if trades.height else []
    rs = trades["pnl_r"].to_list() if trades.height else []
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value <= 0]
    equity = starting_balance
    peak = starting_balance
    max_drawdown = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    reasons = trades["exit_reason"].to_list() if "exit_reason" in trades.columns else []
    durations = trades["duration_days"].to_list() if "duration_days" in trades.columns else []
    return {
        "starting_balance": round(starting_balance, 2),
        "ending_balance": round(equity, 2),
        "net_profit": round(sum(pnl), 2),
        "return_percent": round(sum(pnl) / starting_balance * 100, 4) if starting_balance else 0,
        "total_trades": len(pnl),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / len(pnl) * 100, 4) if pnl else 0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else float("inf") if wins else 0,
        "average_r": round(sum(rs) / len(rs), 4) if rs else 0,
        "expectancy_r": round(sum(rs) / len(rs), 4) if rs else 0,
        "average_win_r": round(sum(r for r in rs if r > 0) / len(wins), 4) if wins else 0,
        "average_loss_r": round(sum(r for r in rs if r <= 0) / len(losses), 4) if losses else 0,
        "best_trade_r": round(max(rs), 4) if rs else 0,
        "worst_trade_r": round(min(rs), 4) if rs else 0,
        "max_drawdown_percent": round(max_drawdown / peak * 100, 4) if peak else 0,
        "max_drawdown_amount": round(max_drawdown, 2),
        "consecutive_losses_max": _longest(pnl, False),
        "consecutive_wins_max": _longest(pnl, True),
        "stop_loss_exit_count": reasons.count("stop_loss"),
        "take_profit_exit_count": reasons.count("take_profit"),
        "trailing_stop_exit_count": reasons.count("trailing_stop"),
        "weekend_force_close_exit_count": reasons.count("weekend_force_close"),
        "average_trade_duration_days": round(sum(durations) / len(durations), 4) if durations else 0,
    }


def period_verdict(metrics: dict) -> str:
    if metrics["return_percent"] < -5 or metrics["max_drawdown_percent"] > 10:
        return "FAIL"
    if (
        metrics["return_percent"] > 5
        and metrics["profit_factor"] >= 1.5
        and metrics["max_drawdown_percent"] < 5
    ):
        return "STRONG"
    if metrics["return_percent"] > 0 and metrics["profit_factor"] >= 1.2:
        return "PASS"
    return "WARNING"


def _period_rows(
    trades: pl.DataFrame,
    starting_balance: float,
    key_name: str,
    key_fn: Callable,
) -> list[dict]:
    trades = prepare_trades(trades)
    balance = starting_balance
    groups: dict[str, list[int]] = {}
    for index, timestamp in enumerate(trades["exit_timestamp_utc"]):
        groups.setdefault(key_fn(timestamp), []).append(index)
    rows = []
    for key, indexes in groups.items():
        subset = trades[indexes]
        metrics = metrics_for_trades(subset, balance)
        balance = metrics["ending_balance"]
        rows.append({key_name: key, **metrics, "positive_period_flag": metrics["net_profit"] > 0,
                     "verdict": period_verdict(metrics)})
    return rows


def yearly_analysis(trades: pl.DataFrame, starting_balance: float) -> pl.DataFrame:
    rows = _period_rows(trades, starting_balance, "year", lambda value: str(value.year))
    for row in rows:
        row["positive_year_flag"] = row.pop("positive_period_flag")
    return pl.DataFrame(rows)


def monthly_analysis(trades: pl.DataFrame, starting_balance: float) -> pl.DataFrame:
    rows = _period_rows(trades, starting_balance, "year_month", lambda value: value.strftime("%Y-%m"))
    for row in rows:
        row["year"] = int(row["year_month"][:4])
        row["month"] = int(row["year_month"][5:])
        row["positive_month_flag"] = row.pop("positive_period_flag")
    return pl.DataFrame(rows)


def quarterly_analysis(trades: pl.DataFrame, starting_balance: float) -> pl.DataFrame:
    def quarter(value):
        return f"{value.year}-Q{(value.month - 1) // 3 + 1}"

    rows = _period_rows(trades, starting_balance, "year_quarter", quarter)
    keep = (
        "year_quarter", "year", "quarter", "starting_balance", "ending_balance", "net_profit",
        "return_percent", "total_trades", "win_rate", "profit_factor", "average_r",
        "worst_trade_r", "max_drawdown_percent", "positive_quarter_flag", "verdict",
    )
    for row in rows:
        row["year"] = int(row["year_quarter"][:4])
        row["quarter"] = int(row["year_quarter"][-1])
        row["positive_quarter_flag"] = row.pop("positive_period_flag")
    return pl.DataFrame([{key: row[key] for key in keep} for row in rows])
