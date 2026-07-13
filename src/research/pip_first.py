import ast
import csv
import html
import json
import re
import random
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


def _trade_value(trade: Any, key: str, default: Any = None) -> Any:
    if isinstance(trade, dict):
        return trade.get(key, default)
    return getattr(trade, key, default)


def _as_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_list(value: Any) -> list[dict]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    text = str(value)
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            price_fraction_pairs = re.findall(
                r"'price':\s*([-+]?\d+(?:\.\d+)?).*?'fraction':\s*([-+]?\d+(?:\.\d+)?)",
                text,
            )
            return [
                {"price": float(price), "fraction": float(fraction)}
                for price, fraction in price_fraction_pairs
            ]
    return parsed if isinstance(parsed, list) else []


def trade_pips(trade: Any, pip_size: float = 0.01) -> float:
    """Return weighted net pips per original stake, preserving partial exits."""
    entry = _as_float(_trade_value(trade, "entry_price"))
    exit_price = _as_float(_trade_value(trade, "exit_price"))
    direction = str(_trade_value(trade, "direction", "")).upper()
    sign = 1 if direction == "LONG" else -1
    partials = _parse_list(_trade_value(trade, "partial_exits", []))
    remaining = 1.0
    total = 0.0
    for partial in partials:
        fraction = _as_float(partial.get("fraction"), 0.0)
        if fraction <= 0:
            continue
        fraction = min(fraction, remaining)
        price = _as_float(partial.get("price"), exit_price)
        total += ((price - entry) * sign / pip_size) * fraction
        remaining -= fraction
    total += ((exit_price - entry) * sign / pip_size) * max(0.0, remaining)
    return total


def trade_risk_pips(trade: Any, pip_size: float = 0.01) -> float:
    configured = _trade_value(trade, "initial_risk_pips")
    if configured not in (None, ""):
        return _as_float(configured)
    return abs(_as_float(_trade_value(trade, "entry_price")) - _as_float(_trade_value(trade, "initial_stop"))) / pip_size


def trade_target_pips(trade: Any, pip_size: float = 0.01) -> float:
    return abs(_as_float(_trade_value(trade, "target_price")) - _as_float(_trade_value(trade, "entry_price"))) / pip_size


def trade_to_pip_row(trade: Any, pip_size: float = 0.01) -> dict:
    row = asdict(trade) if is_dataclass(trade) else dict(trade)
    pips = trade_pips(row, pip_size)
    risk_pips = trade_risk_pips(row, pip_size)
    target_pips = trade_target_pips(row, pip_size)
    row.update({
        "net_pips": round(pips, 4),
        "initial_risk_pips_pip_first": round(risk_pips, 4),
        "target_distance_pips": round(target_pips, 4),
        "pips_per_risk_pip": round(pips / risk_pips, 4) if risk_pips else 0,
    })
    return row


def _period_key(trade: Any, pattern: str) -> str:
    timestamp = _parse_datetime(_trade_value(trade, "exit_timestamp_utc"))
    return timestamp.strftime(pattern) if timestamp else "unknown"


def _equity_drawdown(values: list[float], starting_balance: float = 0.0) -> tuple[float, float]:
    equity = peak = starting_balance
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return equity, max_drawdown


def _longest(values: list[float], predicate) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if predicate(value) else 0
        best = max(best, current)
    return best


def calculate_pip_metrics(
    trades: list[Any],
    *,
    pip_size: float = 0.01,
    pip_values: list[float] | None = None,
    starting_balance: float = 0.0,
    label: str = "",
) -> dict:
    pip_values = pip_values or [0.1, 0.5, 1.0, 2.0]
    pips = [trade_pips(trade, pip_size) for trade in trades]
    wins = [value for value in pips if value > 0]
    losses = [value for value in pips if value <= 0]
    _, max_pip_drawdown = _equity_drawdown(pips, 0.0)
    months = len({_period_key(trade, "%Y-%m") for trade in trades if _period_key(trade, "%Y-%m") != "unknown"})
    risk_pips = [trade_risk_pips(trade, pip_size) for trade in trades]
    target_pips = [trade_target_pips(trade, pip_size) for trade in trades]
    metrics = {
        "label": label,
        "total_trades": len(trades),
        "net_pips": round(sum(pips), 2),
        "gross_winning_pips": round(sum(wins), 2),
        "gross_losing_pips": round(sum(losses), 2),
        "pip_profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else 0,
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0,
        "average_trade_pips": round(mean(pips), 4) if pips else 0,
        "median_trade_pips": round(median(pips), 4) if pips else 0,
        "average_win_pips": round(mean(wins), 4) if wins else 0,
        "average_loss_pips": round(mean(losses), 4) if losses else 0,
        "best_trade_pips": round(max(pips, default=0), 4),
        "worst_trade_pips": round(min(pips, default=0), 4),
        "max_pip_drawdown": round(max_pip_drawdown, 2),
        "return_over_pip_drawdown": round(sum(pips) / max_pip_drawdown, 4) if max_pip_drawdown else 0,
        "consecutive_pip_losses_max": _longest(pips, lambda value: value <= 0),
        "consecutive_pip_wins_max": _longest(pips, lambda value: value > 0),
        "trades_per_month": round(len(trades) / months, 4) if months else 0,
        "average_initial_risk_pips": round(mean(risk_pips), 4) if risk_pips else 0,
        "average_target_distance_pips": round(mean(target_pips), 4) if target_pips else 0,
        "short_net_pips": round(sum(value for trade, value in zip(trades, pips) if str(_trade_value(trade, "direction", "")).upper() == "SHORT"), 2),
        "long_net_pips": round(sum(value for trade, value in zip(trades, pips) if str(_trade_value(trade, "direction", "")).upper() == "LONG"), 2),
    }
    for pip_value in pip_values:
        values = [pip * pip_value for pip in pips]
        ending, drawdown = _equity_drawdown(values, starting_balance)
        suffix = str(pip_value).replace(".", "_")
        metrics[f"fixed_{suffix}_per_pip_net_pnl"] = round(sum(values), 2)
        metrics[f"fixed_{suffix}_per_pip_ending_balance"] = round(ending, 2)
        metrics[f"fixed_{suffix}_per_pip_max_drawdown"] = round(drawdown, 2)
    return metrics


