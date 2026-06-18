import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from statistics import mean


@dataclass(frozen=True)
class StrategyRun:
    label: str
    path: Path


@dataclass(frozen=True)
class GroupTrade:
    strategy: str
    trade_id: str
    symbol: str
    direction: str
    entry_timestamp_utc: datetime
    exit_timestamp_utc: datetime
    net_pnl: float
    pnl_r: float
    session: str
    exit_reason: str
    signal_timestamp_utc: datetime | None = None


def parse_strategy_run(value: str) -> StrategyRun:
    if "=" not in value:
        raise ValueError("Strategy runs must use LABEL=RUN_PATH")
    label, path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError("Strategy run label cannot be empty")
    return StrategyRun(label=label, path=Path(path).resolve())


class StrategyGroupResearchRunner:
    def __init__(self, strategy_runs: list[StrategyRun], output_path: str | Path, starting_balance: float = 10000):
        if len(strategy_runs) < 2:
            raise ValueError("At least two strategy runs are required for grouped research")
        self.strategy_runs = strategy_runs
        self.output_path = Path(output_path).resolve()
        self.starting_balance = float(starting_balance)

    def run(self) -> Path:
        trades = [trade for run in self.strategy_runs for trade in _load_trades(run)]
        self.output_path.mkdir(parents=True, exist_ok=True)
        if not trades:
            raise ValueError("No trades found in supplied strategy runs")

        strategy_rows = _strategy_metrics(trades)
        portfolio_summary = _portfolio_summary(trades, self.starting_balance)
        overlap_rows = _overlap_matrix(trades)
        duplicate_rows = _duplicate_entry_matrix(trades)
        deployment_rows = _deployment_risk_rows(strategy_rows, overlap_rows, duplicate_rows)
        session_rows = _session_matrix(trades)
        monthly_rows = _monthly_strategy_matrix(trades)
        exposure_rows = _exposure_events(trades)
        conflict_rows = _conflict_events(trades)

        _write_csv(self.output_path / "strategy_group_summary.csv", [portfolio_summary])
        _write_csv(self.output_path / "strategy_attribution.csv", strategy_rows)
        _write_csv(self.output_path / "strategy_overlap_matrix.csv", overlap_rows)
        _write_csv(self.output_path / "duplicate_entry_matrix.csv", duplicate_rows)
        _write_csv(self.output_path / "deployment_risk_summary.csv", deployment_rows)
        _write_csv(self.output_path / "strategy_session_matrix.csv", session_rows)
        _write_csv(self.output_path / "monthly_strategy_matrix.csv", monthly_rows)
        _write_csv(self.output_path / "portfolio_exposure_events.csv", exposure_rows)
        _write_csv(self.output_path / "overlap_loss_conflicts.csv", conflict_rows)
        _write_json(self.output_path / "strategy_group_summary.json", {
            "portfolio_summary": portfolio_summary,
            "strategy_attribution": strategy_rows,
            "overlap_matrix": overlap_rows,
            "duplicate_entry_matrix": duplicate_rows,
            "deployment_risk_summary": deployment_rows,
            "session_matrix": session_rows,
            "monthly_strategy_matrix": monthly_rows,
            "overlap_loss_conflicts": conflict_rows[:250],
        })
        _write_html(
            self.output_path / "strategy_group_report.html",
            portfolio_summary,
            strategy_rows,
            overlap_rows,
            duplicate_rows,
            deployment_rows,
            session_rows,
            monthly_rows,
            conflict_rows,
        )
        return self.output_path


def _load_trades(run: StrategyRun) -> list[GroupTrade]:
    trade_log = run.path / "trade_log.csv"
    if not trade_log.exists():
        raise FileNotFoundError(f"Missing trade log for {run.label}: {trade_log}")
    with trade_log.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    trades = []
    for index, row in enumerate(rows, start=1):
        entry = _parse_datetime(row.get("entry_timestamp_utc"))
        exit_ = _parse_datetime(row.get("exit_timestamp_utc"))
        if entry is None or exit_ is None:
            continue
        trades.append(GroupTrade(
            strategy=run.label,
            trade_id=row.get("trade_id") or f"{run.label}-{index}",
            symbol=row.get("symbol") or "",
            direction=row.get("direction") or "",
            entry_timestamp_utc=entry,
            exit_timestamp_utc=exit_,
            net_pnl=_float(row.get("net_pnl")),
            pnl_r=_float(row.get("pnl_r")),
            session=row.get("session") or "unknown",
            exit_reason=row.get("exit_reason") or "unknown",
            signal_timestamp_utc=_parse_datetime(row.get("signal_timestamp_utc")),
        ))
    return trades


