import html
from pathlib import Path

import polars as pl


def _table(frame: pl.DataFrame) -> str:
    if not frame.height:
        return "<p>No data available.</p>"
    headers = "".join(f"<th>{html.escape(column)}</th>" for column in frame.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row.values()) + "</tr>"
        for row in frame.to_dicts()
    )
    return f"<table border='1'><tr>{headers}</tr>{rows}</table>"


def _bars(frame: pl.DataFrame, label: str, value: str) -> str:
    if not frame.height:
        return "<p>No data available.</p>"
    maximum = max(abs(float(item)) for item in frame[value]) or 1
    return "".join(
        f"<div>{html.escape(str(row[label]))}: {row[value]}<br>"
        f"<span style='display:inline-block;background:#4472c4;height:12px;width:"
        f"{max(1, abs(float(row[value])) / maximum * 400):.0f}px'></span></div>"
        for row in frame.select(label, value).to_dicts()
    )


def write_walk_forward_report(output: Path, summary: dict, score: dict, anchored: pl.DataFrame,
                              rolling_summary: pl.DataFrame, rolling_details: dict[str, pl.DataFrame]) -> Path:
    all_anchored_positive = bool(anchored.height and anchored["test_positive_flag"].all())
    any_bad_drawdown = bool(anchored.height and anchored["test_max_drawdown_percent"].max() > 10)
    any_bad_trade = bool(anchored.height and anchored["test_worst_trade_r"].min() < -2.5)
    decay = bool(
        anchored.height and (
            anchored["profit_factor_decay_percent"].median() > 50
            or anchored["average_r_decay_percent"].median() > 60
        )
    )
    low_sample = anchored.filter(
        pl.col("low_train_sample_warning") | pl.col("low_test_sample_warning")
    ) if anchored.height else anchored
    details = "".join(f"<h3>{html.escape(name)}</h3>{_table(frame)}" for name, frame in rolling_details.items())
    proceed = score["verdict"] in {"STRONG_WALK_FORWARD", "PASS"}
    report = output / "walk_forward_report.html"
    report.write_text(
        "<html><body><h1>FX-2D Walk-Forward Validation</h1>"
        f"<h2>Executive Summary</h2><p>Score: <b>{score['walk_forward_score']}</b>; verdict: "
        f"<b>{score['verdict']}</b>. Suitable to proceed to parameter robustness testing: "
        f"<b>{'YES' if proceed else 'NO'}</b>.</p>"
        f"<p>Strategy: {html.escape(summary['strategy_name'])}; market: {html.escape(summary['market'])}; "
        f"weekend policy: {html.escape(summary['weekend_policy_name'])}; baseline: "
        f"{html.escape(summary['baseline_run_path'])}.</p>"
        f"<p>Every anchored out-of-sample year profitable: <b>{'YES' if all_anchored_positive else 'NO'}</b>. "
        f"Unacceptable test drawdown: <b>{'YES' if any_bad_drawdown else 'NO'}</b>. "
        f"Test trade below -2.5R: <b>{'YES' if any_bad_trade else 'NO'}</b>.</p>"
        f"<h2>Walk-Forward Summary</h2>{_table(pl.DataFrame([summary]))}"
        f"<h2>Anchored Train/Test Results</h2>{_table(anchored)}"
        f"<h2>Rolling Window Summary</h2>{_table(rolling_summary)}"
        f"<h2>Detailed Rolling Windows</h2>{details}"
        f"<h2>Test Profit Factor Chart</h2>{_bars(anchored, 'name', 'test_profit_factor')}"
        f"<h2>Test Average R Chart</h2>{_bars(anchored, 'name', 'test_average_r')}"
        f"<h2>Test Window Return Chart</h2>{_bars(anchored, 'name', 'test_return_percent')}"
        f"<h2>Test Drawdown Chart</h2>{_bars(anchored, 'name', 'test_max_drawdown_percent')}"
        f"<h2>Low Sample-Size Warnings</h2>{_table(low_sample)}"
        f"<h2>Evidence of Overfitting</h2><p>{'Material train/test decay detected.' if decay else 'No material anchored train/test decay detected.'}</p>"
        f"<h2>Recommended Next Action</h2><p>{'Proceed to parameter robustness testing.' if proceed else 'Investigate out-of-sample weaknesses before parameter robustness testing.'}</p>"
        "<p>This is historical research only and is not evidence of production readiness.</p></body></html>"
    )
    return report