def load_trade_log(path: str | Path) -> list[dict]:
    path = Path(path)
    with path.open() as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        if not rows:
            handle.write("")
            return
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _group_rows(rows: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key) or "unknown")].append(row)
    output = []
    for value, group in sorted(groups.items()):
        pips = [_as_float(row["net_pips"]) for row in group]
        wins = [item for item in pips if item > 0]
        losses = [item for item in pips if item <= 0]
        output.append({
            key: value,
            "trades": len(group),
            "net_pips": round(sum(pips), 2),
            "win_rate": round(len(wins) / len(group) * 100, 2) if group else 0,
            "average_trade_pips": round(mean(pips), 4) if pips else 0,
            "pip_profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else 0,
        })
    return output


def _period_rows(rows: list[dict], pattern: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        timestamp = _parse_datetime(row.get("exit_timestamp_utc"))
        groups[timestamp.strftime(pattern) if timestamp else "unknown"].append(row)
    return _group_rows([{**row, "period": period} for period, items in groups.items() for row in items], "period")


def _html_table(rows: list[dict]) -> str:
    if not rows:
        return "<p>No rows.</p>"
    headers = list(rows[0])
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(header, '')))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return f"<table border='1'><tr>{head}</tr>{body}</table>"


def _write_html(path: Path, summary_rows: list[dict], sections: list[tuple[str, list[dict]]]) -> None:
    body = ["<html><body><h1>Pip-First Intraday Report</h1>", "<h2>Run Ranking</h2>", _html_table(summary_rows)]
    for title, rows in sections:
        body.extend([f"<h2>{html.escape(title)}</h2>", _html_table(rows)])
    body.append("</body></html>")
    path.write_text("\n".join(body))


def write_pip_first_report(
    run_paths: list[str | Path],
    output_path: str | Path,
    *,
    pip_size: float = 0.01,
    pip_values: list[float] | None = None,
    starting_balance: float = 0.0,
) -> Path:
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    all_period_rows = []
    all_direction_rows = []
    all_session_rows = []
    for run_path in [Path(path).resolve() for path in run_paths]:
        trade_log = run_path / "trade_log.csv"
        label = run_path.name
        trades = load_trade_log(trade_log)
        pip_rows = [trade_to_pip_row(trade, pip_size) for trade in trades]
        metrics = calculate_pip_metrics(
            pip_rows,
            pip_size=pip_size,
            pip_values=pip_values,
            starting_balance=starting_balance,
            label=label,
        )
        metrics["run_path"] = str(run_path)
        summary_rows.append(metrics)
        run_output = output / label
        _write_csv(run_output / "pip_trade_log.csv", pip_rows)
        monthly = _period_rows(pip_rows, "%Y-%m")
        yearly = _period_rows(pip_rows, "%Y")
        direction = _group_rows(pip_rows, "direction")
        session = _group_rows(pip_rows, "session")
        _write_csv(run_output / "pip_monthly_performance.csv", monthly)
        _write_csv(run_output / "pip_yearly_performance.csv", yearly)
        _write_csv(run_output / "pip_direction_breakdown.csv", direction)
        _write_csv(run_output / "pip_session_breakdown.csv", session)
        all_period_rows.extend({**row, "label": label} for row in yearly)
        all_direction_rows.extend({**row, "label": label} for row in direction)
        all_session_rows.extend({**row, "label": label} for row in session)
    summary_rows.sort(
        key=lambda row: (
            _as_float(row.get("net_pips")),
            _as_float(row.get("return_over_pip_drawdown")),
            -_as_float(row.get("max_pip_drawdown")),
        ),
        reverse=True,
    )
    for index, row in enumerate(summary_rows, start=1):
        row["pip_rank"] = index
    _write_csv(output / "pip_first_summary.csv", summary_rows)
    _write_csv(output / "pip_first_yearly_comparison.csv", all_period_rows)
    _write_csv(output / "pip_first_direction_comparison.csv", all_direction_rows)
    _write_csv(output / "pip_first_session_comparison.csv", all_session_rows)
    _write_html(
        output / "pip_first_report.html",
        summary_rows,
        [
            ("Yearly Comparison", all_period_rows),
            ("Direction Comparison", all_direction_rows),
            ("Session Comparison", all_session_rows),
        ],
    )
    return output


