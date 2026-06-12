import argparse
import json

import polars as pl

from src.backtest.backtest_engine import build_candles_for_config, run_backtest
from src.config.config_loader import (
    apply_data_quality_overrides,
    apply_strategy_overrides,
    load_data_quality_config,
    load_strategy_config,
    resolve,
)
from src.data.data_quality import analyze_data_quality, write_quality_reports
from src.data.tick_loader import scan_ticks
from src.data.tick_normalizer import normalize_ticks
from src.utils.logging import configure_logging, get_logger, timed_stage

logger = get_logger(__name__)


def quality(config, ticks=None):
    ticks = ticks if ticks is not None else scan_ticks(
            resolve(config, config.input["raw_tick_path"]),
            config.input["file_pattern"],
            config.market.symbol,
            sort=False,
        )
    with timed_stage(logger, "analyze data quality"):
        report = analyze_data_quality(ticks, config)
    with timed_stage(logger, "write data-quality reports"):
        write_quality_reports(report, ticks, config)
    logger.info(
        "Data quality complete | status=%s, ticks=%s, warnings=%s, extreme_spreads=%s",
        report.status,
        f"{report.total_ticks:,}",
        report.warning_spread_count,
        report.extreme_spread_count,
    )
    print(json.dumps(report.__dict__, default=str, indent=2))


def add_data_overrides(parser):
    parser.add_argument("--raw-tick-path", help="Override input.raw_tick_path; absolute paths are supported")
    parser.add_argument("--file-pattern", help="Override input.file_pattern, for example usdjpy_ticks_202[2-5].csv")
    parser.add_argument("--normalised-output-path", help="Override normalized Parquet output path")
    parser.add_argument("--quality-report-path", help="Override data-quality HTML report path")
    parser.add_argument("--quality-summary-path", help="Override data-quality summary CSV path")


def add_strategy_overrides(parser):
    parser.add_argument("--normalised-tick-path", help="Override strategy normalized Parquet input")
    parser.add_argument("--candle-path", help="Override candle output/input directory")
    parser.add_argument("--report-output-path", help="Override backtest report parent directory")


def data_config(args, path):
    return apply_data_quality_overrides(
        load_data_quality_config(path),
        raw_tick_path=getattr(args, "raw_tick_path", None),
        file_pattern=getattr(args, "file_pattern", None),
        normalised_output_path=getattr(args, "normalised_output_path", None),
        quality_report_path=getattr(args, "quality_report_path", None),
        quality_summary_path=getattr(args, "quality_summary_path", None),
    )


def strategy_config(args, path):
    return apply_strategy_overrides(
        load_strategy_config(path),
        normalised_tick_path=getattr(args, "normalised_tick_path", None),
        candle_path=getattr(args, "candle_path", None),
        report_output_path=getattr(args, "report_output_path", None),
    )


def main():
    parser = argparse.ArgumentParser(description="USDJPY research backtester")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("data-quality", "normalise", "build-candles", "backtest"):
        command = sub.add_parser(name)
        command.add_argument("--config", required=True)
        if name in ("data-quality", "normalise"):
            add_data_overrides(command)
        if name in ("build-candles", "backtest"):
            add_strategy_overrides(command)
        if name == "normalise":
            command.add_argument("--overwrite", action="store_true")
    all_parser = sub.add_parser("all")
    all_parser.add_argument("--data-quality-config", required=True)
    all_parser.add_argument("--strategy-config", required=True)
    all_parser.add_argument("--overwrite", action="store_true")
    add_data_overrides(all_parser)
    add_strategy_overrides(all_parser)
    args = parser.parse_args()
    configure_logging(args.log_level)
    logger.info("Pipeline command started | command=%s", args.command)
    if args.command == "data-quality":
        quality(data_config(args, args.config))
    elif args.command == "normalise":
        _, summary = normalize_ticks(data_config(args, args.config), args.overwrite)
        print(json.dumps(summary, default=str, indent=2))
    elif args.command == "build-candles":
        frames = build_candles_for_config(strategy_config(args, args.config))
        print({name: frame.height for name, frame in frames.items()})
    elif args.command == "backtest":
        _, metrics, output = run_backtest(strategy_config(args, args.config))
        print(json.dumps(metrics, default=str, indent=2))
        print(f"Reports: {output}")
    else:
        data = data_config(args, args.data_quality_config)
        logger.info("ALL stage 1/4 | normalize ticks")
        normalize_ticks(data, args.overwrite)
        logger.info("ALL stage 2/4 | data quality")
        quality(data, pl.scan_parquet(resolve(data, data.input["normalised_output_path"])))
        if args.normalised_output_path and not args.normalised_tick_path:
            args.normalised_tick_path = args.normalised_output_path
        strategy = strategy_config(args, args.strategy_config)
        logger.info("ALL stage 3/4 | build candles")
        build_candles_for_config(strategy)
        logger.info("ALL stage 4/4 | run backtest")
        _, metrics, output = run_backtest(strategy)
        print(json.dumps(metrics, default=str, indent=2))
        print(f"Reports: {output}")
    logger.info("Pipeline command completed | command=%s", args.command)


if __name__ == "__main__":
    main()
