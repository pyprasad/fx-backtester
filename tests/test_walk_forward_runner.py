import polars as pl

from src.walk_forward.walk_forward_runner import WalkForwardValidationRunner


def test_walk_forward_runner_end_to_end(tmp_path, stability_trades):
    run, candles = tmp_path / "run", tmp_path / "candles"
    run.mkdir()
    candles.mkdir()
    stability_trades.write_csv(run / "trade_log.csv")
    pl.DataFrame([{"starting_balance": 10000}]).write_csv(run / "strategy_summary.csv")
    timestamps = pl.datetime_range(
        pl.datetime(2022, 1, 1, time_zone="UTC"), pl.datetime(2025, 12, 31, time_zone="UTC"),
        "1mo", eager=True,
    )
    pl.DataFrame({"timestamp": timestamps}).write_parquet(candles / "USDJPY_1D.parquet")
    output = WalkForwardValidationRunner(
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml", run, candles, tmp_path / "out"
    ).run()
    for name in ("anchored_walk_forward.csv", "rolling_walk_forward_summary.csv",
                 "walk_forward_score.json", "walk_forward_summary.csv", "walk_forward_report.html"):
        assert (output / name).exists()
