from datetime import datetime, timedelta, timezone

import polars as pl

from src.config.config_loader import resolve
from src.config.schemas import StrategyConfig
from src.data.candle_builder import build_and_save_all
from src.execution.tick_execution_engine import execute_signal
from src.indicators.indicator_engine import add_indicators
from src.reporting.csv_report import write_csv_reports, write_weekend_policy_reports
from src.reporting.html_report import write_html_report
from src.reporting.metrics import calculate_metrics
from src.risk.risk_manager import RiskManager
from src.strategies.fx_swing_trend_reclaim import generate_signals
from src.utils.logging import get_logger, timed_stage

logger = get_logger(__name__)


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
        entry = add_indicators(pl.read_parquet(candle_dir / "USDJPY_1H.parquet"))
        trend = add_indicators(pl.read_parquet(candle_dir / "USDJPY_4H.parquet"))
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
        trade = execute_signal(signal, execution_ticks, config, balance)
        if trade:
            trades.append(trade)
            balance += trade.net_pnl
            risk.record(trade.net_pnl, balance, trade.exit_timestamp_utc)
            active_until = trade.exit_timestamp_utc
    metrics = calculate_metrics(trades, config.risk["starting_balance"])
    run_name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1")
    output = output_override or (resolve(config, config.reporting["output_path"]) / run_name)
    with timed_stage(logger, "write backtest reports", output=output):
        write_csv_reports(output, trades, metrics, rejections)
        write_weekend_policy_reports(output, trades, rejections, config.weekend_policy)
        write_html_report(output, metrics)
    logger.info("Backtest complete | trades=%s, ending_balance=%.2f, reports=%s", len(trades), metrics["ending_balance"], output)
    return trades, metrics, output
