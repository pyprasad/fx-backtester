import argparse
import json
from pathlib import Path

import polars as pl

from src.backtest.backtest_engine import build_candles_for_config, run_backtest
from src.backtest.weekend_policy_runner import WeekendPolicyVariantRunner
from src.bakeoff.candidate_runner import FinalGuardrailBakeOffRunner
from src.broker_guardrails.guardrail_runner import BrokerGuardrailRunner
from src.config.config_loader import (
    apply_data_quality_overrides,
    apply_strategy_overrides,
    apply_weekend_policy_variant,
    load_data_quality_config,
    load_strategy_config,
    resolve,
)
from src.data.data_quality import analyze_data_quality, write_quality_reports
from src.data.tick_loader import scan_ticks
from src.data.tick_normalizer import normalize_ticks
from src.forensics.trade_forensics import TradeForensicsEngine
from src.reporting.html_report import add_forensic_link
from src.robustness.robustness_runner import ParameterRobustnessRunner
from src.stability.stability_runner import StabilityValidationRunner
from src.stress.monte_carlo_runner import MonteCarloStressRunner
from src.utils.logging import configure_logging, get_logger, timed_stage
from src.walk_forward.walk_forward_runner import WalkForwardValidationRunner

logger = get_logger(__name__)


def boolean(value):
    if isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("Expected true or false")


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