def _strategy_metrics(trades: list[GroupTrade]) -> list[dict]:
    rows = []
    for strategy in sorted({trade.strategy for trade in trades}):
        group = [trade for trade in trades if trade.strategy == strategy]
        rows.append({"strategy": strategy, **_metrics(group)})
    return rows


def _portfolio_summary(trades: list[GroupTrade], starting_balance: float) -> dict:
    ordered = sorted(trades, key=lambda trade: trade.exit_timestamp_utc)
    equity = peak = starting_balance
    max_drawdown = 0.0
    for trade in ordered:
        equity += trade.net_pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    metrics = _metrics(ordered)
    active = _active_counts(ordered)
    return {
        "starting_balance": round(starting_balance, 2),
        "ending_balance": round(equity, 2),
        "total_return_percent": round((equity / starting_balance - 1) * 100, 4) if starting_balance else 0,
        "net_profit": round(sum(trade.net_pnl for trade in ordered), 2),
        "total_trades": len(ordered),
        "strategy_count": len({trade.strategy for trade in ordered}),
        "symbol_count": len({trade.symbol for trade in ordered}),
        "win_rate": metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "average_r": metrics["average_r"],
        "worst_trade_r": metrics["worst_trade_r"],
        "best_trade_r": metrics["best_trade_r"],
        "max_drawdown_percent": round(max_drawdown / peak * 100, 4) if peak else 0,
        "max_concurrent_trades": max(active, default=0),
        "trades_opened_while_other_trade_active": _trades_opened_during_other_trade(ordered),
    }


def _metrics(trades: list[GroupTrade]) -> dict:
    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl <= 0]
    gross_profit = sum(trade.net_pnl for trade in wins)
    gross_loss = sum(trade.net_pnl for trade in losses)
    return {
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 4) if trades else 0,
        "net_profit": round(sum(trade.net_pnl for trade in trades), 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / abs(gross_loss), 4) if gross_loss else 0,
        "average_r": round(mean([trade.pnl_r for trade in trades]), 4) if trades else 0,
        "average_win_r": round(mean([trade.pnl_r for trade in wins]), 4) if wins else 0,
        "average_loss_r": round(mean([trade.pnl_r for trade in losses]), 4) if losses else 0,
        "best_trade_r": round(max((trade.pnl_r for trade in trades), default=0), 4),
        "worst_trade_r": round(min((trade.pnl_r for trade in trades), default=0), 4),
    }


def _overlap_matrix(trades: list[GroupTrade]) -> list[dict]:
    strategies = sorted({trade.strategy for trade in trades})
    rows = []
    by_strategy = {strategy: [trade for trade in trades if trade.strategy == strategy] for strategy in strategies}
    for left in strategies:
        for right in strategies:
            pairs = []
            for left_trade in by_strategy[left]:
                for right_trade in by_strategy[right]:
                    if left == right and left_trade.trade_id >= right_trade.trade_id:
                        continue
                    if _overlaps(left_trade, right_trade):
                        pairs.append((left_trade, right_trade))
            losing_pairs = [
                (left_trade, right_trade)
                for left_trade, right_trade in pairs
                if left_trade.net_pnl <= 0 and right_trade.net_pnl <= 0
            ]
            rows.append({
                "strategy_a": left,
                "strategy_b": right,
                "temporal_overlap_pairs": len(pairs),
                "both_losing_overlap_pairs": len(losing_pairs),
                "both_losing_overlap_percent": round(len(losing_pairs) / len(pairs) * 100, 4) if pairs else 0,
                "same_day_entry_pairs": _same_day_pairs(by_strategy[left], by_strategy[right], skip_same=left == right),
                "same_signal_hour_pairs": _same_signal_hour_pairs(by_strategy[left], by_strategy[right], skip_same=left == right),
                "average_combined_overlap_r": round(mean([a.pnl_r + b.pnl_r for a, b in pairs]), 4) if pairs else 0,
                "worst_combined_overlap_r": round(min((a.pnl_r + b.pnl_r for a, b in pairs), default=0), 4),
            })
    return rows


