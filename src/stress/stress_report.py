import html
from pathlib import Path

import polars as pl


def _table(rows) -> str:
    frame = pl.DataFrame(rows) if rows else pl.DataFrame()
    if not frame.height:
        return "<p>No data available.</p>"
    headers = "".join(f"<th>{html.escape(column)}</th>" for column in frame.columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row.values())
                   + "</tr>" for row in frame.to_dicts())
    return f"<table border='1'><tr>{headers}</tr>{body}</table>"


def write_stress_report(output: Path, summary: dict, score: dict, distribution: dict,
                        scenarios: list[dict], sequence: list[dict], execution: list[dict],
                        missed: list[dict], tail: list[dict]) -> Path:
    proceed = score["verdict"] in {"STRONG_STRESS_RESILIENCE", "PASS"}
    path = output / "stress_report.html"
    path.write_text(
        "<html><body><h1>FX-2F Monte Carlo + Execution Stress Testing</h1>"
        "<p><b>This is stress testing, not optimisation.</b> The baseline strategy is unchanged. "
        "Monte Carlo does not predict the future; it estimates plausible outcomes from historical "
        "trade behaviour and explicit stress assumptions.</p>"
        f"<h2>Executive Summary</h2><p>Score: <b>{score['stress_score']}</b>; verdict: "
        f"<b>{score['verdict']}</b>; proceed toward demo-readiness gates: "
        f"<b>{'YES' if proceed else 'NO'}</b>.</p>"
        f"<p>5th percentile return: <b>{distribution['p5_return_percent']}%</b>; 95th percentile "
        f"drawdown: <b>{distribution['p95_max_drawdown_percent']}%</b>; probability of loss: "
        f"<b>{distribution['probability_of_loss_percent']}%</b>; probability drawdown above 10%: "
        f"<b>{distribution['probability_drawdown_above_10_percent']}%</b>.</p>"
        f"<h2>Stress Summary</h2>{_table([summary])}<h2>Distribution</h2>{_table([distribution])}"
        "<p>Stress-path drawdown is measured relative to the running peak at each equity point and "
        "may differ from the existing backtest report's drawdown percentage convention.</p>"
        f"<h2>Monte Carlo Scenarios</h2>{_table(scenarios)}"
        f"<h2>Sequence Stress</h2>{_table(sequence)}"
        f"<h2>Execution, Spread, Slippage, Delay, and Friday Close Stress</h2>{_table(execution)}"
        f"<h2>Missed Trade Stress</h2>{_table(missed)}"
        f"<h2>Tail-Loss Injection</h2>{_table(tail)}"
        f"<h2>Key Weaknesses</h2><p>Execution stress produced a trade below the configured -5R "
        f"safety limit: <b>{score.get('execution_tail_warning', False)}</b>. Missed-best-trade "
        "scenarios measure dependence on the strongest historical outcomes.</p>"
        "<h2>Charts</h2><p><a href='charts/sample_equity_paths.html'>Sample equity paths</a> | "
        "<a href='charts/total_return_percent_distribution.html'>Return distribution</a> | "
        "<a href='charts/max_drawdown_percent_distribution.html'>Drawdown distribution</a> | "
        "<a href='charts/profit_factor_distribution.html'>Profit-factor distribution</a> | "
        "<a href='charts/scenario_comparison.html'>Scenario comparison</a></p>"
        "<h2>Limitations</h2><p>Delayed execution uses an R-based adverse-slippage approximation; "
        "true delayed tick replay remains a future enhancement.</p>"
        f"<h2>Recommended Next Action</h2><p>{'Proceed toward demo-readiness checks.' if proceed else 'Investigate stress weaknesses before demo-readiness checks.'}</p>"
        "<p>Passing FX-2F does not make the strategy production-ready.</p></body></html>"
    )
    return path
