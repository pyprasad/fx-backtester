import html
import json
from pathlib import Path


def build_recommendation(ranked: list[dict]) -> dict:
    top = ranked[0]
    complete = not top["missing_validation_layers"] and not top["hard_fail_flag"]
    return {
        "recommended_candidate": top["candidate_name"] if complete else None,
        "recommendation_confidence": "HIGH" if complete and len(ranked) > 1 and (
            top["overall_score"] - ranked[1]["overall_score"] > 5
        ) else "MEDIUM" if complete else "LOW",
        "reason_summary": (
            f"{top['candidate_name']} ranks first after hard-fail, weighted-score, and safety tie-break checks."
            if complete else "Required validation layers are incomplete or the leading candidate hard-failed."
        ),
        "key_strengths": [
            f"profit factor after funding {top['profit_factor_after_funding']}",
            f"maximum drawdown {top['max_drawdown_percent']}%",
            f"worst trade {top['worst_trade_r']}R",
        ],
        "key_weaknesses": [
            f"missing validation layers: {top['missing_validation_layers'] or 'none'}",
            f"return retention versus FX-2G baseline: {top['return_retention_vs_baseline']}%",
        ],
        "required_human_confirmation": True,
        "do_not_auto_modify_baseline": True,
        "next_phase_recommendation": "FX-2I Demo-Readiness Gate" if complete else "FX-2H-Review",
    }


def write_candidate_report(output: Path, ranked: list[dict], breakdowns: list[dict],
                           recommendation: dict, charts: list[str]) -> Path:
    by_name = {row["candidate_name"]: row for row in ranked}
    three = by_name.get("min_risk_3pips", {})
    five = by_name.get("recommended_research_guardrail", {})
    ig_only = by_name.get("ig_min_stop_only", {})
    keys = [
        "rank", "candidate_name", "overall_score", "recommendation", "return_after_funding",
        "profit_factor_after_funding", "average_r_after_funding", "max_drawdown_percent",
        "worst_trade_r", "bootstrap_p5_return", "bootstrap_p95_drawdown",
        "execution_stress_failure_count", "missing_validation_layers",
    ]
    table = "".join("<tr>" + "".join(
        f"<td>{html.escape(str(row.get(key, '')))}</td>" for key in keys
    ) + "</tr>" for row in ranked)
    chart_links = "".join(f"<li><a href='charts/{name}'>{html.escape(name)}</a></li>" for name in charts)
    path = output / "final_guardrail_bakeoff_report.html"
    path.write_text(
        "<html><body><h1>FX-2H Final Guardrail Candidate Bake-Off</h1>"
        "<h2>Executive Summary</h2>"
        f"<p>Recommended candidate: <b>{html.escape(str(recommendation['recommended_candidate']))}</b>. "
        f"Confidence: {recommendation['recommendation_confidence']}. Human confirmation is required.</p>"
        "<h2>Candidate Overview</h2><p>The bake-off compares exactly three surviving FX-2G "
        "guardrails without changing strategy entry or exit logic.</p>"
        "<h2>Why This Bake-Off Exists</h2><p>Highest historical return alone is insufficient; "
        "safety, drawdown, stress resilience, retention, and simplicity are considered.</p>"
        "<h2>Candidate Metrics Table</h2><table border='1'><tr>"
        + "".join(f"<th>{html.escape(key)}</th>" for key in keys) + f"</tr>{table}</table>"
        "<h2>Score Ranking</h2><p>Hard failures are applied before weighted ranking.</p>"
        f"<h2>Score Breakdown</h2><pre>{html.escape(json.dumps(breakdowns, indent=2))}</pre>"
        "<h2>Return vs Safety Comparison</h2><p>See metric table and linked charts.</p>"
        "<h2>Drawdown Comparison</h2><p>Lower drawdown is preferred when scores are close.</p>"
        "<h2>Worst-Trade Comparison</h2><p>Better worst-trade R is the first tie-breaker.</p>"
        "<h2>Execution Stress Comparison</h2><p>Missing stress data forces HUMAN_REVIEW.</p>"
        "<h2>Monte Carlo Comparison</h2><p>Monte Carlo is historical resampling, not prediction.</p>"
        "<h2>Funding-Adjusted Comparison</h2><p>Ranking uses return, PF, and average R after funding.</p>"
        "<h2>Trade-Count Retention Comparison</h2><p>Retention is considered but deliberately low-weighted.</p>"
        "<h2>Guardrail Simplicity Comparison</h2><p>Simplicity is the final tie-breaker.</p>"
        f"<h2>Final Recommendation</h2><pre>{html.escape(json.dumps(recommendation, indent=2))}</pre>"
        "<h2>Why Highest Return May Not Be Selected</h2><p>Execution fragility and safety can "
        "outweigh small return differences.</p><h2>Human Confirmation Required</h2>"
        f"<p>Is min_risk_3pips still the best balance? <b>{recommendation['recommended_candidate'] == 'min_risk_3pips'}</b>. "
        f"Is the 5-pip guardrail relatively conservative? <b>{five.get('return_after_funding', 0) < three.get('return_after_funding', 0)}</b>. "
        f"Does IG-min-only retain more execution exposure than 3 pips? "
        f"<b>{ig_only.get('max_spread_to_risk_ratio', 0) > three.get('max_spread_to_risk_ratio', 0)}</b>. "
        f"Does any candidate fail stress testing? <b>{any(row['execution_stress_failure_count'] > 0 for row in ranked)}</b>.</p>"
        "<p>No strategy or demo baseline is modified automatically.</p>"
        f"<h2>Charts</h2><ul>{chart_links}</ul><h2>Recommended Next Phase</h2>"
        f"<p>{recommendation['next_phase_recommendation']}</p>"
        "<p>This remains historical research only. It does not make the strategy production-ready.</p>"
        "</body></html>"
    )
    return path
