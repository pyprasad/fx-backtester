import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src.config.config_loader import load_strategy_config
from src.utils.logging import get_logger, timed_stage

from .concentration_analysis import concentration_analysis
from .period_analysis import monthly_analysis, quarterly_analysis, yearly_analysis
from .regime_analysis import regime_analysis
from .regime_classifier import classify_regimes
from .rolling_analysis import rolling_analysis
from .stability_report import write_stability_report
from .stability_score import calculate_stability_score

logger = get_logger(__name__)


class StabilityValidationRunner:
    def __init__(self, strategy_config_path, run_path, candle_path, report_output_path, baseline_policy_name=None):
        self.config = load_strategy_config(strategy_config_path)
        self.run_path = Path(run_path).resolve()
        self.candle_path = Path(candle_path).resolve()
        self.report_parent = Path(report_output_path).resolve()
        configured = self.config.stability_validation.get("baseline_policy_name", "force_close_friday_20_30")
        self.policy_name = baseline_policy_name or configured
        self.output = self.report_parent / datetime.now(timezone.utc).strftime(
            f"%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1_{self.policy_name}"
        )

    def load_trade_log(self) -> pl.DataFrame:
        path = self.run_path / "trade_log.csv"
        if not path.exists():
            raise FileNotFoundError(f"Required stability input is missing: {path}")
        logger.info("Load trades | path=%s", path)
        return pl.read_csv(path, try_parse_dates=True)

    def load_equity_curve(self) -> pl.DataFrame:
        path = self.run_path / "equity_curve.csv"
        if not path.exists():
            raise FileNotFoundError(f"Required stability input is missing: {path}")
        logger.info("Load equity curve | path=%s", path)
        return pl.read_csv(path, try_parse_dates=True)

    def load_candles(self) -> pl.DataFrame:
        path = self.candle_path / "USDJPY_1D.parquet" if self.candle_path.is_dir() else self.candle_path
        if not path.exists():
            raise FileNotFoundError(f"Required daily candle input is missing: {path}")
        logger.info("Load daily candles | path=%s", path)
        return pl.read_parquet(path)

    def run_period_analysis(self, trades: pl.DataFrame, starting_balance: float) -> dict[str, pl.DataFrame]:
        return {
            "yearly_stability.csv": yearly_analysis(trades, starting_balance),
            "monthly_stability.csv": monthly_analysis(trades, starting_balance),
            "quarterly_stability.csv": quarterly_analysis(trades, starting_balance),
        }

    def run_regime_analysis(
        self, trades: pl.DataFrame, candles: pl.DataFrame, starting_balance: float
    ) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
        labels = classify_regimes(candles, self.config.stability_validation.get("regime_analysis", {}))
        return labels, regime_analysis(trades, labels, starting_balance)

    def run_concentration_analysis(self, trades: pl.DataFrame) -> tuple[dict, dict[str, pl.DataFrame]]:
        return concentration_analysis(trades)

    def run_rolling_analysis(self, trades: pl.DataFrame, starting_balance: float) -> dict[str, pl.DataFrame]:
        frames = {}
        for window in self.config.stability_validation.get("rolling_windows", {}).get("windows", []):
            frames[window["name"]] = rolling_analysis(
                trades, starting_balance, int(window["months"]), window["name"]
            )
        return frames

    def calculate_stability_score(
        self, summary, yearly, monthly, rolling_6_month, concentration, regimes
    ) -> dict:
        return calculate_stability_score(
            summary, yearly, monthly, rolling_6_month, concentration, regimes
        )

    def export_reports(self, frames: dict[str, pl.DataFrame]) -> None:
        for name, frame in frames.items():
            frame.write_csv(self.output / name)

    def run(self) -> Path:
        logger.info("Start stability validation | run=%s, policy=%s", self.run_path, self.policy_name)
        self.output.mkdir(parents=True, exist_ok=True)
        trades = self.load_trade_log()
        self.load_equity_curve()
        candles = self.load_candles()
        summary_path = self.run_path / "strategy_summary.csv"
        if not summary_path.exists():
            raise FileNotFoundError(f"Required stability input is missing: {summary_path}")
        summary = pl.read_csv(summary_path).row(0, named=True)
        starting_balance = float(summary["starting_balance"])

        with timed_stage(logger, "period analysis"):
            period_frames = self.run_period_analysis(trades, starting_balance)
            self.export_reports(period_frames)
            yearly = period_frames["yearly_stability.csv"]
            monthly = period_frames["monthly_stability.csv"]
            quarterly = period_frames["quarterly_stability.csv"]
        logger.info("Period analysis complete")

        with timed_stage(logger, "regime classification"):
            labels, regime_frames = self.run_regime_analysis(trades, candles, starting_balance)
            labels.write_csv(self.output / "regime_daily_labels.csv")
            self.export_reports(regime_frames)
        logger.info("Regime classification complete")

        with timed_stage(logger, "concentration analysis"):
            concentration, concentration_frames = self.run_concentration_analysis(trades)
            pl.DataFrame([concentration]).write_csv(self.output / "concentration_summary.csv")
            self.export_reports(concentration_frames)
        logger.info("Concentration analysis complete")

        rolling_frames = {}
        with timed_stage(logger, "rolling analysis"):
            rolling_frames = self.run_rolling_analysis(trades, starting_balance)
            for name, frame in rolling_frames.items():
                frame.write_csv(self.output / f"{name}_stability.csv")
        logger.info("Rolling analysis complete")

        rolling6 = rolling_frames.get("rolling_6_month", pl.DataFrame())
        score = self.calculate_stability_score(
            summary, yearly, monthly, rolling6, concentration, regime_frames["regime_performance.csv"]
        )
        flat_score = {key: value for key, value in score.items() if not isinstance(value, dict)}
        pl.DataFrame([flat_score]).write_csv(self.output / "stability_score.csv")
        (self.output / "stability_score.json").write_text(json.dumps(score, indent=2))
        stability_summary = {
            "strategy_name": self.config.strategy["name"], "market": self.config.strategy["market"],
            "baseline_policy_name": self.policy_name, **summary, **flat_score,
        }
        pl.DataFrame([stability_summary]).write_csv(self.output / "stability_summary.csv")
        (self.output / "stability_summary.json").write_text(json.dumps(stability_summary, indent=2))
        report = write_stability_report(
            self.output, self.config.strategy["name"], self.config.strategy["market"], self.policy_name,
            summary, score, yearly, monthly, quarterly, rolling_frames, concentration,
            concentration_frames, regime_frames,
        )
        (self.run_path / "stability_report_link.txt").write_text(str(report))
        logger.info("Stability report written | path=%s", report)
        return self.output
