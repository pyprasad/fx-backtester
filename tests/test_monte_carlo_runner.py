import polars as pl

from src.stress.monte_carlo_runner import MonteCarloStressRunner


def test_runner_end_to_end(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    trades = pl.DataFrame({
        "pnl_r": [1.0, -1.0, 2.0, -.5], "net_pnl": [25.0, -25.0, 50.0, -12.5],
        "direction": ["SHORT"] * 4, "exit_reason": ["take_profit", "stop_loss", "weekend_force_close", "stop_loss"],
        "duration_days": [.1] * 4, "spread_pips_at_entry": [.5] * 4,
        "spread_pips_at_exit": [.5] * 4, "initial_risk_pips": [10.0] * 4,
    })
    trades.write_csv(run / "trade_log.csv")
    pl.DataFrame([{"total_return_percent": 1.0, "max_drawdown_percent": 1.0}]).write_csv(run / "strategy_summary.csv")
    pl.DataFrame([{"policy_name": "force_close_friday_20_30"}]).write_csv(run / "weekend_policy_summary.csv")
    output = MonteCarloStressRunner(
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml", run, tmp_path / "out",
        iterations=5, skip_charts=True,
    ).run()
    for name in ("stress_summary.csv", "monte_carlo_distribution.csv", "execution_stress_summary.csv",
                 "stress_score.json", "stress_report.html"):
        assert (output / name).exists()