def run_forensics(config, run_path, normalised_tick_path, candle_path):
    run_path = Path(run_path).resolve()
    engine = TradeForensicsEngine(
        config,
        run_path / "trade_log.csv",
        Path(normalised_tick_path).resolve(),
        Path(candle_path).resolve(),
        run_path,
    )
    summary = engine.run()
    add_forensic_link(run_path, summary)
    print(json.dumps(summary, default=str, indent=2))
    print(f"Forensic report: {run_path / 'forensics' / 'forensic_report.html'}")


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
    config = apply_strategy_overrides(
        load_strategy_config(path),
        normalised_tick_path=getattr(args, "normalised_tick_path", None),
        candle_path=getattr(args, "candle_path", None),
        report_output_path=getattr(args, "report_output_path", None),
    )
    if getattr(args, "weekend_policy_name", None):
        config = apply_weekend_policy_variant(
            config, args.weekend_policy_name,
            getattr(args, "weekend_variants_config", "config/weekend_policy_variants.usdjpy.yaml"),
        )
    return config


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
        if name == "backtest":
            command.add_argument("--weekend-policy-name")
            command.add_argument("--weekend-variants-config", default="config/weekend_policy_variants.usdjpy.yaml")
        if name == "normalise":
            command.add_argument("--overwrite", action="store_true")
    all_parser = sub.add_parser("all")
    all_parser.add_argument("--data-quality-config", required=True)
    all_parser.add_argument("--strategy-config", required=True)
    all_parser.add_argument("--overwrite", action="store_true")
    all_parser.add_argument("--run-forensics", action="store_true")
    add_data_overrides(all_parser)
    add_strategy_overrides(all_parser)
    forensic_parser = sub.add_parser("forensics")
    forensic_parser.add_argument("--strategy-config", required=True)
    forensic_parser.add_argument("--run-path", required=True)
    forensic_parser.add_argument("--normalised-tick-path", required=True)
    forensic_parser.add_argument("--candle-path", required=True)
    compare_parser = sub.add_parser("weekend-policy-compare")
    compare_parser.add_argument("--strategy-config", required=True)
    compare_parser.add_argument("--weekend-variants-config", required=True)
    compare_parser.add_argument("--normalised-tick-path", required=True)
    compare_parser.add_argument("--candle-path", required=True)
    compare_parser.add_argument("--report-output-path", required=True)
    stability_parser = sub.add_parser("stability-validate")
    stability_parser.add_argument("--strategy-config", required=True)
    stability_parser.add_argument("--run-path", required=True)
    stability_parser.add_argument("--candle-path", required=True)
    stability_parser.add_argument("--report-output-path", required=True)
    stability_parser.add_argument("--baseline-policy-name")
    walk_forward_parser = sub.add_parser("walk-forward")
    walk_forward_parser.add_argument("--strategy-config", required=True)
    walk_forward_parser.add_argument("--run-path", required=True)
    walk_forward_parser.add_argument("--candle-path", required=True)
    walk_forward_parser.add_argument("--report-output-path", required=True)
    robustness_parser = sub.add_parser("parameter-robustness")
    robustness_parser.add_argument("--strategy-config", required=True)
    robustness_parser.add_argument("--normalised-tick-path", required=True)
    robustness_parser.add_argument("--candle-path", required=True)
    robustness_parser.add_argument("--report-output-path", required=True)
    robustness_parser.add_argument("--max-variants", type=int, default=100)
    robustness_parser.add_argument("--include-full-grid", action=argparse.BooleanOptionalAction, default=False)
    robustness_parser.add_argument("--skip-heatmaps", action=argparse.BooleanOptionalAction, default=False)
    robustness_parser.add_argument("--continue-on-error", action=argparse.BooleanOptionalAction, default=True)
    robustness_parser.add_argument("--baseline-run-path")
    stress_parser = sub.add_parser("monte-carlo-stress")
    stress_parser.add_argument("--strategy-config", required=True)
    stress_parser.add_argument("--run-path", required=True)
    stress_parser.add_argument("--normalised-tick-path")
    stress_parser.add_argument("--candle-path")
    stress_parser.add_argument("--report-output-path", required=True)
    stress_parser.add_argument("--iterations", type=int)
    stress_parser.add_argument("--seed", type=int)
    stress_parser.add_argument("--skip-charts", action=argparse.BooleanOptionalAction, default=False)
    stress_parser.add_argument("--quick", action=argparse.BooleanOptionalAction, default=False)
    guardrail_parser = sub.add_parser("broker-guardrails")
    guardrail_parser.add_argument("--strategy-config", required=True)
    guardrail_parser.add_argument("--guardrail-variants-config", required=True)
    guardrail_parser.add_argument("--normalised-tick-path", required=True)
    guardrail_parser.add_argument("--candle-path", required=True)
    guardrail_parser.add_argument("--report-output-path", required=True)
    guardrail_parser.add_argument("--daily-funding-pips", type=float)
    guardrail_parser.add_argument("--skip-funding", action=argparse.BooleanOptionalAction, default=False)
    guardrail_parser.add_argument("--variant")
    guardrail_parser.add_argument("--continue-on-error", action=argparse.BooleanOptionalAction, default=True)
    bakeoff_parser = sub.add_parser("final-guardrail-bakeoff")
    bakeoff_parser.add_argument("--strategy-config", required=True)
    bakeoff_parser.add_argument("--bakeoff-config", required=True)
    bakeoff_parser.add_argument("--guardrail-variants-config", required=True)
    bakeoff_parser.add_argument("--normalised-tick-path", required=True)
    bakeoff_parser.add_argument("--candle-path", required=True)
    bakeoff_parser.add_argument("--report-output-path", required=True)
    bakeoff_parser.add_argument("--reuse-existing", type=boolean, default=True)
    bakeoff_parser.add_argument("--run-missing-validations", type=boolean, default=True)
    bakeoff_parser.add_argument("--skip-monte-carlo", type=boolean, default=False)
    bakeoff_parser.add_argument("--monte-carlo-iterations", type=int, default=5000)
    bakeoff_parser.add_argument("--quick", type=boolean, default=False)
    bakeoff_parser.add_argument("--continue-on-error", type=boolean, default=True)
    bakeoff_parser.add_argument("--existing-guardrail-run-path")
    bakeoff_parser.add_argument("--existing-bakeoff-run-path")
    args = parser.parse_args()
    configure_logging(args.log_level)
    logger.info("Pipeline command started | command=%s", args.command)
    if args.command == "weekend-policy-compare":
        output = WeekendPolicyVariantRunner(
            args.strategy_config, args.weekend_variants_config, args.normalised_tick_path,
            args.candle_path, args.report_output_path,
        ).run_all_variants()
        print(f"Weekend policy comparison: {output / 'weekend_policy_comparison.html'}")
    elif args.command == "stability-validate":
        output = StabilityValidationRunner(
            args.strategy_config, args.run_path, args.candle_path, args.report_output_path,
            args.baseline_policy_name,
        ).run()
        print(f"Stability report: {output / 'stability_report.html'}")
    elif args.command == "walk-forward":
        output = WalkForwardValidationRunner(
            args.strategy_config, args.run_path, args.candle_path, args.report_output_path,
        ).run()
        print(f"Walk-forward report: {output / 'walk_forward_report.html'}")
    elif args.command == "parameter-robustness":
        output = ParameterRobustnessRunner(
            args.strategy_config, args.normalised_tick_path, args.candle_path,
            args.report_output_path, args.max_variants, args.include_full_grid,
            args.skip_heatmaps, args.continue_on_error, args.baseline_run_path,
        ).run()
        print(f"Parameter robustness report: {output / 'robustness_report.html'}")
    elif args.command == "monte-carlo-stress":
        output = MonteCarloStressRunner(
            args.strategy_config, args.run_path, args.report_output_path,
            args.normalised_tick_path, args.candle_path, args.iterations, args.seed,
            args.skip_charts, args.quick,
        ).run()
        print(f"Monte Carlo stress report: {output / 'stress_report.html'}")
    elif args.command == "broker-guardrails":
        output = BrokerGuardrailRunner(
            args.strategy_config, args.guardrail_variants_config, args.normalised_tick_path,
            args.candle_path, args.report_output_path, args.daily_funding_pips,
            args.skip_funding, args.variant, args.continue_on_error,
        ).run()
        print(f"Broker guardrail report: {output / 'broker_guardrail_report.html'}")
    elif args.command == "final-guardrail-bakeoff":
        output = FinalGuardrailBakeOffRunner(
            args.strategy_config, args.bakeoff_config, args.guardrail_variants_config,
            args.normalised_tick_path, args.candle_path, args.report_output_path,
            args.reuse_existing, args.run_missing_validations, args.skip_monte_carlo,
            args.monte_carlo_iterations, args.quick, args.continue_on_error,
            args.existing_guardrail_run_path,
            args.existing_bakeoff_run_path,
        ).run()
        print(f"Final guardrail bake-off report: {output / 'final_guardrail_bakeoff_report.html'}")
    elif args.command == "forensics":
        run_forensics(
            load_strategy_config(args.strategy_config),
            args.run_path,
            args.normalised_tick_path,
            args.candle_path,
        )
    elif args.command == "data-quality":
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
        if args.run_forensics:
            run_forensics(strategy, output, resolve(strategy, strategy.data["normalised_tick_path"]), resolve(strategy, strategy.data["candle_path"]))
        print(json.dumps(metrics, default=str, indent=2))
        print(f"Reports: {output}")
    logger.info("Pipeline command completed | command=%s", args.command)


if __name__ == "__main__":
    main()
