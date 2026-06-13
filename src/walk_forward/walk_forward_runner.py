import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import polars as pl

from src.config.config_loader import load_strategy_config
from src.stability.period_analysis import prepare_trades
from src.utils.logging import get_logger, timed_stage

from .anchored_walk_forward import analyze_windows
from .rolling_walk_forward import analyze_rolling
from .walk_forward_report import write_walk_forward_report
from .walk_forward_score import calculate_walk_forward_score
from .window_backtest import WindowBacktestRunner
from .window_builder import build_anchored_windows, build_rolling_windows, validate_windows

logger = get_logger(__name__)


class WalkForwardValidationRunner:
    def __init__(self, strategy_config_path, run_path, candle_path, report_output_path):
        self.config = load_strategy_config(strategy_config_path)
        self.settings = self.config.walk_forward_validation
        self.run_path = Path(run_path).resolve()
        self.candle_path = Path(candle_path).resolve()
        policy = self.settings.get("baseline_policy_name", "force_close_friday_20_30")
        self.output = Path(report_output_path).resolve() / datetime.now(timezone.utc).strftime(
            f"%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1_{policy}"
        )

    def _load(self) -> tuple[pl.DataFrame, dict]:
        required = [self.run_path / name for name in ("trade_log.csv", "strategy_summary.csv")]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Required walk-forward baseline outputs are missing: {', '.join(missing)}")
        equity_path = self.run_path / "equity_curve.csv"
        if equity_path.exists():
            logger.info(
                "Equity curve available | path=%s; strict entry-window drawdown uses selected trades",
                equity_path,
            )
        else:
            logger.warning("Equity curve unavailable; drawdown will be reconstructed from trade exits")
        policy_path = self.run_path / "weekend_policy_summary.csv"
        if policy_path.exists():
            policy = pl.read_csv(policy_path).row(0, named=True).get("policy_name")
            expected = self.settings.get("baseline_policy_name")
            if policy != expected:
                raise ValueError(f"Walk-forward requires weekend policy {expected}, but run uses {policy}")
        trades = prepare_trades(pl.read_csv(required[0], try_parse_dates=True))
        return trades, pl.read_csv(required[1]).row(0, named=True)

    def run(self) -> Path:
        logger.info("Start walk-forward validation | run=%s", self.run_path)
        self.output.mkdir(parents=True, exist_ok=True)
        trades, baseline = self._load()
        daily_path = self.candle_path / "USDJPY_1D.parquet" if self.candle_path.is_dir() else self.candle_path
        if daily_path.exists():
            daily = pl.read_parquet(daily_path, columns=["timestamp"])
            available_start, available_end = daily["timestamp"].min(), daily["timestamp"].max()
        else:
            logger.warning("Daily candles unavailable; using first/last trade for rolling data range")
            available_start, available_end = trades["entry_timestamp_utc"].min(), trades["entry_timestamp_utc"].max()
        anchored_windows = build_anchored_windows(self.settings["anchored_windows"])
        rolling_windows = build_rolling_windows(self.settings["rolling_windows"], available_start, available_end)
        errors = validate_windows(anchored_windows) + validate_windows(
            rolling_windows, available_start, available_end
        )
        if errors:
            raise ValueError("Invalid walk-forward windows: " + "; ".join(errors))
        runner = WindowBacktestRunner(trades, float(baseline["starting_balance"]), self.settings["minimums"])
        with timed_stage(logger, "anchored walk-forward analysis"):
            anchored = analyze_windows(anchored_windows, runner)
            anchored.write_csv(self.output / "anchored_walk_forward.csv")
        with timed_stage(logger, "rolling walk-forward analysis"):
            rolling_details, rolling_summary = analyze_rolling(rolling_windows, runner)
            for name, frame in rolling_details.items():
                frame.write_csv(self.output / f"rolling_wf_{name}.csv")
            rolling_summary.write_csv(self.output / "rolling_walk_forward_summary.csv")
        all_rolling = pl.concat(list(rolling_details.values()), how="diagonal_relaxed")
        score = calculate_walk_forward_score(anchored, all_rolling, rolling_summary)
        flat_score = {key: value for key, value in score.items() if not isinstance(value, dict)}
        pl.DataFrame([flat_score]).write_csv(self.output / "walk_forward_score.csv")
        (self.output / "walk_forward_score.json").write_text(json.dumps(score, indent=2))
        all_tests = pl.concat([anchored, all_rolling], how="diagonal_relaxed")
        summary = {
            "strategy_name": self.settings["strategy_name"], "market": self.settings["market"],
            "weekend_policy_name": self.settings["baseline_policy_name"],
            "baseline_run_path": str(self.run_path), "total_anchored_windows": anchored.height,
            "anchored_positive_test_windows": int(anchored["test_positive_flag"].sum()),
            "anchored_positive_test_percent": round(anchored["test_positive_flag"].mean() * 100, 4),
            "total_rolling_windows": all_rolling.height,
            "rolling_positive_test_windows": int(all_rolling["test_positive_flag"].sum()),
            "rolling_positive_test_percent": round(all_rolling["test_positive_flag"].mean() * 100, 4),
            "average_test_profit_factor": round(float(all_tests["test_profit_factor"].mean()), 4),
            "median_test_profit_factor": round(median(all_tests["test_profit_factor"].to_list()), 4),
            "average_test_average_r": round(float(all_tests["test_average_r"].mean()), 4),
            "median_test_average_r": round(median(all_tests["test_average_r"].to_list()), 4),
            "worst_test_trade_r": float(all_tests["test_worst_trade_r"].min()),
            "max_test_drawdown_percent": float(all_tests["test_max_drawdown_percent"].max()),
            "lowest_test_profit_factor": float(all_tests["test_profit_factor"].min()),
            "walk_forward_score": score["walk_forward_score"], "final_verdict": score["verdict"],
        }
        pl.DataFrame([summary]).write_csv(self.output / "walk_forward_summary.csv")
        (self.output / "walk_forward_summary.json").write_text(json.dumps(summary, indent=2))
        report = write_walk_forward_report(
            self.output, summary, score, anchored, rolling_summary, rolling_details
        )
        (self.run_path / "walk_forward_report_link.txt").write_text(str(report))
        logger.info("Walk-forward report written | path=%s", report)
        return self.output