def _duplicate_entry_matrix(trades: list[GroupTrade]) -> list[dict]:
    strategies = sorted({trade.strategy for trade in trades})
    by_strategy = {strategy: [trade for trade in trades if trade.strategy == strategy] for strategy in strategies}
    rows = []
    for left in strategies:
        for right in strategies:
            if left == right:
                rows.append({
                    "strategy_a": left,
                    "strategy_b": right,
                    "exact_signal_entry_duplicates": 0,
                    "duplicate_percent_of_strategy_a": 0,
                    "duplicate_percent_of_strategy_b": 0,
                    "same_direction_duplicates": 0,
                    "opposite_direction_duplicates": 0,
                    "both_losing_duplicates": 0,
                    "average_combined_duplicate_r": 0,
                    "worst_combined_duplicate_r": 0,
                })
                continue
            pairs = _duplicate_pairs(by_strategy[left], by_strategy[right])
            both_losing = [(a, b) for a, b in pairs if a.net_pnl <= 0 and b.net_pnl <= 0]
            rows.append({
                "strategy_a": left,
                "strategy_b": right,
                "exact_signal_entry_duplicates": len(pairs),
                "duplicate_percent_of_strategy_a": round(len(pairs) / len(by_strategy[left]) * 100, 4) if by_strategy[left] else 0,
                "duplicate_percent_of_strategy_b": round(len(pairs) / len(by_strategy[right]) * 100, 4) if by_strategy[right] else 0,
                "same_direction_duplicates": sum(a.direction == b.direction for a, b in pairs),
                "opposite_direction_duplicates": sum(a.direction != b.direction for a, b in pairs),
                "both_losing_duplicates": len(both_losing),
                "average_combined_duplicate_r": round(mean([a.pnl_r + b.pnl_r for a, b in pairs]), 4) if pairs else 0,
                "worst_combined_duplicate_r": round(min((a.pnl_r + b.pnl_r for a, b in pairs), default=0), 4),
            })
    return rows


def _deployment_risk_rows(strategy_rows: list[dict], overlap_rows: list[dict], duplicate_rows: list[dict]) -> list[dict]:
    by_strategy = {row["strategy"]: row for row in strategy_rows}
    rows = []
    for strategy, metrics in by_strategy.items():
        duplicates = [
            row for row in duplicate_rows
            if row["strategy_a"] == strategy and row["strategy_b"] != strategy
        ]
        overlaps = [
            row for row in overlap_rows
            if row["strategy_a"] == strategy and row["strategy_b"] != strategy
        ]
        max_duplicate = max((float(row["duplicate_percent_of_strategy_a"]) for row in duplicates), default=0)
        max_both_losing_overlap = max((float(row["both_losing_overlap_percent"]) for row in overlaps), default=0)
        best_duplicate_peer = max(duplicates, key=lambda row: float(row["duplicate_percent_of_strategy_a"]), default=None)
        if max_duplicate >= 50:
            deployment_role = "variant_candidate_only"
            warning = "Do not deploy beside the most-overlapping peer; treat as a replacement candidate."
        elif max_both_losing_overlap >= 25:
            deployment_role = "requires_correlation_throttle"
            warning = "Overlap losses are material; cap concurrent exposure or add a correlation gate."
        else:
            deployment_role = "possible_portfolio_member"
            warning = "No dominant duplicate-exposure warning from this report."
        rows.append({
            "strategy": strategy,
            "deployment_role": deployment_role,
            "warning": warning,
            "best_duplicate_peer": best_duplicate_peer["strategy_b"] if best_duplicate_peer else "",
            "max_duplicate_percent_vs_peer": round(max_duplicate, 4),
            "max_both_losing_overlap_percent_vs_peer": round(max_both_losing_overlap, 4),
            "total_trades": metrics["total_trades"],
            "net_profit": metrics["net_profit"],
            "profit_factor": metrics["profit_factor"],
            "average_r": metrics["average_r"],
            "worst_trade_r": metrics["worst_trade_r"],
        })
    return rows