def _stress_values(
    pips: list[float],
    *,
    method: str,
    iterations: int,
    seed: int,
    missed_trade_rate: float,
) -> list[float]:
    if not pips:
        return []
    rng = random.Random(seed)
    results = []
    sample_size = max(1, int(round(len(pips) * (1 - missed_trade_rate))))
    for _ in range(iterations):
        if method == "shuffle":
            sample = pips[:]
            rng.shuffle(sample)
            if missed_trade_rate:
                sample = sample[:sample_size]
        elif method == "bootstrap":
            sample = [rng.choice(pips) for _ in range(sample_size)]
        elif method == "miss_best":
            drop = len(pips) - sample_size
            sample = sorted(pips)[:len(pips) - drop] if drop > 0 else pips[:]
        elif method == "miss_worst":
            drop = len(pips) - sample_size
            sample = sorted(pips, reverse=True)[:len(pips) - drop] if drop > 0 else pips[:]
        else:
            raise ValueError(f"Unknown pip-first stress method: {method}")
        results.append(sum(sample))
    return results


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]


def _sequence_drawdowns(pips: list[float]) -> dict:
    _, historical = _equity_drawdown(pips, 0.0)
    worst_first = sorted(pips)
    _, worst_first_dd = _equity_drawdown(worst_first, 0.0)
    best_first = sorted(pips, reverse=True)
    _, best_first_dd = _equity_drawdown(best_first, 0.0)
    return {
        "historical_max_pip_drawdown": round(historical, 2),
        "worst_first_max_pip_drawdown": round(worst_first_dd, 2),
        "best_first_max_pip_drawdown": round(best_first_dd, 2),
    }


def write_pip_first_stress_report(
    run_paths: list[str | Path],
    output_path: str | Path,
    *,
    pip_size: float = 0.01,
    pip_values: list[float] | None = None,
    starting_balance: float = 0.0,
    iterations: int = 2000,
    seed: int = 42,
    slippage_pips: list[float] | None = None,
    missed_trade_rates: list[float] | None = None,
) -> Path:
    pip_values = pip_values or [0.5, 1.0, 2.0]
    slippage_pips = slippage_pips or [0.0, 0.2, 0.5, 1.0]
    missed_trade_rates = missed_trade_rates or [0.0, 0.05, 0.10, 0.20]
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for run_path in [Path(path).resolve() for path in run_paths]:
        label = run_path.name
        trades = load_trade_log(run_path / "trade_log.csv")
        base_pips = [trade_pips(trade, pip_size) for trade in trades]
        for slip in slippage_pips:
            slipped = [
                pip - (slip * (1 + (1 if _parse_list(_trade_value(trade, "partial_exits", [])) else 0.5)))
                for pip, trade in zip(base_pips, trades)
            ]
            seq = _sequence_drawdowns(slipped)
            for missed in missed_trade_rates:
                for method in ("shuffle", "bootstrap", "miss_best", "miss_worst"):
                    values = _stress_values(
                        slipped,
                        method=method,
                        iterations=iterations,
                        seed=seed,
                        missed_trade_rate=missed,
                    )
                    row = {
                        "label": label,
                        "method": method,
                        "iterations": iterations,
                        "seed": seed,
                        "trade_count": len(trades),
                        "slippage_pips_per_execution": slip,
                        "missed_trade_rate": missed,
                        "median_net_pips": round(_percentile(values, 50), 2),
                        "p05_net_pips": round(_percentile(values, 5), 2),
                        "p95_net_pips": round(_percentile(values, 95), 2),
                        "worst_net_pips": round(min(values, default=0), 2),
                        "best_net_pips": round(max(values, default=0), 2),
                        **seq,
                    }
                    for pip_value in pip_values:
                        suffix = str(pip_value).replace(".", "_")
                        row[f"p05_pnl_at_{suffix}_per_pip"] = round(row["p05_net_pips"] * pip_value, 2)
                        row[f"median_pnl_at_{suffix}_per_pip"] = round(row["median_net_pips"] * pip_value, 2)
                        row[f"historical_drawdown_at_{suffix}_per_pip"] = round(
                            row["historical_max_pip_drawdown"] * pip_value,
                            2,
                        )
                        row[f"ending_balance_p05_at_{suffix}_per_pip"] = round(
                            starting_balance + row["p05_net_pips"] * pip_value,
                            2,
                        )
                    rows.append(row)
    rows.sort(key=lambda row: (row["label"], row["slippage_pips_per_execution"], row["missed_trade_rate"], row["method"]))
    _write_csv(output / "pip_first_stress_summary.csv", rows)
    _write_html(output / "pip_first_stress_report.html", rows, [])
    return output
