import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from src.broker_guardrails.guardrail_runner import BrokerGuardrailRunner
from src.stability.stability_runner import StabilityValidationRunner
from src.stress.monte_carlo_runner import MonteCarloStressRunner
from src.utils.logging import get_logger
from src.walk_forward.walk_forward_runner import WalkForwardValidationRunner

from .candidate_config import load_bakeoff_config
from .candidate_metrics import collect_candidate_metrics
from .candidate_report import build_recommendation, write_candidate_report
from .candidate_scoring import rank_candidates, score_candidates
from .charts import generate_charts

logger = get_logger(__name__)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _comparison_row(backtest: Path, name: str) -> dict:
    path = backtest.parent.parent / "broker_guardrail_comparison.csv"
    if not path.exists():
        return {}
    with path.open() as handle:
        return next((row for row in csv.DictReader(handle) if row["variant_name"] == name), {})


def _baseline_row(root: Path | None) -> dict:
    if root is None:
        return {}
    path = root / "broker_guardrail_comparison.csv"
    if not path.exists():
        return {}
    with path.open() as handle:
        return next(
            (row for row in csv.DictReader(handle) if row["variant_name"] == "baseline_no_extra_guardrails"),
            {},
        )


class FinalGuardrailBakeOffRunner:
    def __init__(self, strategy_config, bakeoff_config, guardrail_variants_config,
                 normalised_tick_path, candle_path, report_output_path, reuse_existing=True,
                 run_missing_validations=True, skip_monte_carlo=False, monte_carlo_iterations=5000,
                 quick=False, continue_on_error=True, existing_guardrail_run_path=None,
                 existing_bakeoff_run_path=None):
        self.strategy_config = Path(strategy_config)
        self.config = load_bakeoff_config(bakeoff_config)
        self.variants_config = Path(guardrail_variants_config)
        self.tick_path, self.candle_path = Path(normalised_tick_path), Path(candle_path)
        self.report_parent = Path(report_output_path).resolve()
        self.reuse_existing, self.run_missing = reuse_existing, run_missing_validations
        self.skip_monte_carlo, self.iterations = skip_monte_carlo, monte_carlo_iterations
        self.quick, self.continue_on_error = quick, continue_on_error
        self.existing_guardrail_root = Path(existing_guardrail_run_path).resolve() if existing_guardrail_run_path else None
        self.existing_bakeoff_root = Path(existing_bakeoff_run_path).resolve() if existing_bakeoff_run_path else None
        self.output = self.report_parent / datetime.now(timezone.utc).strftime(
            "%Y%m%d_%H%M%S_usdjpy_fx_swing_trend_reclaim_v1"
        )

    def _discover_guardrail_root(self) -> Path | None:
        if self.existing_guardrail_root:
            return self.existing_guardrail_root
        root = self.strategy_config.resolve().parent.parent / "reports" / "broker_guardrails"
        required = {candidate["guardrail_variant_name"] for candidate in self.config["candidates"]}
        matches = [
            path for path in root.glob("*") if path.is_dir() and
            required.issubset({item.name for item in (path / "variants").glob("*")})
        ]
        return max(matches, key=lambda path: path.name) if matches else None

    def _run_base(self, candidate: dict, candidate_output: Path) -> Path:
        output = BrokerGuardrailRunner(
            self.strategy_config, self.variants_config, self.tick_path, self.candle_path,
            candidate_output / "base_run", variant=candidate["guardrail_variant_name"],
            continue_on_error=False,
        ).run()
        return output / "variants" / candidate["guardrail_variant_name"]

    def _existing_validation(self, candidate: str, label: str) -> Path | None:
        if not self.existing_bakeoff_root:
            return None
        reference = self.existing_bakeoff_root / "candidates" / candidate / f"{label}_path.txt"
        if not reference.exists():
            return None
        path = Path(reference.read_text().strip())
        return path if path.exists() else None

    def _validation(self, candidate: str, candidate_output: Path,
                    backtest: Path) -> tuple[Path | None, Path | None, Path | None]:
        stability = self._existing_validation(candidate, "stability") if self.reuse_existing else None
        walk_forward = self._existing_validation(candidate, "walk_forward") if self.reuse_existing else None
        stress = self._existing_validation(candidate, "stress") if self.reuse_existing else None
        if self.run_missing and stability is None:
            stability = StabilityValidationRunner(
                self.strategy_config, backtest, self.candle_path, candidate_output / "stability"
            ).run()
        if self.run_missing and walk_forward is None:
            walk_forward = WalkForwardValidationRunner(
                self.strategy_config, backtest, self.candle_path, candidate_output / "walk_forward"
            ).run()
        if self.run_missing and not self.skip_monte_carlo and stress is None:
            stress = MonteCarloStressRunner(
                self.strategy_config, backtest, candidate_output / "stress", self.tick_path,
                self.candle_path, self.iterations, quick=self.quick,
            ).run()
        return stability, walk_forward, stress

    def run(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        existing = self._discover_guardrail_root() if self.reuse_existing else None
        baseline = _baseline_row(existing)
        metrics = []
        for candidate in self.config["candidates"]:
            name = candidate["name"]
            candidate_output = self.output / "candidates" / name
            candidate_output.mkdir(parents=True, exist_ok=True)
            try:
                backtest = existing / "variants" / name if existing else None
                if not backtest or not (backtest / "trade_log.csv").exists():
                    if not self.run_missing:
                        raise FileNotFoundError(f"Missing base backtest for {name}")
                    backtest = self._run_base(candidate, candidate_output)
                (candidate_output / "backtest_path.txt").write_text(str(backtest))
                stability, walk_forward, stress = self._validation(name, candidate_output, backtest)
                for label, path in (("stability", stability), ("walk_forward", walk_forward), ("stress", stress)):
                    if path:
                        (candidate_output / f"{label}_path.txt").write_text(str(path))
                row = collect_candidate_metrics(
                    candidate, backtest, _comparison_row(backtest, name),
                    stability, walk_forward, stress,
                )
                if baseline:
                    row["baseline_total_trades"] = float(baseline["total_trades"])
                    row["baseline_return_after_funding"] = float(baseline["return_percent_after_funding"])
                metrics.append(row)
            except Exception:
                logger.exception("Bake-off candidate failed | candidate=%s", name)
                if not self.continue_on_error:
                    raise
        if len(metrics) != 3:
            raise RuntimeError("FX-2H requires all three candidates to produce metric rows")
        metrics, breakdowns = score_candidates(metrics, self.config)
        ranked = rank_candidates(metrics, self.config)
        recommendation = build_recommendation(ranked)
        _write_csv(self.output / "final_guardrail_bakeoff_summary.csv", metrics)
        (self.output / "final_guardrail_bakeoff_summary.json").write_text(json.dumps(metrics, indent=2))
        _write_csv(self.output / "candidate_metric_matrix.csv", metrics)
        _write_csv(self.output / "candidate_score_breakdown.csv", breakdowns)
        _write_csv(self.output / "candidate_ranking.csv", ranked)
        (self.output / "final_candidate_recommendation.json").write_text(
            json.dumps(recommendation, indent=2)
        )
        charts = []
        if self.config["output"].get("include_charts"):
            try:
                charts = generate_charts(self.output / "charts", metrics, breakdowns)
            except Exception as exc:
                logger.warning("Bake-off charts skipped | error=%s", exc)
        write_candidate_report(self.output, ranked, breakdowns, recommendation, charts)
        return self.output