def _session_matrix(trades: list[GroupTrade]) -> list[dict]:
    rows = []
    for strategy in sorted({trade.strategy for trade in trades}):
        for session in sorted({trade.session for trade in trades if trade.strategy == strategy}):
            group = [trade for trade in trades if trade.strategy == strategy and trade.session == session]
            rows.append({"strategy": strategy, "session": session, **_metrics(group)})
    return rows


def _monthly_strategy_matrix(trades: list[GroupTrade]) -> list[dict]:
    rows = []
    periods = sorted({trade.exit_timestamp_utc.strftime("%Y-%m") for trade in trades})
    strategies = sorted({trade.strategy for trade in trades})
    for period in periods:
        row = {"period": period}
        period_trades = [trade for trade in trades if trade.exit_timestamp_utc.strftime("%Y-%m") == period]
        row["portfolio_net_pnl"] = round(sum(trade.net_pnl for trade in period_trades), 2)
        row["portfolio_trades"] = len(period_trades)
        for strategy in strategies:
            group = [trade for trade in period_trades if trade.strategy == strategy]
            row[f"{strategy}_trades"] = len(group)
            row[f"{strategy}_net_pnl"] = round(sum(trade.net_pnl for trade in group), 2)
            row[f"{strategy}_average_r"] = round(mean([trade.pnl_r for trade in group]), 4) if group else 0
        rows.append(row)
    return rows


def _exposure_events(trades: list[GroupTrade]) -> list[dict]:
    events = []
    for trade in trades:
        events.append((trade.entry_timestamp_utc, 1, trade))
        events.append((trade.exit_timestamp_utc, -1, trade))
    active: set[tuple[str, str]] = set()
    rows = []
    for timestamp, delta, trade in sorted(events, key=lambda item: (item[0], item[1])):
        key = (trade.strategy, trade.trade_id)
        if delta > 0:
            active.add(key)
        else:
            active.discard(key)
        rows.append({
            "timestamp_utc": timestamp.isoformat(),
            "event": "entry" if delta > 0 else "exit",
            "strategy": trade.strategy,
            "trade_id": trade.trade_id,
            "active_trade_count_after_event": len(active),
        })
    return rows


def _conflict_events(trades: list[GroupTrade]) -> list[dict]:
    rows = []
    ordered = sorted(trades, key=lambda trade: trade.entry_timestamp_utc)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if right.entry_timestamp_utc > left.exit_timestamp_utc:
                break
            if left.strategy == right.strategy or not _overlaps(left, right):
                continue
            combined_pnl = left.net_pnl + right.net_pnl
            combined_r = left.pnl_r + right.pnl_r
            if combined_pnl >= 0:
                continue
            rows.append({
                "strategy_a": left.strategy,
                "trade_id_a": left.trade_id,
                "symbol_a": left.symbol,
                "entry_a": left.entry_timestamp_utc.isoformat(),
                "exit_a": left.exit_timestamp_utc.isoformat(),
                "pnl_r_a": round(left.pnl_r, 4),
                "net_pnl_a": round(left.net_pnl, 2),
                "strategy_b": right.strategy,
                "trade_id_b": right.trade_id,
                "symbol_b": right.symbol,
                "entry_b": right.entry_timestamp_utc.isoformat(),
                "exit_b": right.exit_timestamp_utc.isoformat(),
                "pnl_r_b": round(right.pnl_r, 4),
                "net_pnl_b": round(right.net_pnl, 2),
                "combined_pnl": round(combined_pnl, 2),
                "combined_r": round(combined_r, 4),
            })
    return sorted(rows, key=lambda row: row["combined_pnl"])


def _overlaps(left: GroupTrade, right: GroupTrade) -> bool:
    return left.entry_timestamp_utc < right.exit_timestamp_utc and right.entry_timestamp_utc < left.exit_timestamp_utc


def _same_day_pairs(left: list[GroupTrade], right: list[GroupTrade], *, skip_same: bool) -> int:
    count = 0
    for a in left:
        for b in right:
            if skip_same and a.trade_id >= b.trade_id:
                continue
            if a.entry_timestamp_utc.date() == b.entry_timestamp_utc.date():
                count += 1
    return count


