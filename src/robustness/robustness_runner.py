import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from src.config.config_loader import apply_strategy_overrides, load_strategy_config
from src.utils.logging import get_logger

from .heatmap_generator import generate_heatmaps
from .parameter_space import ParameterSpaceBuilder
from .robustness_report import write_robustness_report
from .robustness_score import calculate_robustness_score
from .sensitivity_analysis import local_neighbourhood_analysis, one_factor_sensitivity, paired_summary
from .variant_backtest import VariantBacktestRunner

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


class ParameterRobustnessRunner:
    def __init__(self, strategy_config, normalised_tick_path, candle_path, report_output_path,
                 max_variants=100, include_full_grid=False, skip_heatmaps=False,
                 continue_on_error=True, baseline_run_path=None,
                 session_timezone=None, session_windows=None,
                 risk_per_trade_percent=None, atr_stop_multiplier=None,
                 rsi_short_trigger=None, ema_mid=None, ema_slow=None,
                 final_target_r=None, partial_take_profit_r=None,
                 breakeven_after_r=None, trailing_atr_multiplier=None,
                 enable_long=None):
        self.config = load_strategy_config(strategy_config)
        self.config = apply_strategy_overrides(
            self.config,
            risk_per_trade_percent=risk_per_trade_percent,
            atr_stop_multiplier=atr_stop_multiplier,
            rsi_short_trigger=rsi_short_trigger,
            ema_mid=ema_mid,
            ema_slow=ema_slow,
            final_target_r=final_target_r,
            partial_take_profit_r=partial_take_profit_r,
            breakeven_after_r=breakeven_after_r,
            trailing_atr_multiplier=trailing_atr_multiplier,
            enable_long=enable_long,
        )
        self.settings = self.config.parameter_robustness
        if atr_stop_multiplier is not None:
            self.settings["baseline_parameters"]["atr_stop_multiplier"] = atr_stop_multiplier
        if rsi_short_trigger is not None:
            self.settings["baseline_parameters"]["rsi_short_trigger"] = rsi_short_trigger
        if ema_mid is not None:
            self.settings["baseline_parameters"]["ema_mid"] = ema_mid
        if ema_slow is not None:
            self.settings["baseline_parameters"]["ema_slow"] = ema_slow
        if final_target_r is not None:
            self.settings["baseline_parameters"]["final_target_r"] = final_target_r
        if partial_take_profit_r is not None:
            self.settings["baseline_parameters"]["partial_take_profit_r"] = partial_take_profit_r
        if breakeven_after_r is not None:
            self.settings["baseline_parameters"]["breakeven_after_r"] = breakeven_after_r
        if trailing_atr_multiplier is not None:
            self.settings["baseline_parameters"]["trailing_atr_multiplier"] = trailing_atr_multiplier
        self.config.data["normalised_tick_path"] = str(Path(normalised_tick_path).resolve())
        self.config.data["candle_path"] = str(Path(candle_path).resolve())
        if session_timezone:
            self.config.session_filter["timezone"] = session_timezone
        if session_windows:
            self.config.session_filter["entry_windows"] = session_windows
        self.report_parent = Path(report_output_path).resolve()
        self.max_variants = max_variants
        self.skip_heatmaps = skip_heatmaps
        self.continue_on_error = continue_on_error
        self.baseline_run_path = Path(baseline_run_path).resolve() if baseline_run_path else None
        if include_full_grid:
            self.settings.setdefault("test_modes", {}).setdefault("full_grid", {})["enabled"] = True
        policy = self.settings.get("baseline_policy_name", "force_close_friday_20_30")
        self.output = self.report_parent / datetime.now(timezone.utc).strftime(
            f"%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1_{policy}"
        )

    def _paired_rows(self, executed: list[dict], builder: ParameterSpaceBuilder) -> tuple[dict, list[dict]]:
        baseline = self.settings["baseline_parameters"]
        by_effective = {}
        for row in executed:
            effective = {**baseline, **json.loads(row["parameter_overrides_json"])}
            by_effective[tuple(sorted(effective.items()))] = row
        files, summaries = {}, []
        for pair in self.settings.get("paired_sensitivity_tests", []):
            x, y = list(pair["parameters"])
            rows = []
            for variant in builder.build_paired_sensitivity_variants(
                {"baseline_parameters": baseline, "paired_sensitivity_tests": [pair]}
            ):
                effective = {**baseline, **variant.parameter_overrides}
                source = by_effective.get(tuple(sorted(effective.items())))
                if not source:
                    continue
                rows.append({
                    "parameter_x": x, "value_x": variant.parameter_overrides[x],
                    "parameter_y": y, "value_y": variant.parameter_overrides[y],
                    "variant_name": source["variant_name"],
                    **{key: source.get(key) for key in (
                        "total_return_percent", "profit_factor", "max_drawdown_percent",
                        "average_r", "worst_trade_r", "pass_flag", "score", "run_status",
                    )},
                })
            files[pair["name"]] = rows
            summaries.append(paired_summary(pair["name"], rows))
        return files, summaries

    def run(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        builder = ParameterSpaceBuilder()
        variants = builder.build_all_variants(self.config)
        if len(variants) > self.max_variants:
            raise ValueError(f"Robustness variants ({len(variants)}) exceed --max-variants ({self.max_variants})")
        runner = VariantBacktestRunner(self.config, self.output)
        rows = []
        for index, variant in enumerate(variants, 1):
            logger.info("Robustness variant %s/%s | name=%s | overrides=%s",
                        index, len(variants), variant.variant_name, variant.parameter_overrides)
            row = runner.run(variant)
            rows.append(row)
            logger.info("Robustness variant complete | name=%s | status=%s | pass=%s",
                        variant.variant_name, row["run_status"], row["pass_flag"])
            if row["run_status"] == "ERROR" and not self.continue_on_error:
                raise RuntimeError(row["error_message"])
        _write_csv(self.output / "robustness_summary.csv", rows)
        (self.output / "robustness_summary.json").write_text(json.dumps(rows, indent=2))

        one_factor = one_factor_sensitivity(rows)
        _write_csv(self.output / "one_factor_sensitivity.csv", one_factor)
        paired_files, paired = self._paired_rows(rows, builder)
        for name, pair_rows in paired_files.items():
            _write_csv(self.output / f"paired_{name}.csv", pair_rows)
            if not self.skip_heatmaps:
                try:
                    generate_heatmaps(self.output, name, pair_rows)
                except Exception as exc:
                    logger.warning("Heatmap generation skipped | pair=%s | error=%s", name, exc)
        _write_csv(self.output / "paired_sensitivity_summary.csv", paired)

        local, neighbourhood = local_neighbourhood_analysis(rows)
        _write_csv(self.output / "local_neighbourhood_summary.csv", local + [neighbourhood])
        score = calculate_robustness_score(rows, one_factor, paired, neighbourhood)
        flat_score = {key: value for key, value in score.items() if not isinstance(value, dict)}
        _write_csv(self.output / "robustness_score.csv", [flat_score])
        (self.output / "robustness_score.json").write_text(json.dumps(score, indent=2))
        successful = [row for row in rows if row["run_status"] == "SUCCESS"]
        baseline = next(row for row in rows if row["variant_name"] == "baseline_original")
        ranked_return = sorted(successful, key=lambda row: row["total_return_percent"], reverse=True)
        ranked_pf = sorted(successful, key=lambda row: row["profit_factor"], reverse=True)
        ranked_drawdown = sorted(successful, key=lambda row: row["max_drawdown_percent"])
        summary = {
            "strategy_name": self.settings["strategy_name"], "market": self.settings["market"],
            "weekend_policy_name": self.settings["baseline_policy_name"], "variants_tested": len(rows),
            "normalised_tick_path": self.config.data["normalised_tick_path"],
            "candle_path": self.config.data["candle_path"],
            "successful_variants": len(successful), "worst_observed_trade_r": min(
                (row["worst_trade_r"] for row in successful), default=0
            ),
            "baseline_return_rank": ranked_return.index(baseline) + 1,
            "baseline_profit_factor_rank": ranked_pf.index(baseline) + 1,
            "baseline_drawdown_rank": ranked_drawdown.index(baseline) + 1,
            **flat_score,
        }
        report = write_robustness_report(
            self.output, summary, score, baseline, one_factor, paired, local, neighbourhood
        )
        if self.baseline_run_path:
            (self.baseline_run_path / "parameter_robustness_report_link.txt").write_text(str(report))
        logger.info("Parameter robustness report written | path=%s", report)
        return self.output
