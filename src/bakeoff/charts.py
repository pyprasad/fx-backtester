from pathlib import Path

import plotly.graph_objects as go


def _bar(rows: list[dict], key: str, title: str) -> go.Figure:
    return go.Figure(
        data=[go.Bar(x=[row["candidate_name"] for row in rows], y=[row[key] for row in rows])],
        layout={"title": title},
    )


def _scatter(rows: list[dict], x: str, y: str, title: str) -> go.Figure:
    return go.Figure(
        data=[go.Scatter(
            x=[row[x] for row in rows], y=[row[y] for row in rows],
            text=[row["candidate_name"] for row in rows], mode="markers+text",
        )],
        layout={"title": title, "xaxis_title": x, "yaxis_title": y},
    )


def generate_charts(output: Path, rows: list[dict], breakdowns: list[dict]) -> list[str]:
    output.mkdir(parents=True, exist_ok=True)
    definitions = [
        ("candidate_total_return.html", _bar(rows, "return_after_funding", "Return After Funding")),
        ("candidate_profit_factor.html", _bar(rows, "profit_factor_after_funding", "Profit Factor")),
        ("candidate_max_drawdown.html", _bar(rows, "max_drawdown_percent", "Maximum Drawdown")),
        ("candidate_worst_trade.html", _bar(rows, "worst_trade_r", "Worst Trade R")),
        ("return_vs_drawdown.html", _scatter(
            rows, "max_drawdown_percent", "return_after_funding", "Return vs Drawdown"
        )),
        ("return_vs_worst_trade.html", _scatter(
            rows, "worst_trade_r", "return_after_funding", "Return vs Worst Trade"
        )),
    ]
    if all(row.get("bootstrap_p5_return") is not None for row in rows):
        definitions.append(("monte_carlo_return_vs_drawdown.html", _scatter(
            rows, "bootstrap_p95_drawdown", "bootstrap_p5_return",
            "Monte Carlo P5 Return vs P95 Drawdown",
        )))
    score_keys = [key for key in breakdowns[0] if key.endswith("_score") and key != "weighted_total_score"]
    score_chart = go.Figure()
    for key in score_keys:
        score_chart.add_bar(
            name=key, x=[row["candidate_name"] for row in breakdowns],
            y=[row[key] for row in breakdowns],
        )
    score_chart.update_layout(title="Candidate Score Breakdown", barmode="stack")
    definitions.append(("candidate_score_breakdown.html", score_chart))
    for name, chart in definitions:
        chart.write_html(output / name, include_plotlyjs="cdn")
    return [name for name, _chart in definitions]
