import html
from pathlib import Path


def write_html_report(output: Path, metrics: dict) -> None:
    forensic = output / "forensics" / "forensic_report.html"
    forensic_link = (
        "<h2>Integrity Forensics</h2><p><a href='forensics/forensic_report.html'>Open forensic report</a></p>"
        if forensic.exists() else
        "<h2>Integrity Forensics</h2><p>Not run for this backtest.</p>"
    )
    cards = "".join(f"<tr><th>{html.escape(k)}</th><td>{v}</td></tr>" for k, v in metrics.items())
    (output / "html_report.html").write_text(
        f"<html><body><h1>FX Swing Trend Reclaim v1</h1><table>{cards}</table>"
        f"{forensic_link}"
        "<h2>Research warning</h2><p>This is a historical research backtest, not live trading advice.</p>"
        "</body></html>"
    )
    if metrics.get("position_sizing_mode") == "fixed_spread_bet_stake":
        (output / "fixed_stake_backtest_report.html").write_text(
            f"<html><body><h1>USDJPY Fixed £{metrics['stake_per_pip_gbp']:.2f} Per Pip Backtest</h1>"
            f"<table>{cards}</table><h2>Purpose</h2><p>This backtest changes monetary sizing only. "
            "Signals, bid/ask execution, stops, targets, trailing logic, and guardrails are unchanged."
            "</p><h2>Research warning</h2><p>No IG DEMO or live order was placed.</p></body></html>"
        )


def add_forensic_link(output: Path, summary: dict) -> None:
    report = output / "html_report.html"
    if not report.exists():
        return
    content = report.read_text()
    block = (
        f"<h2>Integrity Forensics: {html.escape(summary['final_status'])}</h2>"
        f"<p>Worst trade: {summary['worst_trade_r']}R; critical flags: "
        f"{summary['critical_flag_count']}; warning flags: {summary['warning_flag_count']}.</p>"
        "<p><a href='forensics/forensic_report.html'>Open forensic report</a></p>"
    )
    content = content.replace("<h2>Integrity Forensics</h2><p>Not run for this backtest.</p>", block)
    report.write_text(content)
