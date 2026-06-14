from datetime import datetime, timedelta, timezone

import polars as pl

from src.config.config_loader import resolve
from src.config.schemas import StrategyConfig
from src.data.candle_builder import build_and_save_all
from src.execution.tick_execution_engine import evaluate_executable_entry_guardrail, execute_signal
from src.indicators.indicator_engine import add_indicators
from src.reporting.csv_report import (
    write_csv_reports,
    write_funding_reports,
    write_strategy_summary,
    write_weekend_policy_reports,
)
from src.reporting.html_report import write_html_report
from src.reporting.metrics import calculate_metrics
from src.reporting.fixed_stake_comparison import write_fixed_stake_comparison
from src.validation.fixed_stake_baseline_validator import (
    validate_fixed_stake_baseline,
    write_validation_report,
)
from src.validation.weekend_exposure_audit import (
    weekend_exposure_audit,
    write_weekend_exposure_audit,
)
from src.risk.risk_manager import RiskManager
from src.strategies.fx_swing_trend_reclaim import generate_signals
from src.utils.logging import get_logger, timed_stage

logger = get_logger(__name__)


def _execution_guardrail_rejections(signal, decision) -> list[dict]:
    groups = {
        "REJECT_BELOW_BROKER_MIN_STOP_DISTANCE": "BROKER_DISTANCE",
        "REJECT_BELOW_BROKER_MIN_TP_DISTANCE": "BROKER_DISTANCE",
        "REJECT_BELOW_MIN_INITIAL_RISK_PIPS": "MIN_RISK",
        "REJECT_ENTRY_SPREAD_ABOVE_MAX": "SPREAD_RISK",
        "REJECT_SPREAD_TO_RISK_RATIO_TOO_HIGH": "SPREAD_RISK",
        "REJECT_AFTER_FUNDING_ENTRY_CUTOFF": "FUNDING_TIME_GUARD",
    }
    return [{
        "timestamp": decision.timestamp_utc, "timestamp_utc": decision.timestamp_utc,
        "rejection_reason": reason, "reason": reason, "rejection_group": groups[reason],
        "guardrail_stage": "executable_entry",
        "initial_risk_pips": decision.initial_risk_pips,
        "entry_spread_pips": decision.entry_spread_pips,
        "spread_to_risk_ratio": decision.spread_to_risk_ratio,
        "min_required_stop_distance_pips": decision.min_stop_distance_pips,
        "timestamp_london": decision.timestamp_local, "hour_london": decision.timestamp_local.hour,
        "day_of_week_london": decision.timestamp_local.strftime("%A"), "session_label": signal.session,
        "warnings": "|".join(decision.warnings),
    } for reason in decision.rejection_reasons]


def build_candles_for_config(config: StrategyConfig) -> dict[str, pl.DataFrame]:
    tick_path = resolve(config, config.data["normalised_tick_path"])
    logger.info("Building candles | tick_path=%s, output=%s", tick_path, resolve(config, config.data["candle_path"]))
    ticks = pl.scan_parquet(tick_path)
    return build_and_save_all(ticks, resolve(config, config.data["candle_path"]), config.candles["build_timeframes"])


