import csv
import html
from pathlib import Path


def _as_float(row: dict, key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value in (None, ""):
        return default
    return float(value)


def _load_csv(path: str | Path) -> list[dict]:
    with Path(path).open() as handle:
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


def _stress_lookup(stress_rows: list[dict], label: str, *, method: str, slippage: float, missed: float) -> dict:
    for row in stress_rows:
        if (
            row["label"] == label
            and row["method"] == method
            and _as_float(row, "slippage_pips_per_execution") == slippage
            and _as_float(row, "missed_trade_rate") == missed
        ):
            return row
    return {}


def score_candidate(summary: dict, stress_rows: list[dict]) -> dict:
    label = summary["label"]
    bootstrap_base = _stress_lookup(stress_rows, label, method="bootstrap", slippage=0.0, missed=0.0)
    bootstrap_adverse = _stress_lookup(stress_rows, label, method="bootstrap", slippage=1.0, missed=0.10)
    miss_best_adverse = _stress_lookup(stress_rows, label, method="miss_best", slippage=1.0, missed=0.10)
    net_pips = _as_float(summary, "net_pips")
    drawdown = _as_float(summary, "max_pip_drawdown")
    p05_base = _as_float(bootstrap_base, "p05_net_pips")
    p05_adverse = _as_float(bootstrap_adverse, "p05_net_pips")
    miss_best = _as_float(miss_best_adverse, "median_net_pips")
    drawdown_penalty = min(30.0, drawdown / 25.0)
    miss_best_penalty = min(35.0, abs(min(0.0, miss_best)) / 150.0)
    p05_bonus = max(0.0, min(25.0, p05_adverse / 80.0))
    raw_pip_bonus = max(0.0, min(25.0, net_pips / 200.0))
    efficiency_bonus = max(0.0, min(15.0, _as_float(summary, "return_over_pip_drawdown") / 1.5))
    score = raw_pip_bonus + p05_bonus + efficiency_bonus - drawdown_penalty - miss_best_penalty
    hard_flags = []
    if p05_adverse <= 0:
        hard_flags.append("ADVERSE_BOOTSTRAP_P05_NOT_POSITIVE")
    if miss_best <= -3000:
        hard_flags.append("MISS_BEST_10_WITH_1PIP_SLIPPAGE_FRAGILE")
    if drawdown > 350:
        hard_flags.append("HIGH_PIP_DRAWDOWN")
    return {
        "label": label,
        "total_trades": summary.get("total_trades", ""),
        "net_pips": round(net_pips, 2),
        "max_pip_drawdown": round(drawdown, 2),
        "return_over_pip_drawdown": summary.get("return_over_pip_drawdown", ""),
        "bootstrap_p05_net_pips": round(p05_base, 2),
        "adverse_bootstrap_p05_net_pips": round(p05_adverse, 2),
        "miss_best_10pct_1pip_net_pips": round(miss_best, 2),
        "score": round(score, 4),
        "hard_flags": "|".join(hard_flags),
        "recommendation": "",
    }


def write_pip_first_decision_report(
    *,
    comparison_summary_path: str | Path,
    stress_summary_path: str | Path,
    output_path: str | Path,
) -> Path:
    comparison_rows = _load_csv(comparison_summary_path)
    stress_rows = _load_csv(stress_summary_path)
    rows = [score_candidate(row, stress_rows) for row in comparison_rows]
    rows.sort(key=lambda row: (not row["hard_flags"], row["score"]), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    clean = [row for row in rows if not row["hard_flags"]]
    selected = clean[0] if clean else rows[0] if rows else None
    if selected:
        selected["recommendation"] = "SELECTED_FOR_NEXT_PIP_FIRST_VALIDATION"
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "pip_first_decision_summary.csv", rows)
    body = [
        "<html><body><h1>Pip-First Decision Report</h1>",
        "<p>Safety-first ranking: raw pips, adverse bootstrap p05, drawdown, and miss-best-trades fragility.</p>",
        _html_table(rows),
        "</body></html>",
    ]
    (output / "pip_first_decision_report.html").write_text("\n".join(body))
    return output
