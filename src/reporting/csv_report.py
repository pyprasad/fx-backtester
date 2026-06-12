import csv
from dataclasses import asdict
from pathlib import Path
from collections import defaultdict


def write_csv_reports(output: Path, trades: list, metrics: dict, rejections: list[dict]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "strategy_summary.csv", [metrics])
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
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