def _same_signal_hour_pairs(left: list[GroupTrade], right: list[GroupTrade], *, skip_same: bool) -> int:
    count = 0
    for a in left:
        for b in right:
            if skip_same and a.trade_id >= b.trade_id:
                continue
            a_signal = a.signal_timestamp_utc or a.entry_timestamp_utc.replace(minute=0, second=0, microsecond=0)
            b_signal = b.signal_timestamp_utc or b.entry_timestamp_utc.replace(minute=0, second=0, microsecond=0)
            if a_signal == b_signal:
                count += 1
    return count


def _duplicate_pairs(left: list[GroupTrade], right: list[GroupTrade]) -> list[tuple[GroupTrade, GroupTrade]]:
    right_by_key = {}
    for trade in right:
        signal_time = trade.signal_timestamp_utc or trade.entry_timestamp_utc.replace(minute=0, second=0, microsecond=0)
        right_by_key.setdefault((signal_time, trade.entry_timestamp_utc, trade.symbol), []).append(trade)
    pairs = []
    for trade in left:
        signal_time = trade.signal_timestamp_utc or trade.entry_timestamp_utc.replace(minute=0, second=0, microsecond=0)
        matches = right_by_key.get((signal_time, trade.entry_timestamp_utc, trade.symbol), [])
        pairs.extend((trade, match) for match in matches)
    return pairs


def _active_counts(trades: list[GroupTrade]) -> list[int]:
    events = []
    for trade in trades:
        events.append((trade.entry_timestamp_utc, 1))
        events.append((trade.exit_timestamp_utc, -1))
    active = 0
    counts = []
    for _timestamp, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        counts.append(active)
    return counts


def _trades_opened_during_other_trade(trades: list[GroupTrade]) -> int:
    count = 0
    for trade in trades:
        if any(
            other.trade_id != trade.trade_id
            and other.strategy != trade.strategy
            and other.entry_timestamp_utc <= trade.entry_timestamp_utc < other.exit_timestamp_utc
            for other in trades
        ):
            count += 1
    return count


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _float(value: str | None) -> float:
    if value in {None, ""}:
        return 0.0
    return float(value)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        if not rows:
            handle.write("")
            return
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str))


def _write_html(
    path: Path,
    summary: dict,
    strategy_rows: list[dict],
    overlap_rows: list[dict],
    duplicate_rows: list[dict],
    deployment_rows: list[dict],
    session_rows: list[dict],
    monthly_rows: list[dict],
    conflict_rows: list[dict],
) -> None:
    html = "\n".join([
        "<!doctype html><html><head><meta charset='utf-8'><title>Strategy Group Research</title>",
        "<style>body{font-family:Arial,sans-serif;margin:24px;color:#17202a}table{border-collapse:collapse;margin:16px 0;width:100%}th,td{border:1px solid #d5d8dc;padding:6px 8px;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#f4f6f7}h1,h2{margin-bottom:8px}.note{color:#566573}</style>",
        "</head><body>",
        "<h1>Strategy Group Research</h1>",
        "<p class='note'>This report combines completed backtest run folders. It does not rerun signal generation.</p>",
        "<h2>Portfolio Summary</h2>",
        _table([summary]),
        "<h2>Strategy Attribution</h2>",
        _table(strategy_rows),
        "<h2>Deployment Risk Summary</h2>",
        _table(deployment_rows),
        "<h2>Duplicate Entry Matrix</h2>",
        _table(duplicate_rows),
        "<h2>Overlap Matrix</h2>",
        _table(overlap_rows),
        "<h2>Session Matrix</h2>",
        _table(session_rows),
        "<h2>Monthly Strategy Matrix</h2>",
        _table(monthly_rows),
        "<h2>Worst Overlap Loss Conflicts</h2>",
        _table(conflict_rows[:100]),
        "</body></html>",
    ])
    path.write_text(html)


def _table(rows: list[dict]) -> str:
    if not rows:
        return "<p>No rows.</p>"
    columns = list(dict.fromkeys(key for row in rows for key in row))
    header = "".join(f"<th>{escape(str(column))}</th>" for column in columns)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"
