import csv
import html
import json
from pathlib import Path


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        if not rows:
            handle.write("")
            return
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, default=str) if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            })


def write_forensic_report(output: Path, summary: dict, worst: list[dict], flags: list[dict]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "forensic_summary.json").write_text(json.dumps(summary, default=str, indent=2))
    write_rows(output / "forensic_summary.csv", [summary])
    cards = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in summary.items()
    )
    worst_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key in (
            "trade_id", "direction", "entry_timestamp_utc", "exit_timestamp_utc", "actual_pnl_r",
            "actual_exit_reason", "held_over_weekend", "expected_exit_reason_if_first_barrier_wins",
            "integrity_flags",
        )) + "</tr>" for row in worst
    )
    flag_rows = "".join(
        f"<tr><td>{html.escape(str(row['trade_id']))}</td><td>{html.escape(str(row['flag']))}</td></tr>"
        for row in flags
    )
    verdict = {
        "PASS": "Engine appears trustworthy for the audited conditions.",
        "WARNING": "Execution appears technically consistent, but gap/slippage risk exists.",
        "FAIL": "An execution or reporting mismatch requires correction.",
    }[summary["final_status"]]
    (output / "forensic_report.html").write_text(
        f"<html><body><h1>FX-2A Backtest Integrity Forensics: {summary['final_status']}</h1>"
        f"<p>{verdict}</p><h2>Summary</h2><table>{cards}</table>"
        "<h2>Worst Trade Forensics</h2><p>The first row is the automatically identified worst trade.</p>"
        "<table border='1'><tr><th>Trade ID</th><th>Direction</th><th>Entry</th><th>Exit</th>"
        "<th>R</th><th>Actual Exit</th><th>Weekend</th><th>Expected Exit</th><th>Flags</th></tr>"
        f"{worst_rows}</table><h2>Integrity Flags</h2><table border='1'>{flag_rows}</table>"
        "<h2>Flag Meaning</h2><p>FAIL flags identify execution/reporting defects. WARNING flags "
        "identify technically valid execution with material gap, spread, or slippage risk.</p>"
        "<p>This is research-only validation and is not live trading advice.</p></body></html>"
    )