def run_backtest(config: StrategyConfig, output_override=None) -> tuple[list, dict, object]:
    tick_path = resolve(config, config.data["normalised_tick_path"])
    candle_dir = resolve(config, config.data["candle_path"])
    if not (candle_dir / "USDJPY_1H.parquet").exists():
        build_candles_for_config(config)
    with timed_stage(logger, "load candles and calculate indicators"):
        entry = add_indicators(pl.read_parquet(candle_dir / "USDJPY_1H.parquet"), parameters=config.indicators)
        trend = add_indicators(pl.read_parquet(candle_dir / "USDJPY_4H.parquet"), parameters=config.indicators)
    with timed_stage(logger, "generate strategy signals"):
        signals, rejections = generate_signals(entry, trend, config)
    logger.info("Signals generated | accepted=%s, rejected=%s", f"{len(signals):,}", f"{len(rejections):,}")
    balance, active_until, trades = config.risk["starting_balance"], None, []
    risk = RiskManager(
        balance, config.risk["max_open_trades_total"], config.risk["max_open_trades_per_market"],
        config.risk["max_daily_loss_percent"], config.risk["max_weekly_loss_percent"],
        config.risk["max_strategy_drawdown_percent"],
    )
    total_signals = len(signals)
    for index, signal in enumerate(signals, start=1):
        if index == 1 or index % 25 == 0 or index == total_signals:
            logger.info(
                "Execution progress | signal=%s/%s, trades=%s, balance=%.2f",
                index, total_signals, len(trades), balance,
            )
        if active_until and signal.timestamp_utc < active_until:
            rejections.append({"timestamp": signal.timestamp_utc, "reason": "max_open_trades"})
            continue
        risk.roll_periods(signal.timestamp_utc)
        allowed, reason = risk.can_open(signal.symbol, balance)
        if not allowed:
            rejections.append({"timestamp": signal.timestamp_utc, "reason": reason})
            continue
        execution_ticks = (
            pl.scan_parquet(tick_path)
            .filter(
                (pl.col("timestamp_utc") > signal.timestamp_utc)
                & (pl.col("timestamp_utc") <= signal.timestamp_utc + timedelta(days=config.max_trade_duration_days))
            )
            .collect(engine="streaming")
        )
        guardrail = evaluate_executable_entry_guardrail(signal, execution_ticks, config)
        if guardrail is not None and not guardrail.accepted:
            rejections.extend(_execution_guardrail_rejections(signal, guardrail))
            continue
        trade = execute_signal(signal, execution_ticks, config, balance)
        if trade:
            trades.append(trade)
            balance += trade.net_pnl
            risk.record(trade.net_pnl, balance, trade.exit_timestamp_utc)
            active_until = trade.exit_timestamp_utc
    metrics = calculate_metrics(trades, config.risk["starting_balance"])
    run_name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1")
    output = output_override or (resolve(config, config.reporting["output_path"]) / run_name)
    audit_rows = []
    if metrics.get("position_sizing_mode") == "fixed_spread_bet_stake":
        close_time = config.weekend_policy.get("force_close_on_friday", {}).get(
            "close_time_utc", "20:30"
        )
        audit_rows = weekend_exposure_audit(trades, close_time)
        metrics.update(validate_fixed_stake_baseline(config, trades, metrics, audit_rows))
    with timed_stage(logger, "write backtest reports", output=output):
        write_csv_reports(output, trades, metrics, rejections)
        if audit_rows:
            write_weekend_exposure_audit(output / "weekend_exposure_audit.csv", audit_rows)
            write_validation_report(output / "fixed_stake_validation.json", {
                key: metrics[key] for key in (
                    "validation_status", "validation_errors", "config_path", "config_hash",
                    "weekend_crossing_trade_count", "weekend_gap_risk_trade_count",
                    "old_weekend_gap_removed",
                )
            })
        write_weekend_policy_reports(output, trades, rejections, config.weekend_policy)
        write_funding_reports(output, trades, metrics, config.broker_execution_guardrails)
        write_html_report(output, metrics)
        comparison = config.reporting.get("comparison_baseline_run_path")
        comparison_output = config.reporting.get("comparison_output_stem")
        if metrics.get("position_sizing_mode") == "fixed_spread_bet_stake" and comparison and comparison_output:
            baseline_path = resolve(config, comparison)
            if baseline_path.exists():
                comparison_result = write_fixed_stake_comparison(
                    baseline_path, output, resolve(config, comparison_output)
                )
                validation_output = config.reporting.get("baseline_validation_output_stem")
                if validation_output:
                    write_fixed_stake_comparison(
                        baseline_path, output, resolve(config, validation_output)
                    )
                if not comparison_result["strategy_logic_matches"]:
                    metrics["validation_status"] = "FAILED_VALIDATION"
                    prior = metrics.get("validation_errors", "")
                    metrics["validation_errors"] = "|".join(
                        item for item in (prior, "BASELINE_STRATEGY_LOGIC_MISMATCH") if item
                    )
                    write_strategy_summary(output, metrics)
                    write_validation_report(output / "fixed_stake_validation.json", {
                        key: metrics[key] for key in (
                            "validation_status", "validation_errors", "config_path", "config_hash",
                            "weekend_crossing_trade_count", "weekend_gap_risk_trade_count",
                            "old_weekend_gap_removed",
                        )
                    })
                    logger.error(
                        "Fixed-stake baseline comparison failed | strategy_logic_matches=false"
                    )
            else:
                logger.warning("Fixed-stake baseline comparison skipped | missing=%s", baseline_path)
    if metrics.get("validation_status") == "FAILED_VALIDATION":
        logger.error("Fixed-stake baseline validation failed | errors=%s", metrics["validation_errors"])
    logger.info("Backtest complete | trades=%s, ending_balance=%.2f, reports=%s", len(trades), metrics["ending_balance"], output)
    return trades, metrics, output
