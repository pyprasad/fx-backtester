from src.config.config_loader import load_strategy_config


def test_fixed_004_config_contains_final_baseline_controls():
    config = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.fixed_004.yaml")
    assert config.position_sizing["mode"] == "fixed_spread_bet_stake"
    assert config.position_sizing["stake_per_pip_gbp"] == 0.04
    assert config.weekend_policy["enabled"] is True
    assert config.weekend_policy["policy_name"] == "force_close_friday_20_30"
    assert config.weekend_policy["force_close_on_friday"]["enabled"] is True
    assert config.weekend_policy["force_close_on_friday"]["close_time_utc"] == "20:30"
    assert config.broker_guardrails["selected_guardrail_candidate"] == "min_risk_3pips"
    assert config.broker_guardrails["min_initial_risk_pips"] == 3.0
    assert config.time_guards["block_new_entries_after"] == "21:30"
