from pathlib import Path

import plotly.express as px
import polars as pl


def generate_charts(output: Path, distribution: list[dict], samples: list[dict], scenarios: list[dict]) -> list[Path]:
    folder = output / "charts"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    frame = pl.DataFrame(distribution)
    for metric in ("total_return_percent", "max_drawdown_percent", "profit_factor"):
        path = folder / f"{metric}_distribution.html"
        px.histogram(frame, x=metric, title=metric.replace("_", " ").title()).write_html(path)
        paths.append(path)
    if scenarios:
        path = folder / "scenario_comparison.html"
        px.bar(pl.DataFrame(scenarios), x="scenario_name", y="median_return_percent",
               title="Scenario Median Return").write_html(path)
        paths.append(path)
    if samples:
        path = folder / "sample_equity_paths.html"
        px.line(pl.DataFrame(samples), x="trade_index", y="equity", color="path_id",
                title="Monte Carlo Sample Equity Paths").write_html(path)
        paths.append(path)
    return paths
