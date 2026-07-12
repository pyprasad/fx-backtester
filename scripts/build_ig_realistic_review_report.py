#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

import plotly.graph_objects as go
import yaml
from plotly.offline.offline import get_plotlyjs
from plotly.subplots import make_subplots


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "ig_realistic_candidate_validation" / "review" / "ig_realistic_strategy_review.html"
PIP_SIZE = 0.01
MIN_INITIAL_RISK_PIPS = 3.0
MIN_STOP_OR_LIMIT_DISTANCE_PIPS = 2.0
SPREAD_TO_RISK_WARNING = 0.20

FINAL_CONTRACT = ROOT / "config" / "strategies" / "usdjpy_fx_swing_trend_reclaim_v1_final.yaml"
REFERENCE_SELECTED_BASELINE = (
    ROOT
    / "reports"
    / "next_level_validation"
    / "atr15_guardrails"
    / "20260618_135434_usdjpy_fx_swing_trend_reclaim_v1"
    / "variants"
    / "min_risk_3pips"
)

VARIANTS = {
    "swing_risk025": {
        "label": "Swing 0.25%",
        "backtest": ROOT
        / "reports"
        / "ig_realistic_candidate_validation"
        / "backtests"
        / "swing_risk025"
        / "20260711_133240_usdjpy_fx_swing_trend_reclaim_v1_atr15_long_short_ig_realistic_swing_risk025",
        "validation": ROOT / "reports" / "ig_realistic_candidate_validation" / "validation" / "swing_risk025",
    },
    "swing_risk050": {
        "label": "Swing 0.50%",
        "backtest": ROOT
        / "reports"
        / "ig_realistic_candidate_validation"
        / "backtests"
        / "swing_risk050"
        / "20260711_133044_usdjpy_fx_swing_trend_reclaim_v1_atr15_long_short_ig_realistic_swing_risk050",
        "validation": ROOT / "reports" / "ig_realistic_candidate_validation" / "validation" / "swing_risk050",
    },
    "intraday_risk025": {
        "label": "Intraday 0.25%",
        "backtest": ROOT
        / "reports"
        / "ig_realistic_candidate_validation"
        / "backtests"
        / "intraday_risk025"
        / "20260711_133226_usdjpy_fx_swing_trend_reclaim_v1_atr15_long_short_ig_realistic_intraday_risk025",
        "validation": ROOT / "reports" / "ig_realistic_candidate_validation" / "validation" / "intraday_risk025",
    },
    "intraday_risk050": {
        "label": "Intraday 0.50%",
        "backtest": ROOT
        / "reports"
        / "ig_realistic_candidate_validation"
        / "backtests"
        / "intraday_risk050"
        / "20260711_133029_usdjpy_fx_swing_trend_reclaim_v1_atr15_long_short_ig_realistic_intraday_risk050",
        "validation": ROOT / "reports" / "ig_realistic_candidate_validation" / "validation" / "intraday_risk050",
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_one_csv(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    return rows[0] if rows else {}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def latest_file(root: Path, pattern: str) -> Path:
    matches = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No file matching {pattern} under {root}")
    return matches[0]


def fnum(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def pct(value: Any) -> str:
    return f"{fnum(value):,.2f}%"


def money(value: Any) -> str:
    return f"{fnum(value):,.2f}"


def num(value: Any, places: int = 2) -> str:
    return f"{fnum(value):,.{places}f}"


def link(path: Path, label: str | None = None) -> str:
    rel = Path(os.path.relpath(path, OUTPUT.parent))
    text = label or path.name
    return f"<a href='{html.escape(rel.as_posix())}'>{html.escape(text)}</a>"


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def relative_html(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id)


def drawdown_percent_curve(equity_rows: list[dict[str, str]]) -> tuple[list[str], list[float]]:
    times: list[str] = []
    values: list[float] = []
    peak = 0.0
    for row in equity_rows:
        balance = fnum(row.get("balance"))
        peak = max(peak, balance)
        drawdown = 0.0 if peak <= 0 else (peak - balance) / peak * 100
        times.append(row.get("timestamp", ""))
        values.append(drawdown)
    return times, values


def trade_distance_stats(trades: list[dict[str, str]]) -> dict[str, Any]:
    risks = [fnum(row.get("initial_risk_pips")) for row in trades]
    spreads = [fnum(row.get("spread_pips_at_entry")) for row in trades]
    sizes = [fnum(row.get("size")) for row in trades]
    risk_amounts = [fnum(row.get("risk_amount")) for row in trades]
    close_distances = [abs(fnum(row.get("exit_price")) - fnum(row.get("entry_price"))) / PIP_SIZE for row in trades]
    durations = [fnum(row.get("duration_hours")) for row in trades]
    ratios = [
        spread / risk
        for spread, risk in zip(spreads, risks, strict=False)
        if risk > 0
    ]
    near_risk = [row for row in trades if fnum(row.get("initial_risk_pips")) < MIN_INITIAL_RISK_PIPS + 1.0]
    below_risk = [row for row in trades if fnum(row.get("initial_risk_pips")) < MIN_INITIAL_RISK_PIPS]
    below_stop = [row for row in trades if fnum(row.get("initial_risk_pips")) < MIN_STOP_OR_LIMIT_DISTANCE_PIPS]
    spread_warn = [
        row
        for row in trades
        if fnum(row.get("initial_risk_pips")) > 0
        and fnum(row.get("spread_pips_at_entry")) / fnum(row.get("initial_risk_pips")) > SPREAD_TO_RISK_WARNING
    ]
    tiny_realised = [row for row, distance in zip(trades, close_distances, strict=False) if distance < MIN_STOP_OR_LIMIT_DISTANCE_PIPS]
    return {
        "min_risk": min(risks) if risks else 0.0,
        "p5_risk": percentile(risks, 0.05),
        "median_risk": median(risks) if risks else 0.0,
        "min_close_distance": min(close_distances) if close_distances else 0.0,
        "p5_close_distance": percentile(close_distances, 0.05),
        "median_close_distance": median(close_distances) if close_distances else 0.0,
        "median_duration": median(durations) if durations else 0.0,
        "avg_spread": mean(spreads) if spreads else 0.0,
        "min_size": min(sizes) if sizes else 0.0,
        "p5_size": percentile(sizes, 0.05),
        "median_size": median(sizes) if sizes else 0.0,
        "max_size": max(sizes) if sizes else 0.0,
        "min_risk_amount": min(risk_amounts) if risk_amounts else 0.0,
        "median_risk_amount": median(risk_amounts) if risk_amounts else 0.0,
        "max_risk_amount": max(risk_amounts) if risk_amounts else 0.0,
        "max_spread_to_risk": max(ratios) if ratios else 0.0,
        "below_initial_risk_count": len(below_risk),
        "below_stop_distance_count": len(below_stop),
        "near_initial_risk_count": len(near_risk),
        "spread_warning_count": len(spread_warn),
        "tiny_realised_count": len(tiny_realised),
        "near_initial_risk_trades": sorted(near_risk, key=lambda row: fnum(row.get("initial_risk_pips")))[:20],
        "tiny_realised_trades": sorted(
            tiny_realised,
            key=lambda row: abs(fnum(row.get("exit_price")) - fnum(row.get("entry_price"))) / PIP_SIZE,
        )[:20],
        "worst_trades": sorted(trades, key=lambda row: fnum(row.get("pnl_r")))[:20],
        "best_trades": sorted(trades, key=lambda row: fnum(row.get("pnl_r")), reverse=True)[:10],
    }


def load_variant(slug: str, meta: dict[str, Any]) -> dict[str, Any]:
    backtest = meta["backtest"]
    validation = meta["validation"]
    return {
        "slug": slug,
        "label": meta["label"],
        "backtest": backtest,
        "summary": read_one_csv(backtest / "strategy_summary.csv"),
        "equity": read_csv(backtest / "equity_curve.csv"),
        "drawdown": read_csv(backtest / "drawdown_report.csv"),
        "monthly": read_csv(backtest / "monthly_performance.csv"),
        "trades": read_csv(backtest / "trade_log.csv"),
        "stability": read_json(latest_file(validation / "stability", "*/stability_summary.json")),
        "walk_forward": read_json(latest_file(validation / "walk_forward", "*/walk_forward_summary.json")),
        "stress": read_json(latest_file(validation / "monte_carlo", "*/stress_summary.json")),
        "stability_report": latest_file(validation / "stability", "*/stability_report.html"),
        "walk_forward_report": latest_file(validation / "walk_forward", "*/walk_forward_report.html"),
        "stress_report": latest_file(validation / "monte_carlo", "*/stress_report.html"),
    }


def equity_chart(variants: list[dict[str, Any]]) -> str:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for variant in variants:
        equity = variant["equity"]
        times = [row["timestamp"] for row in equity]
        balances = [fnum(row["balance"]) for row in equity]
        dd_times, dd_values = drawdown_percent_curve(equity)
        fig.add_trace(go.Scatter(x=times, y=balances, name=f"{variant['label']} balance", mode="lines"))
        fig.add_trace(
            go.Scatter(x=dd_times, y=dd_values, name=f"{variant['label']} drawdown %", mode="lines", line={"dash": "dot"}),
            secondary_y=True,
        )
    fig.update_layout(title="Balance and Peak-Relative Drawdown", height=620, margin={"l": 40, "r": 40, "t": 60, "b": 40})
    fig.update_yaxes(title_text="Balance", secondary_y=False)
    fig.update_yaxes(title_text="Drawdown %", secondary_y=True)
    return relative_html(fig, "equity-chart")


def monthly_chart(variants: list[dict[str, Any]]) -> str:
    fig = go.Figure()
    for variant in variants:
        fig.add_trace(
            go.Bar(
                x=[row["period"] for row in variant["monthly"]],
                y=[fnum(row["net_pnl"]) for row in variant["monthly"]],
                name=variant["label"],
            )
        )
    fig.update_layout(title="Monthly Net P&L", barmode="group", height=520, margin={"l": 40, "r": 40, "t": 60, "b": 80})
    return relative_html(fig, "monthly-chart")


def risk_distance_chart(variants: list[dict[str, Any]]) -> str:
    fig = go.Figure()
    for variant in variants:
        risks = [fnum(row.get("initial_risk_pips")) for row in variant["trades"]]
        close_distances = [
            abs(fnum(row.get("exit_price")) - fnum(row.get("entry_price"))) / PIP_SIZE
            for row in variant["trades"]
        ]
        fig.add_trace(go.Box(y=risks, name=f"{variant['label']} initial risk", boxpoints=False))
        fig.add_trace(go.Box(y=close_distances, name=f"{variant['label']} open-close", boxpoints=False))
    fig.add_hline(y=MIN_INITIAL_RISK_PIPS, line_dash="dash", line_color="#d14", annotation_text="3 pip selected min initial risk")
    fig.add_hline(y=MIN_STOP_OR_LIMIT_DISTANCE_PIPS, line_dash="dot", line_color="#a70", annotation_text="2 pip IG min stop/limit reference")
    fig.update_layout(title="Trade Distance Distribution in Pips", height=560, margin={"l": 40, "r": 40, "t": 60, "b": 120})
    fig.update_yaxes(title_text="Pips")
    return relative_html(fig, "risk-distance-chart")


def stress_chart(variants: list[dict[str, Any]]) -> str:
    labels = [variant["label"] for variant in variants]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=[fnum(v["stress"]["baseline_return_percent"]) for v in variants], name="Baseline return %"))
    fig.add_trace(go.Bar(x=labels, y=[fnum(v["stress"]["p5_return_percent"]) for v in variants], name="Monte Carlo p5 return %"))
    fig.add_trace(go.Bar(x=labels, y=[fnum(v["stress"]["worst_execution_return_percent"]) for v in variants], name="Worst execution return %"))
    fig.update_layout(title="Stress Return Comparison", barmode="group", height=480, margin={"l": 40, "r": 40, "t": 60, "b": 70})
    return relative_html(fig, "stress-chart")


def table(headers: list[str], rows: list[list[Any]], css_class: str = "", raw_columns: set[int] | None = None) -> str:
    raw_columns = raw_columns or set()
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{cell if index in raw_columns else html.escape(str(cell))}</td>"
            for index, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    klass = f" class='{css_class}'" if css_class else ""
    return f"<table{klass}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def trade_rows(trades: list[dict[str, str]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for row in trades:
        close_pips = abs(fnum(row.get("exit_price")) - fnum(row.get("entry_price"))) / PIP_SIZE
        rows.append(
            [
                row.get("entry_timestamp_utc", ""),
                row.get("exit_timestamp_utc", ""),
                row.get("direction", ""),
                num(row.get("size"), 2),
                money(row.get("risk_amount")),
                num(row.get("initial_risk_pips"), 2),
                num(row.get("spread_pips_at_entry"), 2),
                num(close_pips, 2),
                num(row.get("duration_hours"), 2),
                num(row.get("pnl_r"), 2),
                row.get("exit_reason", ""),
            ]
        )
    return rows


def build() -> str:
    variants = [load_variant(slug, meta) for slug, meta in VARIANTS.items()]
    for variant in variants:
        variant["distance"] = trade_distance_stats(variant["trades"])

    final_contract = yaml.safe_load(FINAL_CONTRACT.read_text())
    selected_summary = read_one_csv(REFERENCE_SELECTED_BASELINE / "strategy_summary.csv")
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    overview_rows = []
    for variant in variants:
        summary = variant["summary"]
        stress = variant["stress"]
        wf = variant["walk_forward"]
        stability = variant["stability"]
        overview_rows.append(
            [
                variant["label"],
                summary.get("total_trades"),
                pct(summary.get("total_return_percent")),
                money(summary.get("ending_balance")),
                pct(summary.get("max_drawdown_percent")),
                num(summary.get("profit_factor"), 2),
                pct(summary.get("win_rate")),
                stability.get("verdict"),
                wf.get("final_verdict"),
                stress.get("verdict"),
            ]
        )

    distance_rows = []
    size_rows = []
    for variant in variants:
        stats = variant["distance"]
        distance_rows.append(
            [
                variant["label"],
                num(stats["min_risk"], 2),
                num(stats["p5_risk"], 2),
                num(stats["median_risk"], 2),
                stats["below_initial_risk_count"],
                stats["near_initial_risk_count"],
                num(stats["min_close_distance"], 2),
                num(stats["p5_close_distance"], 2),
                stats["tiny_realised_count"],
                stats["spread_warning_count"],
                num(stats["max_spread_to_risk"], 2),
            ]
        )
        size_rows.append(
            [
                variant["label"],
                num(stats["min_size"], 2),
                num(stats["p5_size"], 2),
                num(stats["median_size"], 2),
                num(stats["max_size"], 2),
                money(stats["min_risk_amount"]),
                money(stats["median_risk_amount"]),
                money(stats["max_risk_amount"]),
            ]
        )

    validation_rows = []
    for variant in variants:
        validation_rows.append(
            [
                variant["label"],
                num(variant["walk_forward"]["lowest_test_profit_factor"], 2),
                pct(variant["walk_forward"]["max_test_drawdown_percent"]),
                pct(variant["stress"]["p5_return_percent"]),
                pct(variant["stress"]["worst_path_drawdown_percent"]),
                pct(variant["stress"]["worst_execution_return_percent"]),
                variant["stress"]["worst_execution_scenario"],
                link(variant["stability_report"], "stability"),
                link(variant["walk_forward_report"], "walk-forward"),
                link(variant["stress_report"], "stress"),
            ]
        )

    selected_bits = [
        ["strategy", final_contract["strategy"]["name"]],
        ["contract status", final_contract["strategy"]["status"]],
        ["direction mode in final contract", final_contract["strategy"]["direction_mode"]],
        ["selected guardrail", final_contract["broker_guardrails"]["selected_guardrail_candidate"]],
        ["minimum initial risk", f"{final_contract['broker_guardrails']['min_initial_risk_pips']} pips"],
        ["minimum stop/take-profit distance", f"{final_contract['broker_guardrails']['min_stop_distance_pips']} pips"],
        ["weekend policy", final_contract["weekend_policy"]["name"]],
        ["production ready", str(final_contract["strategy"]["production_ready"])],
        ["live trading approved", str(final_contract["strategy"]["live_trading_approved"])],
    ]

    reference_rows = [
        ["total return", pct(selected_summary.get("total_return_percent"))],
        ["ending balance", money(selected_summary.get("ending_balance"))],
        ["total trades", selected_summary.get("total_trades")],
        ["profit factor", num(selected_summary.get("profit_factor"), 2)],
        ["max drawdown", pct(selected_summary.get("max_drawdown_percent"))],
        ["average initial risk guardrail", "min_risk_3pips selected by human confirmation"],
    ]

    sensitive_sections = []
    for variant in variants:
        stats = variant["distance"]
        sensitive_sections.append(
            f"""
            <section>
              <h3>{html.escape(variant["label"])}: IG-Sensitive Trades</h3>
              <p class="small">Trades below 3 pips initial risk would violate the selected research guardrail. The realised open-to-close distance is diagnostic only; IG order rejection is normally tied to stop/limit distance at submission and amendment time.</p>
              <h4>Closest Initial Risk Trades</h4>
              {table(["Entry", "Exit", "Side", "Size", "Risk amount", "Initial risk pips", "Entry spread", "Open-close pips", "Hours", "PnL R", "Exit"], trade_rows(stats["near_initial_risk_trades"]), "dense")}
              <h4>Smallest Realised Open-Close Distance Trades</h4>
              {table(["Entry", "Exit", "Side", "Size", "Risk amount", "Initial risk pips", "Entry spread", "Open-close pips", "Hours", "PnL R", "Exit"], trade_rows(stats["tiny_realised_trades"]), "dense")}
              <h4>Worst Trades by R</h4>
              {table(["Entry", "Exit", "Side", "Size", "Risk amount", "Initial risk pips", "Entry spread", "Open-close pips", "Hours", "PnL R", "Exit"], trade_rows(stats["worst_trades"][:10]), "dense")}
            </section>
            """
        )

    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #172026; background: #f5f7f8; }
    header { padding: 32px 42px; background: #18212b; color: white; }
    main { max-width: 1480px; margin: 0 auto; padding: 28px 32px 52px; }
    section { background: white; border: 1px solid #dde4e8; border-radius: 8px; padding: 22px; margin: 18px 0; }
    h1 { margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }
    h2 { margin: 0 0 16px; font-size: 22px; }
    h3 { margin: 8px 0 12px; font-size: 18px; }
    h4 { margin: 20px 0 8px; font-size: 15px; }
    p { line-height: 1.48; }
    .small { color: #5a6872; font-size: 13px; }
    .callout { border-left: 4px solid #c07622; background: #fff7ed; padding: 12px 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
    table { border-collapse: collapse; width: 100%; font-size: 13px; }
    th, td { border-bottom: 1px solid #e6ecef; text-align: left; padding: 8px 9px; vertical-align: top; }
    th { background: #edf2f4; color: #26323a; font-weight: 650; }
    .dense { font-size: 12px; }
    .dense th, .dense td { padding: 6px 7px; }
    .scroll { overflow-x: auto; }
    a { color: #145ea8; text-decoration: none; }
    a:hover { text-decoration: underline; }
    """
    plotly_js = get_plotlyjs()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>USDJPY IG-Realistic Strategy Review</title>
  <script>{plotly_js}</script>
  <style>{css}</style>
</head>
<body>
  <header>
    <h1>USDJPY IG-Realistic Strategy Review</h1>
    <p>Generated {html.escape(generated_at)} from existing backtest and validation artifacts. No strategy config was changed.</p>
  </header>
  <main>
    <section class="callout">
      <strong>Important distinction:</strong> the frozen final research contract selects <code>min_risk_3pips</code>, <code>force_close_friday_20_30</code>, and <code>short_only</code>. The four July 11 validation runs reviewed here are IG-realistic long/short variants at swing/intraday holding modes and 0.25%/0.50% risk. This report is historical research evidence, not live-trading approval.
    </section>

    <section>
      <h2>Final Contract Snapshot</h2>
      <div class="grid">
        <div>{table(["Field", "Value"], selected_bits)}</div>
        <div>{table(["Reference selected baseline metric", "Value"], reference_rows)}</div>
      </div>
    </section>

    <section>
      <h2>Four Completed July 11 Runs</h2>
      <div class="scroll">{table(["Variant", "Trades", "Return", "Ending balance", "Max DD", "Profit factor", "Win rate", "Stability", "Walk-forward", "Stress"], overview_rows)}</div>
    </section>

    <section>
      <h2>Equity and Drawdown Time Series</h2>
      {equity_chart(variants)}
    </section>

    <section>
      <h2>Monthly Performance</h2>
      {monthly_chart(variants)}
    </section>

    <section>
      <h2>IG-Sensitive Distance Diagnostics</h2>
      <p class="small">USDJPY pip size is 0.01. The key selected guardrail is initial risk at or above 3 pips; 2 pips is shown as the IG stop/limit reference used by the research guardrail model.</p>
      {risk_distance_chart(variants)}
      <div class="scroll">{table(["Variant", "Min initial risk", "P5 initial risk", "Median initial risk", "<3 pip count", "<4 pip count", "Min open-close", "P5 open-close", "<2 pip open-close", "Spread/risk warnings", "Max spread/risk"], distance_rows)}</div>
      <h3>Trade Size and Risk Amount</h3>
      <p class="small">The <code>size</code> column is the backtester position-size exposure from the historical model. It is not yet an IG contract/deal-size conversion; the project README notes exact GBP/JPY pip-value conversion is outside this simplified research sizing model.</p>
      <div class="scroll">{table(["Variant", "Min size", "P5 size", "Median size", "Max size", "Min risk amount", "Median risk amount", "Max risk amount"], size_rows)}</div>
    </section>

    <section>
      <h2>Validation and Stress Summary</h2>
      {stress_chart(variants)}
      <div class="scroll">{table(["Variant", "Lowest WF PF", "Max WF DD", "MC p5 return", "Worst path DD", "Worst execution return", "Worst execution scenario", "Stability report", "WF report", "Stress report"], validation_rows, raw_columns={7, 8, 9})}</div>
    </section>

    {''.join(sensitive_sections)}
  </main>
</body>
</html>
"""


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build())
    print(OUTPUT)


if __name__ == "__main__":
    main()
