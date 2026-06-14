from src.robustness.parameter_space import ParameterVariant
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
