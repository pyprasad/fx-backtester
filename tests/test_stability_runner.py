import polars as pl

from src.stability.stability_runner import StabilityValidationRunner


def test_runner_end_to_end(tmp_path, stability_trades):
    run = tmp_path / "run"
    candles = tmp_path / "candles"
    run.mkdir()
    candles.mkdir()
    stability_trades.write_csv(run / "trade_log.csv")
    pl.DataFrame({"timestamp": stability_trades["exit_timestamp_utc"], "balance": [10100, 10060, 10180, 10160]}).write_csv(run / "equity_curve.csv")
    pl.DataFrame([{"starting_balance": 10000, "profit_factor": 2, "worst_trade_r": -0.4,
                   "max_drawdown_percent": 1, "total_return_percent": 1.6}]).write_csv(run / "strategy_summary.csv")
    dates = pl.date_range(stability_trades["entry_timestamp_utc"].min().date(),
                          stability_trades["entry_timestamp_utc"].max().date(), "1d", eager=True)
    pl.DataFrame({"timestamp": dates.cast(pl.Datetime("us", "UTC")), "mid_close": [100.0] * len(dates),
                  "mid_high": [100.2] * len(dates), "mid_low": [99.8] * len(dates)}).write_parquet(candles / "USDJPY_1D.parquet")
    output = StabilityValidationRunner(
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml", run, candles, tmp_path / "out"
    ).run()
    assert (output / "stability_report.html").exists()
    assert (output / "yearly_stability.csv").exists()
    assert (run / "stability_report_link.txt").exists()
