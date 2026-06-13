import csv
import html
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.backtest.backtest_engine import run_backtest
from src.config.config_loader import load_strategy_config
from src.utils.logging import get_logger, timed_stage

logger = get_logger(__name__)


def deep_merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        result[key] = deep_merge(result.get(key, {}), value) if isinstance(value, dict) else value
    return result


def score_variant(row: dict) -> tuple[float, str]:
    score = (
        row["total_return_percent"] - row["max_drawdown_percent"] * 2
        - max(0, abs(row["worst_trade_r"]) - 2.5) * 5
        - row["trades_loss_beyond_2_5r_count"] * 5
        - row["trades_loss_beyond_5r_count"] * 15
        + row["profit_factor"] * 5 + row["average_r"] * 10
    )
    if row["worst_trade_r"] < -5 or row["trades_loss_beyond_5r_count"] > 0:
        verdict = "REJECT"
    elif row["worst_trade_r"] < -2.5:
        verdict = "CAUTION"
    elif row["worst_trade_r"] >= -2 and row["profit_factor"] >= 1.5 and row["total_return_percent"] > 20 and row["max_drawdown_percent"] < 10:
        verdict = "STRONG_PASS"
    elif row["profit_factor"] >= 1.3 and row["total_return_percent"] > 0:
        verdict = "PASS"
    else:
        verdict = "CAUTION"
    return round(score, 4), verdict


class WeekendPolicyVariantRunner:
    def __init__(self, strategy_config, variants_config, normalised_tick_path, candle_path, report_output_path):
        self.strategy_path = Path(strategy_config)
        self.variants_path = Path(variants_config)
        self.tick_path = str(Path(normalised_tick_path).resolve())
        self.candle_path = str(Path(candle_path).resolve())
        self.report_parent = Path(report_output_path).resolve()

    def run_all_variants(self) -> Path:
        variants = yaml.safe_load(self.variants_path.read_text())["variants"]
        root = self.report_parent / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1")
        root.mkdir(parents=True, exist_ok=True)
        rows = []
        for index, variant in enumerate(variants, 1):
            logger.info("Weekend variant %s/%s | name=%s", index, len(variants), variant["name"])
            config = load_strategy_config(self.strategy_path)
            config.data["normalised_tick_path"] = self.tick_path
            config.data["candle_path"] = self.candle_path
            config.weekend_policy = deep_merge(config.weekend_policy, variant["weekend_policy"])
            config.weekend_policy["policy_name"] = variant["name"]
            output = root / variant["name"]
            with timed_stage(logger, "run weekend variant", variant=variant["name"]):
                trades, metrics, _ = run_backtest(config, output_override=output)
            weekend = next(csv.DictReader((output / "weekend_policy_summary.csv").open()))
            row = {
                "variant_name": variant["name"], "description": variant["description"], **metrics,
                "trades_loss_beyond_2_5r_count": sum(t.pnl_r < -2.5 for t in trades),
                "trades_loss_beyond_5r_count": sum(t.pnl_r < -5 for t in trades),
                "weekend_held_trade_count": int(weekend["weekend_held_trades"]),
                "weekend_held_loss_count": int(weekend["weekend_held_losses"]),
                "weekend_force_close_count": int(weekend["weekend_force_closes"]),
                "weekend_partial_reduce_count": int(weekend["weekend_partial_reductions"]),
                "weekend_stop_tighten_count": int(weekend["weekend_stop_tightens"]),
                "friday_cutoff_signal_rejection_count": int(weekend["friday_cutoff_signal_rejections"]),
                "sunday_open_signal_rejection_count": int(weekend["sunday_open_signal_rejections"]),
                "average_trade_duration_days": metrics["average_trade_duration"] / 24,
                "median_trade_duration_days": metrics["median_trade_duration"] / 24,
            }
            row["score"], row["verdict"] = score_variant(row)
            rows.append(row)
        self._write_comparison(root, rows)
        return root

    def _write_comparison(self, root: Path, rows: list[dict]) -> None:
        fields = list(rows[0])
        with (root / "weekend_policy_comparison.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        (root / "weekend_policy_comparison.json").write_text(json.dumps(rows, indent=2))
        ranked = sorted(rows, key=lambda row: row["score"], reverse=True)
        baseline = next(row for row in rows if row["variant_name"] == "baseline_allow_weekend")
        safest = max(rows, key=lambda row: row["worst_trade_r"])
        highest = max(rows, key=lambda row: row["total_return_percent"])
        table = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(row[key]))}</td>" for key in (
                "variant_name", "total_return_percent", "profit_factor", "max_drawdown_percent",
                "worst_trade_r", "weekend_held_trade_count", "score", "verdict",
            )) + "</tr>" for row in ranked
        )
        (root / "weekend_policy_comparison.html").write_text(
            "<html><body><h1>FX-2B Weekend Policy Comparison</h1>"
            f"<p>Baseline: {baseline['variant_name']}; safest: {safest['variant_name']}; "
            f"highest return: {highest['variant_name']}; best safety-adjusted score: {ranked[0]['variant_name']}.</p>"
            f"<p>Did policy remove -14.77R loss? {'Yes' if safest['worst_trade_r'] > -5 else 'No'}.</p>"
            "<table border='1'><tr><th>Variant</th><th>Return %</th><th>PF</th><th>Max DD %</th>"
            "<th>Worst R</th><th>Weekend Held</th><th>Score</th><th>Verdict</th></tr>"
            f"{table}</table><p>Scoring ranks return after drawdown and tail-risk penalties. Research only.</p></body></html>"
        )
