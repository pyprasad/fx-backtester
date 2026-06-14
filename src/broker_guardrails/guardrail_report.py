import html
from pathlib import Path


def write_guardrail_report(output: Path, rows: list[dict], assumptions: dict) -> Path:
    def value(row: dict, key: str, default=0):
        return row.get(key, default)

    ranked = sorted(rows, key=lambda row: row["score"], reverse=True)
    headers = "".join(f"<th>{html.escape(key)}</th>" for key in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row.values())
                   + "</tr>" for row in ranked)
    best = ranked[0]
    baseline = next((row for row in rows if row["variant_name"] == "baseline_no_extra_guardrails"), rows[0])
    recommended = next((row for row in rows if row["variant_name"] == "recommended_research_guardrail"), best)
    report = output / "broker_guardrail_report.html"
    report.write_text(
        "<html><body><h1>FX-2G Broker-Realistic Execution Guardrails + Overnight Funding</h1>"
        "<p>This is research-only broker realism testing, not strategy optimisation. The baseline "
        "is not automatically replaced.</p><h2>Executive Summary</h2>"
        f"<p>Best safety-adjusted research candidate: <b>{html.escape(best['variant_name'])}</b>; "
        f"score: <b>{best['score']}</b>; verdict: <b>{best['verdict']}</b>.</p>"
        f"<h2>Broker Assumptions</h2><pre>{html.escape(str(assumptions))}</pre>"
        f"<h2>Business Questions</h2><p>Baseline trades below 2 pips risk: "
        f"<b>{value(baseline, 'trades_below_2_pips_risk')}</b>; below 5 pips risk: "
        f"<b>{value(baseline, 'trades_below_5_pips_risk')}</b>. Recommended candidate minimum-risk "
        f"rejections: <b>{value(recommended, 'min_risk_rejections')}</b>; funding-time rejections: "
        f"<b>{value(recommended, 'funding_time_rejections')}</b>. It remained profitable after funding: "
        f"<b>{value(recommended, 'return_percent_after_funding') > 0}</b>; overnight trades: "
        f"<b>{value(recommended, 'overnight_trade_count')}</b>; funding days: "
        f"<b>{value(recommended, 'funding_days')}</b>; Wednesday triple-rollover events: "
        f"<b>{value(recommended, 'wednesday_triple_rollover_count')}</b>. Removing tiny-risk and "
        "high spread/risk signals reduces the accepted-set execution-risk proxy when maximum "
        f"spread/risk falls below baseline: <b>{value(recommended, 'max_spread_to_risk_ratio') < value(baseline, 'max_spread_to_risk_ratio')}</b>.</p>"
        f"<h2>Baseline vs Guardrail Variants</h2><table border='1'><tr>{headers}</tr>{body}</table>"
        "<h2>Signal Rejection Breakdown</h2><p>Distance, minimum-risk, spread/risk, and funding-time "
        "rejections are shown in the comparison table and each variant rejection log.</p>"
        "<h2>Initial Risk and Spread-to-Risk Distribution</h2><p>Threshold counts and maximum/"
        "average spread-to-risk ratios are shown per variant.</p>"
        "<h2>Funding Exposure</h2><p>Funding-adjusted performance and Wednesday triple-rollover "
        "exposure are shown per variant. Funding uses configurable pip-cost assumptions, not live IG rates.</p>"
        f"<h2>Recommended Research Baseline</h2><p><b>{html.escape(best['variant_name'])}</b> is "
        "the highest safety-adjusted research candidate only. Review rejected-trade concentration "
        "and funding assumptions before approval.</p>"
        "<h2>Limitations</h2><p>Signal guardrails use signal-close spread and proposed mid-price "
        "distances. No live IG execution or live funding-rate retrieval is implemented.</p>"
        "<p>Passing FX-2G does not make the strategy production-ready.</p></body></html>"
    )
    return report
