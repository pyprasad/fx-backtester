from pathlib import Path

from scripts.run_ig_realistic_candidate_validation import _candidate_dict, variant_config


def test_validation_variant_sets_risk_and_intraday_mode():
    base = _candidate_dict()

    config = variant_config(base, {"name": "intraday_risk050", "holding_mode": "intraday", "risk": 0.50})

    assert config["risk"]["risk_per_trade_percent"] == 0.50
    assert config["max_trade_duration_days"] == 1
    assert config["broker_execution_guardrails"]["intraday_mode"]["enabled"] is True
    assert config["broker_execution_guardrails"]["swing_mode"]["allow_overnight_holding"] is False
    assert config["strategy"]["test_mode"] == "long_short_ig_realistic_intraday_risk050"
    assert Path(config["data"]["normalised_tick_path"]).is_absolute()
    assert Path(config["data"]["candle_path"]).is_absolute()
    assert Path(config["news_guard"]["calendar_file"]).is_absolute()


def test_validation_variant_keeps_swing_mode_for_baseline_risk():
    base = _candidate_dict()

    config = variant_config(base, {"name": "swing_risk025", "holding_mode": "swing", "risk": 0.25})

    assert config["risk"]["risk_per_trade_percent"] == 0.25
    assert config["max_trade_duration_days"] == 7
    assert config["broker_execution_guardrails"]["intraday_mode"]["enabled"] is False
    assert config["broker_execution_guardrails"]["swing_mode"]["allow_overnight_holding"] is True
