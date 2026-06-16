import csv
from pathlib import Path
from types import SimpleNamespace

import yaml

from src.broker_guardrails.guardrail_runner import BrokerGuardrailRunner


def test_guardrail_runner_two_variants(monkeypatch, tmp_path: Path, strategy_config):
    variants = tmp_path / "variants.yaml"
    variants.write_text(yaml.safe_dump({"variants": [
        {"name": "a", "description": "a", "broker_execution_guardrails": {"enabled": False}},
        {"name": "b", "description": "b", "broker_execution_guardrails": {"enabled": True}},
    ]}))
    monkeypatch.setattr("src.broker_guardrails.guardrail_runner.load_strategy_config",
                        lambda _path: strategy_config.model_copy(deep=True))
    monkeypatch.setattr("src.broker_guardrails.guardrail_runner.apply_weekend_policy_variant",
                        lambda config, *_args: config)

    trade = SimpleNamespace(initial_risk_pips=10, spread_pips_at_entry=1, pnl_r=1)

    def fake_backtest(config, output_override):
        output_override.mkdir(parents=True)
        (output_override / "signal_rejection_log.csv").write_text("")
        with (output_override / "funding_summary.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "return_after_funding", "profit_factor_after_funding", "average_r_after_funding",
                "worst_trade_r_after_funding", "trades_held_overnight", "total_funding_days",
                "wednesday_triple_rollover_events",
            ])
            writer.writeheader()
            writer.writerow({
                "return_after_funding": 10, "profit_factor_after_funding": 2,
                "average_r_after_funding": 1, "worst_trade_r_after_funding": -1,
                "trades_held_overnight": 0, "total_funding_days": 0,
                "wednesday_triple_rollover_events": 0,
            })
        return [trade], {"total_return_percent": 10, "profit_factor": 2, "max_drawdown_percent": 1,
                         "average_r": 1, "worst_trade_r": -1}, output_override

    monkeypatch.setattr("src.broker_guardrails.guardrail_runner.run_backtest", fake_backtest)
    output = BrokerGuardrailRunner("x", variants, tmp_path / "ticks", tmp_path / "candles",
                                   tmp_path / "out").run()
    assert (output / "broker_guardrail_comparison.csv").exists()
    assert len(list(csv.DictReader((output / "broker_guardrail_comparison.csv").open()))) == 2


def test_guardrail_runner_applies_session_research_override(tmp_path: Path, strategy_config):
    runner = BrokerGuardrailRunner(
        "x", "x", tmp_path / "ticks", tmp_path / "candles", tmp_path / "out",
        session_timezone="Asia/Tokyo",
        session_windows=[{"name": "Tokyo", "start": "09:00", "end": "18:00"}],
    )
    runner.strategy_path = Path("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")
    runner.variants_path = Path("config/broker_guardrail_variants.usdjpy.yaml")

    config = runner._config({"broker_execution_guardrails": {}})

    assert config.session_filter["timezone"] == "Asia/Tokyo"
    assert config.session_filter["entry_windows"] == [
        {"name": "Tokyo", "start": "09:00", "end": "18:00"}
    ]
