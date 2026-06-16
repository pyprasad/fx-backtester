import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.backtest.backtest_engine import run_backtest
from src.backtest.weekend_policy_runner import deep_merge
from src.config.config_loader import apply_weekend_policy_variant, load_strategy_config
from src.utils.logging import get_logger

from .guardrail_metrics import score_guardrail, trade_guardrail_stats
from .guardrail_report import write_guardrail_report

logger = get_logger(__name__)


def _read_one(path: Path) -> dict:
    with path.open() as handle:
        return next(csv.DictReader(handle))


def _read_all(path: Path) -> list[dict]:
    if not path.exists() or not path.read_text().strip():
        return []
    with path.open() as handle:
        return list(csv.DictReader(handle))


class BrokerGuardrailRunner:
    def __init__(self, strategy_config, variants_config, normalised_tick_path, candle_path,
                 report_output_path, daily_funding_pips=None, skip_funding=False,
                 variant=None, continue_on_error=True, session_timezone=None,
                 session_windows=None):
        self.strategy_path = Path(strategy_config)
        self.variants_path = Path(variants_config)
        self.tick_path = str(Path(normalised_tick_path).resolve())
        self.candle_path = str(Path(candle_path).resolve())
        self.report_parent = Path(report_output_path).resolve()
        self.daily_funding_pips = daily_funding_pips
        self.skip_funding = skip_funding
        self.selected_variant = variant
        self.continue_on_error = continue_on_error
        self.session_timezone = session_timezone
        self.session_windows = session_windows
        self.output = self.report_parent / datetime.now(timezone.utc).strftime(
            "%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1"
        )

    def _config(self, variant: dict):
        config = load_strategy_config(self.strategy_path)
        config.data["normalised_tick_path"], config.data["candle_path"] = self.tick_path, self.candle_path
        if self.session_timezone:
            config.session_filter["timezone"] = self.session_timezone
        if self.session_windows:
            config.session_filter["entry_windows"] = self.session_windows
        config.broker_execution_guardrails = deep_merge(
            config.broker_execution_guardrails, variant["broker_execution_guardrails"]
        )
        if self.daily_funding_pips is not None:
            config.broker_execution_guardrails["overnight_funding"]["default_daily_funding_pips"] = self.daily_funding_pips
        if self.skip_funding:
            config.broker_execution_guardrails["overnight_funding"]["default_daily_funding_pips"] = 0
        return apply_weekend_policy_variant(
            config, "force_close_friday_20_30", "config/weekend_policy_variants.usdjpy.yaml"
        )

    def _row(self, variant, config, trades, metrics, output) -> dict:
        rejections = _read_all(output / "signal_rejection_log.csv")
        funding = _read_one(output / "funding_summary.csv")
        stats = trade_guardrail_stats(trades, config.broker_execution_guardrails)
        def count(group):
            return sum(row.get("rejection_group") == group for row in rejections)

        row = {
            "variant_name": variant["name"], "description": variant["description"],
            "total_trades": len(trades), "accepted_signals": len(trades), "rejected_signals": len(rejections),
            "broker_distance_rejections": count("BROKER_DISTANCE"),
            "min_risk_rejections": count("MIN_RISK"), "spread_risk_rejections": count("SPREAD_RISK"),
            "funding_time_rejections": count("FUNDING_TIME_GUARD"),
            "return_percent_before_funding": metrics["total_return_percent"],
            "return_percent_after_funding": float(funding["return_after_funding"]),
            "profit_factor_before_funding": metrics["profit_factor"],
            "profit_factor_after_funding": float(funding["profit_factor_after_funding"]),
            "max_drawdown_percent": metrics["max_drawdown_percent"],
            "average_r_before_funding": metrics["average_r"],
            "average_r_after_funding": float(funding["average_r_after_funding"]),
            "worst_trade_r": metrics["worst_trade_r"],
            "worst_trade_r_after_funding": float(funding["worst_trade_r_after_funding"]),
            "overnight_trade_count": int(funding["trades_held_overnight"]),
            "funding_days": int(funding["total_funding_days"]),
            "wednesday_triple_rollover_count": int(funding["wednesday_triple_rollover_events"]),
            **stats,
        }
        row["score"], row["verdict"] = score_guardrail(row, config.broker_execution_guardrails)
        return row

    def run(self) -> Path:
        variants = yaml.safe_load(self.variants_path.read_text())["variants"]
        if self.selected_variant:
            variants = [item for item in variants if item["name"] == self.selected_variant]
            if not variants:
                raise ValueError(f"Unknown broker guardrail variant: {self.selected_variant}")
        self.output.mkdir(parents=True, exist_ok=True)
        rows = []
        for index, variant in enumerate(variants, 1):
            logger.info("Broker guardrail variant %s/%s | name=%s", index, len(variants), variant["name"])
            config, folder = self._config(variant), self.output / "variants" / variant["name"]
            try:
                trades, metrics, _ = run_backtest(config, output_override=folder)
                rows.append(self._row(variant, config, trades, metrics, folder))
            except Exception:
                logger.exception("Broker guardrail variant failed | name=%s", variant["name"])
                if not self.continue_on_error:
                    raise
        if not rows:
            raise RuntimeError("No broker guardrail variants completed successfully")
        fields = list(rows[0])
        with (self.output / "broker_guardrail_comparison.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        (self.output / "broker_guardrail_comparison.json").write_text(json.dumps(rows, indent=2))
        base = load_strategy_config(self.strategy_path).broker_execution_guardrails
        write_guardrail_report(self.output, rows, {
            "broker": base["broker"], "market": base["market"], "pip_size": base["pip_size"],
            "minimum_stop_distance_pips": base["broker_distance_rules"]["min_stop_distance_pips"],
            "overnight_cutoff": f"{base['overnight_funding']['cutoff_time']} {base['overnight_funding']['timezone']}",
            "daily_funding_pips": self.daily_funding_pips if self.daily_funding_pips is not None else base["overnight_funding"]["default_daily_funding_pips"],
        })
        return self.output
