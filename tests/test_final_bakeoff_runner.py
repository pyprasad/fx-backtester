import csv
from pathlib import Path

from src.bakeoff.candidate_runner import FinalGuardrailBakeOffRunner


def test_runner_with_synthetic_reused_candidates(monkeypatch, tmp_path: Path):
    existing = tmp_path / "guardrails"
    candidates = ["ig_min_stop_only", "min_risk_3pips", "recommended_research_guardrail"]
    for name in candidates:
        folder = existing / "variants" / name
        folder.mkdir(parents=True)
        (folder / "trade_log.csv").write_text("trade_id\nx\n")

    def fake_metrics(candidate, *_args):
        return {
            "candidate_name": candidate["name"], "return_after_funding": 50,
            "profit_factor_after_funding": 2, "average_r_after_funding": .4,
            "max_drawdown_percent": 1.5, "worst_trade_r": -2,
            "bootstrap_p5_return": None, "bootstrap_p95_drawdown": None,
            "bootstrap_probability_of_loss": None, "bootstrap_probability_drawdown_above_10": None,
            "execution_stress_failure_count": 0, "worst_execution_stress_trade_r": None,
            "total_trades": 400, "max_spread_to_risk_ratio": .2,
            "missing_validation_layers": "stability|walk_forward|monte_carlo_stress|execution_stress",
        }

    monkeypatch.setattr("src.bakeoff.candidate_runner.collect_candidate_metrics", fake_metrics)
    monkeypatch.setattr("src.bakeoff.candidate_runner.generate_charts", lambda *_args: [])
    runner = FinalGuardrailBakeOffRunner(
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml",
        "config/final_guardrail_bakeoff.usdjpy.yaml", "config/broker_guardrail_variants.usdjpy.yaml",
        tmp_path / "ticks", tmp_path / "candles", tmp_path / "out",
        reuse_existing=True, run_missing_validations=False, existing_guardrail_run_path=existing,
    )
    output = runner.run()
    with (output / "candidate_ranking.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert {row["recommendation"] for row in rows} == {"HUMAN_REVIEW"}
    assert (output / "final_guardrail_bakeoff_report.html").exists()
