import html
from pathlib import Path


def write_html_report(output: Path, metrics: dict) -> None:
    cards = "".join(f"<tr><th>{html.escape(k)}</th><td>{v}</td></tr>" for k, v in metrics.items())
    (output / "html_report.html").write_text(
        f"<html><body><h1>FX Swing Trend Reclaim v1</h1><table>{cards}</table>"
        "<h2>Research warning</h2><p>This is a historical research backtest, not live trading advice.</p>"
        "</body></html>"
    )
