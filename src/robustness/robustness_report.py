import html
from pathlib import Path

import polars as pl


def _table(rows) -> str:
    frame = rows if isinstance(rows, pl.DataFrame) else pl.DataFrame(rows) if rows else pl.DataFrame()
    if not frame.height:
        return "<p>No data available.</p>"
    headers = "".join(f"<th>{html.escape(column)}</th>" for column in frame.columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row.values()) + "</tr>"
                   for row in frame.to_dicts())
    return f"<table border='1'><tr>{headers}</tr>{body}</table>"


def write_robustness_report(output: Path, summary: dict, score: dict, baseline: dict,
                            one_factor: list[dict], paired: list[dict], local: list[dict],
                            neighbourhood: dict) -> Path:
    cliffs = [row for row in one_factor if row["sensitivity_level"] == "CLIFF"]
    sensitivity = {}
    for row in one_factor:
        sensitivity.setdefault(row["parameter_name"], []).append(abs(row["return_delta"]))
    cliff_parameters = {
        row["parameter_name"] for row in one_factor if row["sensitivity_level"] == "CLIFF"
    }
    ordered = sorted(
        sensitivity,
        key=lambda key: (key in cliff_parameters, sum(sensitivity[key]) / len(sensitivity[key])),
        reverse=True,
    )
    proceed = score["verdict"] in {"STRONG_ROBUSTNESS", "PASS"}
    report = output / "robustness_report.html"
    report.write_text(
        "<html><body><h1>FX-2E Parameter Robustness Testing</h1>"
        "<p><b>This is robustness testing, not parameter optimisation.</b> The baseline remains the "
        "reference and should not be replaced merely because another variant has higher return.</p>"
        f"<h2>Executive Summary</h2><p>Score: <b>{score['robustness_score']}</b>; verdict: "
        f"<b>{score['verdict']}</b>; proceed to Monte Carlo and execution stress testing: "
        f"<b>{'YES' if proceed else 'NO'}</b>.</p>"
        f"<p>Most nearby variants profitable: <b>{'YES' if score['profitable_variant_percent'] >= 70 else 'NO'}</b>. "
        f"Most pass safety criteria: <b>{'YES' if score['pass_variant_percent'] >= 60 else 'NO'}</b>. "
        f"Baseline isolated: <b>{neighbourhood.get('baseline_isolated_flag', False)}</b>. "
        f"Small-change collapse found: <b>{bool(cliffs)}</b>. Tail risk below -2.5R found: "
        f"<b>{summary['worst_observed_trade_r'] < -2.5}</b>.</p>"
        f"<p>Most sensitive parameter: <b>{ordered[0] if ordered else 'n/a'}</b>; least sensitive: "
        f"<b>{ordered[-1] if ordered else 'n/a'}</b>.</p>"
        f"<p>Normalised tick input: <b>{html.escape(summary['normalised_tick_path'])}</b>; "
        f"candle input: <b>{html.escape(summary['candle_path'])}</b>.</p>"
        f"<h2>Robustness Summary</h2>{_table([summary])}"
        f"<h2>Baseline Metrics</h2>{_table([baseline])}"
        f"<h2>One-Factor Sensitivity</h2>{_table(one_factor)}"
        f"<h2>Cliff Sensitivity Warnings</h2>{_table(cliffs)}"
        f"<h2>Paired Sensitivity Summary</h2>{_table(paired)}"
        f"<h2>Local Neighbourhood Analysis</h2>{_table(local)}{_table([neighbourhood])}"
        "<h2>Overfitting Warning</h2><p>We are looking for a stable cluster of acceptable performance, "
        "not the highest-return combination. The current baseline should remain the reference unless "
        "later research explicitly approves a change.</p>"
        f"<h2>Recommended Next Action</h2><p>{'Proceed to Monte Carlo and execution stress testing.' if proceed else 'Investigate parameter fragility before further validation.'}</p>"
        "<p>This remains historical research only and is not evidence of production readiness.</p></body></html>"
    )
    return report
