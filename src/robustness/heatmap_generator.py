from pathlib import Path

import plotly.express as px
import polars as pl


def generate_heatmaps(output: Path, pair_name: str, rows: list[dict]) -> list[Path]:
    heatmaps = output / "heatmaps"
    heatmaps.mkdir(parents=True, exist_ok=True)
    frame = pl.DataFrame(rows)
    if not frame.height:
        return []
    paths = []
    for metric in ("total_return_percent", "profit_factor", "average_r", "max_drawdown_percent", "pass_flag"):
        pivot = frame.pivot(on="value_x", index="value_y", values=metric, aggregate_function="first")
        x = [column for column in pivot.columns if column != "value_y"]
        z = pivot.select(x).to_numpy()
        figure = px.imshow(z, x=x, y=pivot["value_y"].to_list(), text_auto=True,
                           title=f"{pair_name}: {metric}", aspect="auto")
        path = heatmaps / f"{pair_name}_{metric}.html"
        figure.write_html(path)
        paths.append(path)
    return paths
