import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

from src.config.config_loader import load_strategy_config
from src.utils.logging import get_logger

from .charts import generate_charts
from .equity_simulator import EquitySimulator
from .execution_stress import (
    apply_delayed_execution,
    apply_friday_close_slippage,
    apply_slippage,
    apply_spread_multiplier,
)
from .sequence_stress import sequence_stress_rows
from .stress_config import validate_trade_columns
from .stress_metrics import distribution_metrics
from .stress_report import write_stress_report
from .stress_score import calculate_stress_score
from .trade_sampler import TradeSampler

logger = get_logger(__name__)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class MonteCarloStressRunner:
    def __init__(self, strategy_config, run_path, report_output_path, normalised_tick_path=None,
                 candle_path=None, iterations=None, seed=None, skip_charts=False, quick=False):
        self.config = load_strategy_config(strategy_config)
        self.settings = self.config.monte_carlo_stress
        simulation = self.settings["simulation"]
        self.iterations = 500 if quick else int(iterations or simulation["iterations"])
        self.seed = int(seed if seed is not None else self.settings["methodology"]["random_seed"])
        self.run_path = Path(run_path).resolve()
        self.tick_path = str(Path(normalised_tick_path).resolve()) if normalised_tick_path else ""
        self.candle_path = str(Path(candle_path).resolve()) if candle_path else ""
        self.skip_charts = skip_charts
        policy = self.settings["baseline_policy_name"]
        self.output = Path(report_output_path).resolve() / datetime.now(timezone.utc).strftime(
            f"%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1_{policy}"
        )

    def _load(self) -> tuple[pl.DataFrame, dict]:
        trade_path, summary_path = self.run_path / "trade_log.csv", self.run_path / "strategy_summary.csv"
        missing = [str(path) for path in (trade_path, summary_path) if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Required stress inputs are missing: {', '.join(missing)}")
        trades = pl.read_csv(trade_path, try_parse_dates=True)
        validate_trade_columns(trades.columns)
        numeric = [
            "pnl_r", "net_pnl", "duration_days", "spread_pips_at_entry",
            "spread_pips_at_exit", "initial_risk_pips",
        ]
        trades = trades.with_columns(*(pl.col(column).cast(pl.Float64) for column in numeric))
        policy_path = self.run_path / "weekend_policy_summary.csv"
        if policy_path.exists():
            policy = pl.read_csv(policy_path).row(0, named=True)["policy_name"]
            if policy != self.settings["baseline_policy_name"]:
                raise ValueError(f"Stress testing requires {self.settings['baseline_policy_name']}, got {policy}")
        return trades, pl.read_csv(summary_path).row(0, named=True)

    def _simulate(self, name, method, factory, simulator, rng) -> tuple[list[dict], dict]:
        paths = []
        for index in range(self.iterations):
            if index and index % 1000 == 0:
                logger.info("Stress simulation progress | scenario=%s | iteration=%s/%s",
                            name, index, self.iterations)
            paths.append(simulator.simulate(factory(TradeSampler(rng))))
        summary = {"scenario_name": name, "method": method, "iteration_count": self.iterations,
                   **distribution_metrics(paths)}
        return paths, summary

    def _write_scenario(self, name: str, summary: dict, paths: list[dict]) -> None:
        folder = self.output / "scenarios" / name
        folder.mkdir(parents=True, exist_ok=True)
        _write_csv(folder / "scenario_summary.csv", [summary])
        distribution = [{key: value for key, value in path.items() if key != "equity_curve"} for path in paths]
        _write_csv(folder / "scenario_distribution.csv", distribution)
        samples = []
        for path_id, path in enumerate(paths[: min(100, len(paths))]):
            samples += [{"path_id": path_id, "trade_index": index, "equity": equity}
                        for index, equity in enumerate(path["equity_curve"])]
        _write_csv(folder / "scenario_paths_sample.csv", samples)

    def _execution_rows(self, trades, simulator) -> list[dict]:
        rows = []
        worst_limit = float(self.settings["pass_fail_rules"]["max_worst_simulated_trade_r"])

        def add(name, stress_type, value, stressed):
            result = simulator.simulate(stressed)
            rows.append({
                "scenario_name": name, "stress_type": stress_type, "stress_value": value,
                **{key: result[key] for key in (
                    "total_return_percent", "profit_factor", "max_drawdown_percent",
                    "average_r", "worst_trade_r",
                )}, "probability_of_loss_percent": 100 if result["loss_flag"] else 0,
                "verdict": "PASS" if (
                    result["total_return_percent"] > 0
                    and result["profit_factor"] >= 1.3
                    and result["worst_trade_r"] >= worst_limit
                ) else "FAIL",
            })

        settings = self.settings["execution_stress"]
        for value in settings["slippage_stress"]["slippage_pips"]:
            for side in settings["slippage_stress"]["apply_to"]:
                add(f"slippage_{value}_{side}", "slippage", value, apply_slippage(trades, value, side))
        for value in settings["spread_stress"]["spread_multiplier"]:
            for side in settings["spread_stress"]["apply_to"]:
                add(f"spread_{value}_{side}", "spread", value, apply_spread_multiplier(trades, value, side))
        for entry in settings["delayed_execution"]["entry_delay_ticks"]:
            add(f"entry_delay_{entry}_ticks", "entry_delay_approximation", entry,
                apply_delayed_execution(trades, entry_ticks=entry))
        for exit_ in settings["delayed_execution"]["exit_delay_ticks"]:
            add(f"exit_delay_{exit_}_ticks", "exit_delay_approximation", exit_,
                apply_delayed_execution(trades, exit_ticks=exit_))
        for value in settings["friday_close_stress"]["force_close_slippage_pips"]:
            add(f"friday_close_{value}_pips", "friday_close", value,
                apply_friday_close_slippage(trades, value))
        return rows

    def _tail_rows(self, trades, simulator, rng, baseline) -> list[dict]:
        rows = []
        for scenario in self.settings["execution_stress"]["tail_loss_injection"]["scenarios"]:
            paths = []
            losses = scenario["injected_losses_r"]
            injected = pl.DataFrame({"pnl_r": losses}).with_columns(
                pl.lit(0.0).alias("net_pnl")
            )
            for _ in range(self.iterations):
                position = int(rng.integers(0, trades.height + 1))
                sequence = pl.concat([trades.head(position), injected, trades.tail(trades.height - position)],
                                     how="diagonal_relaxed")
                paths.append(simulator.simulate(sequence))
            metrics = distribution_metrics(paths, baseline)
            rows.append({
                "scenario_name": scenario["name"], "injected_losses": json.dumps(losses),
                "median_return_percent": metrics["median_return_percent"],
                "p5_return_percent": metrics["p5_return_percent"],
                "p95_drawdown_percent": metrics["p95_max_drawdown_percent"],
                "probability_drawdown_above_10_percent": metrics["probability_drawdown_above_10_percent"],
                "probability_of_loss_percent": metrics["probability_of_loss_percent"],
                "verdict": "PASS" if metrics["p5_return_percent"] > 0 and metrics["p95_max_drawdown_percent"] <= 15 else "FAIL",
            })
        return rows

    def run(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        trades, baseline_reported = self._load()
        simulation = self.settings["simulation"]
        simulator = EquitySimulator(float(simulation["starting_balance"]),
                                    float(self.config.risk["risk_per_trade_percent"]))
        baseline = simulator.simulate(trades)
        rng = np.random.default_rng(self.seed)
        scenarios, all_distributions, primary_paths = [], [], []
        definitions = [
            ("trade_shuffle", "trade_shuffle", lambda sampler: sampler.shuffle_without_replacement(trades)),
            ("bootstrap_resample", "bootstrap", lambda sampler: sampler.bootstrap_with_replacement(trades)),
        ]
        for block in self.settings["monte_carlo_methods"]["block_bootstrap"]["block_size"]:
            definitions.append((f"block_bootstrap_{block}", "block_bootstrap",
                                lambda sampler, size=block: sampler.block_bootstrap(trades, size)))
        for name, method, factory in definitions:
            logger.info("Start stress scenario | name=%s | iterations=%s", name, self.iterations)
            paths, summary = self._simulate(name, method, factory, simulator, rng)
            scenarios.append(summary)
            self._write_scenario(name, summary, paths)
            for path in paths:
                all_distributions.append({"scenario_name": name, **{k: v for k, v in path.items()
                                         if k != "equity_curve"}})
            if name == "bootstrap_resample":
                primary_paths = paths

        missed = []
        for rate in self.settings["monte_carlo_methods"]["missed_trade_simulation"]["missed_trade_rates"]:
            for mode, method in (
                ("random", "remove_random_trades"), ("best_trades", "remove_best_trades"),
                ("worst_trades", "remove_worst_trades"),
            ):
                name = f"miss_{mode}_{int(rate * 100)}pct"
                paths, summary = self._simulate(
                    name, "missed_trade", lambda sampler, m=method, r=rate: getattr(sampler, m)(trades, r),
                    simulator, rng,
                )
                missed.append(summary)
                self._write_scenario(name, summary, paths)

        sequence = sequence_stress_rows(trades, TradeSampler(rng), simulator)
        execution = self._execution_rows(trades, simulator)
        tail = self._tail_rows(trades, simulator, rng, baseline)
        distribution = distribution_metrics(primary_paths, baseline)
        score = calculate_stress_score(distribution, execution, missed, tail, sequence)
        flat_score = {key: value for key, value in score.items() if not isinstance(value, dict)}
        worst_execution = min(execution, key=lambda row: row["total_return_percent"])
        worst_monte_carlo = min(scenarios, key=lambda row: row["p5_return_percent"])
        summary = {
            "strategy_name": self.settings["strategy_name"], "market": self.settings["market"],
            "weekend_policy_name": self.settings["baseline_policy_name"], "baseline_run_path": str(self.run_path),
            "normalised_tick_path": self.tick_path, "candle_path": self.candle_path,
            "iterations": self.iterations, "seed": self.seed, "simulation_mode": "r_compounding",
            "reported_baseline_return_percent": baseline_reported.get("total_return_percent"),
            "reproduced_baseline_return_percent": baseline["total_return_percent"], **flat_score, **distribution,
            "reported_baseline_profit_factor": baseline_reported.get("profit_factor"),
            "reproduced_baseline_profit_factor": baseline["profit_factor"],
            "reported_baseline_drawdown_percent": baseline_reported.get("max_drawdown_percent"),
            "stress_path_baseline_drawdown_percent": baseline["max_drawdown_percent"],
            "drawdown_method_note": "Stress paths use peak-relative drawdown at each equity point.",
            "worst_execution_scenario": worst_execution["scenario_name"],
            "worst_execution_return_percent": worst_execution["total_return_percent"],
            "worst_monte_carlo_scenario": worst_monte_carlo["scenario_name"],
            "worst_monte_carlo_p5_return_percent": worst_monte_carlo["p5_return_percent"],
        }
        _write_csv(self.output / "stress_summary.csv", [summary])
        (self.output / "stress_summary.json").write_text(json.dumps(summary, indent=2))
        _write_csv(self.output / "monte_carlo_distribution.csv", all_distributions)
        _write_csv(self.output / "monte_carlo_scenario_summary.csv", scenarios)
        _write_csv(self.output / "sequence_stress_summary.csv", sequence)
        _write_csv(self.output / "execution_stress_summary.csv", execution)
        _write_csv(self.output / "slippage_stress_summary.csv", [r for r in execution if r["stress_type"] == "slippage"])
        _write_csv(self.output / "spread_stress_summary.csv", [r for r in execution if r["stress_type"] == "spread"])
        _write_csv(self.output / "friday_close_stress_summary.csv", [r for r in execution if r["stress_type"] == "friday_close"])
        _write_csv(self.output / "missed_trade_stress_summary.csv", missed)
        _write_csv(self.output / "tail_loss_stress_summary.csv", tail)
        _write_csv(self.output / "stress_score.csv", [flat_score])
        (self.output / "stress_score.json").write_text(json.dumps(score, indent=2))
        selected = sorted(enumerate(primary_paths), key=lambda item: item[1]["total_return_percent"])
        labels = {
            "worst": selected[0], "p5": selected[max(0, round(len(selected) * .05) - 1)],
            "median": selected[len(selected) // 2],
            "p95": selected[min(len(selected) - 1, round(len(selected) * .95) - 1)],
        }
        samples = []
        for label, (path_id, path) in labels.items():
            curve = [{"trade_index": i, "equity": value, "path_id": label} for i, value in enumerate(path["equity_curve"])]
            _write_csv(self.output / f"{label}_path_equity_curve.csv", curve)
            samples += curve
        _write_csv(self.output / "sample_equity_paths.csv", samples)
        if not self.skip_charts:
            try:
                generate_charts(self.output, all_distributions, samples, scenarios)
            except Exception as exc:
                logger.warning("Stress charts skipped | error=%s", exc)
        report = write_stress_report(self.output, summary, score, distribution, scenarios,
                                     sequence, execution, missed, tail)
        (self.run_path / "monte_carlo_stress_report_link.txt").write_text(str(report))
        logger.info("Monte Carlo stress report written | path=%s", report)
        return self.output
