from src.robustness.parameter_space import ParameterVariant
from src.robustness.robustness_runner import ParameterRobustnessRunner
from src.robustness.variant_backtest import VariantBacktestRunner


def test_variant_runner_records_error(monkeypatch, tmp_path, strategy_config):
    monkeypatch.setattr("src.robustness.variant_backtest.apply_weekend_policy_variant",
                        lambda config, *_args: config)
    monkeypatch.setattr("src.robustness.variant_backtest.run_backtest",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("failed")))
    row = VariantBacktestRunner(strategy_config, tmp_path).run(
        ParameterVariant("x", "x", "baseline", {}, "", True)
    )
    assert row["run_status"] == "ERROR"
    assert (tmp_path / "variants/x/variant_metadata.json").exists()


def test_parameter_robustness_applies_session_overrides(tmp_path):
    windows = [
        {"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
        {"name": "London morning", "start": "07:00", "end": "11:30", "timezone": "Europe/London"},
    ]
    runner = ParameterRobustnessRunner(
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml",
        tmp_path / "ticks.parquet",
        tmp_path / "candles",
        tmp_path / "reports",
        session_timezone="UTC",
        session_windows=windows,
    )

    assert runner.config.session_filter["timezone"] == "UTC"
    assert runner.config.session_filter["entry_windows"] == windows
