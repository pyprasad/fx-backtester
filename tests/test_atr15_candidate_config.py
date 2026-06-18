import yaml


def test_atr15_candidate_contract_is_validation_only():
    with open("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_atr15_combined_candidate.yaml") as handle:
        config = yaml.safe_load(handle)

    assert config["strategy"]["version"] == "atr15_combined_sessions_candidate"
    assert config["strategy"]["production_ready"] is False
    assert config["strategy"]["live_trading_approved"] is False
    assert config["stop_loss"]["atr_multiplier"] == 1.5
    assert config["risk_management"]["risk_per_trade_percent"] == 0.25
    assert config["broker_guardrails"]["selected_guardrail_candidate"] == "min_risk_3pips_spread_ratio_20pct"
    assert config["candidate_decision"]["selected_for_demo_validation"] is False
