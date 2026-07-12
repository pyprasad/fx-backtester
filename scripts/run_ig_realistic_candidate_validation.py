#!/usr/bin/env python3
import argparse
import copy
import os
import subprocess
from pathlib import Path

import yaml

from src.config.config_loader import load_strategy_config


FROZEN_CANDIDATE = "config/strategy.usdjpy.fx_swing_trend_reclaim_atr15_long_short_ig_realistic.yaml"
NORMALISED_TICKS = "data/normalised_ticks/USDJPY_2021_2026.parquet"
CANDLES = "data/candles/USDJPY_2021_2026"
NEWS_CALENDAR = "data/macro_calendar/usd_jpy_events_2022_2025_nasdaq.csv"
WEEKEND_POLICY = "force_close_friday_20_30"
ROOT = Path("reports/ig_realistic_candidate_validation")


VARIANTS = [
    {"name": "swing_risk025", "holding_mode": "swing", "risk": 0.25},
    {"name": "swing_risk050", "holding_mode": "swing", "risk": 0.50},
    {"name": "intraday_risk025", "holding_mode": "intraday", "risk": 0.25},
    {"name": "intraday_risk050", "holding_mode": "intraday", "risk": 0.50},
]


def _strategy_slug(variant: dict) -> str:
    return f"fx_swing_trend_reclaim_v1_atr15_long_short_ig_realistic_{variant['name']}"


def _candidate_dict() -> dict:
    config = load_strategy_config(FROZEN_CANDIDATE)
    data = config.model_dump(mode="json")
    data.pop("base_dir", None)
    return data


def _abs(path: str | Path) -> str:
    return str(Path(path).resolve())


def variant_config(base: dict, variant: dict) -> dict:
    data = copy.deepcopy(base)
    strategy_name = _strategy_slug(variant)
    direction_mode = f"long_short_ig_realistic_{variant['name']}"
    data["strategy"]["name"] = strategy_name
    data["strategy"]["test_mode"] = direction_mode
    data["risk"]["risk_per_trade_percent"] = variant["risk"]
    data["data"]["normalised_tick_path"] = _abs(NORMALISED_TICKS)
    data["data"]["candle_path"] = _abs(CANDLES)
    data["news_guard"]["calendar_file"] = _abs(NEWS_CALENDAR)
    data["walk_forward_validation"]["strategy_name"] = strategy_name
    data["walk_forward_validation"]["direction_mode"] = direction_mode
    data["parameter_robustness"]["strategy_name"] = strategy_name
    data["parameter_robustness"]["direction_mode"] = direction_mode
    data["monte_carlo_stress"]["strategy_name"] = strategy_name
    data["monte_carlo_stress"]["direction_mode"] = direction_mode
    data["monte_carlo_stress"]["simulation"]["starting_balance"] = data["risk"]["starting_balance"]

    guardrails = data["broker_execution_guardrails"]
    intraday = guardrails["intraday_mode"]
    swing = guardrails["swing_mode"]
    if variant["holding_mode"] == "intraday":
        intraday["enabled"] = True
        intraday["force_close_before_funding_cutoff"] = True
        intraday["force_close_time"] = "21:55"
        swing["allow_overnight_holding"] = False
        data["max_trade_duration_days"] = 1
    else:
        intraday["enabled"] = False
        swing["allow_overnight_holding"] = True
        data["max_trade_duration_days"] = 7
    return data


def config_path(variant: dict) -> Path:
    return ROOT / "generated_configs" / f"{variant['name']}.yaml"


def backtest_output_path(variant: dict) -> Path:
    return ROOT / "backtests" / variant["name"]


def latest_run_path(variant: dict) -> Path | None:
    root = backtest_output_path(variant)
    candidates = sorted(
        (path.parent for path in root.glob("*/strategy_summary.csv")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def prepare_configs() -> list[Path]:
    base = _candidate_dict()
    paths = []
    for variant in VARIANTS:
        path = config_path(variant)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(variant_config(base, variant), sort_keys=False))
        paths.append(path)
    return paths


def backtest_command(variant: dict) -> list[str]:
    return [
        "PYTHONPATH=.",
        ".venv/bin/python",
        "-m",
        "src.main",
        "backtest",
        "--config",
        str(config_path(variant)),
        "--normalised-tick-path",
        _abs(NORMALISED_TICKS),
        "--candle-path",
        _abs(CANDLES),
        "--report-output-path",
        _abs(backtest_output_path(variant)),
        "--weekend-policy-name",
        WEEKEND_POLICY,
    ]


def validation_commands(variant: dict, run_path: Path) -> list[list[str]]:
    config = str(config_path(variant))
    variant_root = ROOT / "validation" / variant["name"]
    return [
        [
            "PYTHONPATH=.", ".venv/bin/python", "-m", "src.main", "stability-validate",
            "--strategy-config", config,
            "--run-path", str(run_path),
            "--candle-path", _abs(CANDLES),
            "--report-output-path", _abs(variant_root / "stability"),
            "--baseline-policy-name", WEEKEND_POLICY,
        ],
        [
            "PYTHONPATH=.", ".venv/bin/python", "-m", "src.main", "walk-forward",
            "--strategy-config", config,
            "--run-path", str(run_path),
            "--candle-path", _abs(CANDLES),
            "--report-output-path", _abs(variant_root / "walk_forward"),
        ],
        [
            "PYTHONPATH=.", ".venv/bin/python", "-m", "src.main", "monte-carlo-stress",
            "--strategy-config", config,
            "--run-path", str(run_path),
            "--normalised-tick-path", NORMALISED_TICKS,
            "--normalised-tick-path", _abs(NORMALISED_TICKS),
            "--candle-path", _abs(CANDLES),
            "--report-output-path", _abs(variant_root / "monte_carlo"),
            "--iterations", "2000",
            "--seed", "42",
        ],
    ]


def shell(command: list[str]) -> str:
    return " ".join(command)


def print_backtest_commands() -> None:
    for variant in VARIANTS:
        print(f"# {variant['name']}")
        print(shell(backtest_command(variant)))
        print()


def print_validation_commands() -> None:
    for variant in VARIANTS:
        run_path = latest_run_path(variant)
        print(f"# {variant['name']}")
        if run_path is None:
            print(f"# Missing backtest run. Run the {variant['name']} backtest first.")
            print()
            continue
        for command in validation_commands(variant, run_path):
            print(shell(command))
        print()


def run_backtests() -> None:
    for variant in VARIANTS:
        command = backtest_command(variant)
        _env_prefix, executable, *args = command
        env = {**os.environ, "PYTHONPATH": "."}
        print(f"Running {variant['name']}...")
        subprocess.run([executable, *args], check=True, env=env)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and print validation commands for the frozen IG-realistic candidate.")
    parser.add_argument("--prepare", action="store_true", help="Write generated validation configs.")
    parser.add_argument("--print-backtest-commands", action="store_true")
    parser.add_argument("--print-validation-commands", action="store_true")
    parser.add_argument("--run-backtests", action="store_true", help="Run all four backtests locally.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.prepare or not any((args.print_backtest_commands, args.print_validation_commands, args.run_backtests)):
        paths = prepare_configs()
        print("Prepared configs:")
        for path in paths:
            print(f"- {path}")
        print()
    if args.print_backtest_commands:
        print_backtest_commands()
    if args.run_backtests:
        run_backtests()
    if args.print_validation_commands:
        print_validation_commands()


if __name__ == "__main__":
    main()
