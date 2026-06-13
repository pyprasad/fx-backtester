import html
from pathlib import Path

import polars as pl


def _table(frame: pl.DataFrame, columns: list[str] | None = None) -> str:
    if not frame.height:
        return "<p>No data available.</p>"
    columns = [column for column in (columns or frame.columns) if column in frame.columns]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row[column]))}</td>" for column in columns) + "</tr>"
        for row in frame.select(columns).to_dicts()
    )
    return f"<table border='1'><tr>{header}</tr>{rows}</table>"


def write_stability_report(
    output: Path,
    strategy_name: str,
    market: str,
    policy_name: str,
    summary: dict,
    score: dict,
    yearly: pl.DataFrame,
    monthly: pl.DataFrame,
    quarterly: pl.DataFrame,
    rolling: dict[str, pl.DataFrame],
    concentration: dict,
    concentration_frames: dict[str, pl.DataFrame],
    regime_frames: dict[str, pl.DataFrame],
) -> Path:
    all_years = bool(yearly.height and yearly["positive_year_flag"].all())
    positive_months = score["positive_months_percent"]
    top_regime = (
        regime_frames["regime_performance.csv"].sort("net_profit", descending=True).row(0, named=True)
        if regime_frames["regime_performance.csv"].height else {}
    )
    dangerous = (
        regime_frames["regime_performance.csv"].sort("average_r").row(0, named=True)
        if regime_frames["regime_performance.csv"].height else {}
    )
    def regime_result(frame_name: str, regime_name: str) -> str:
        frame = regime_frames.get(frame_name, pl.DataFrame())
        match = frame.filter(pl.col("regime_name") == regime_name) if frame.height else frame
        if not match.height:
            return "not observed"
        row = match.row(0, named=True)
        return f"net profit {row['net_profit']}, average R {row['average_r']}, verdict {row['verdict']}"

    proceed = score["verdict"] in {"STRONG_STABILITY", "PASS"}
    warnings = []
    if not all_years:
        warnings.append("At least one tested year was not profitable.")
    if positive_months < 50:
        warnings.append("Fewer than half of active months were profitable.")
    if concentration["verdict"] != "PASS":
        warnings.append("Profit concentration requires review.")
    if not warnings:
        warnings.append("No configured stability threshold warnings were triggered.")
    rolling_tables = "".join(f"<h3>{name}</h3>{_table(frame)}" for name, frame in rolling.items())
    report = output / "stability_report.html"
    report.write_text(
        "<html><head><title>FX-2C Stability Validation</title></head><body>"
        "<h1>FX-2C Yearly, Monthly, and Regime Stability Validation</h1>"
        f"<p><b>Strategy:</b> {html.escape(strategy_name)} | <b>Market:</b> {html.escape(market)} | "
        f"<b>Weekend policy:</b> {html.escape(policy_name)}</p>"
        f"<h2>Executive Summary</h2><p>Stability score: <b>{score['stability_score']}</b>; "
        f"verdict: <b>{score['verdict']}</b>. Stable enough to proceed to walk-forward validation: "
        f"<b>{'YES' if proceed else 'NO'}</b>.</p>"
        f"<p>Every year profitable: <b>{'YES' if all_years else 'NO'}</b>. "
        f"Profitable active months: <b>{positive_months:.2f}%</b>. "
        f"Top-three-month contribution: <b>{concentration['top_3_month_profit_contribution_percent']:.2f}%</b>. "
        f"Top-ten-trade contribution: <b>{concentration['top_10_trade_profit_contribution_percent']:.2f}%</b>.</p>"
        f"<p>Most profitable regime: <b>{html.escape(str(top_regime.get('regime_name', 'unknown')))}</b>. "
        f"Most dangerous regime by average R: <b>{html.escape(str(dangerous.get('regime_name', 'unknown')))}</b>.</p>"
        f"<p>High volatility: <b>{html.escape(regime_result('volatility_regime_performance.csv', 'high'))}</b>. "
        f"Strong USDJPY uptrend: <b>{html.escape(regime_result('trend_regime_performance.csv', 'strong_uptrend'))}</b>. "
        f"USDJPY downtrend: <b>{html.escape(regime_result('trend_regime_performance.csv', 'strong_downtrend'))}</b>.</p>"
        f"<h2>Overall Strategy Summary</h2>{_table(pl.DataFrame([summary]))}"
        f"<h2>Yearly Performance</h2>{_table(yearly)}"
        f"<h2>Monthly Heatmap Data</h2>{_table(monthly, ['year_month', 'net_profit', 'return_percent', 'profit_factor', 'verdict'])}"
        f"<h2>Quarterly Performance</h2>{_table(quarterly)}"
        f"<h2>Rolling Windows</h2>{rolling_tables}"
        f"<h2>Profit Concentration</h2>{_table(pl.DataFrame([concentration]))}"
        f"<h3>Top Profit Months</h3>{_table(concentration_frames['top_profit_months.csv'])}"
        f"<h3>Top Loss Months</h3>{_table(concentration_frames['top_loss_months.csv'])}"
        f"<h3>Top Winning Trades</h3>{_table(concentration_frames['top_winning_trades.csv'])}"
        f"<h3>Top Losing Trades</h3>{_table(concentration_frames['top_losing_trades.csv'])}"
        f"<h2>Volatility Regimes</h2>{_table(regime_frames['volatility_regime_performance.csv'])}"
        f"<h2>Trend Regimes</h2>{_table(regime_frames['trend_regime_performance.csv'])}"
        f"<h2>Price Location Regimes</h2>{_table(regime_frames['price_location_regime_performance.csv'])}"
        f"<h2>Session Performance</h2>{_table(regime_frames.get('session_regime_performance.csv', pl.DataFrame()))}"
        "<h2>Key Warnings</h2><ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in warnings) + "</ul>"
        f"<h2>Recommended Next Action</h2><p>{'Proceed to walk-forward validation.' if proceed else 'Investigate stability warnings before walk-forward validation.'}</p>"
        "<p>This is historical research only. It is not evidence of production readiness.</p></body></html>"
    )
    return report
