from types import SimpleNamespace

from src.backtest.backtest_engine import strategy_run_name


def test_strategy_run_name_uses_configured_strategy_name():
    config = SimpleNamespace(strategy={"name": "FX Swing ATR15 Long/Short Candidate"})

    run_name = strategy_run_name(config)

    assert run_name.endswith("_usdjpy_fx_swing_atr15_long_short_candidate")
