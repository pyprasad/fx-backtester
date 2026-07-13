from pathlib import Path

import yaml


CONFIG = Path("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml")
PIP_FIRST_CONFIG = Path("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_pip_first_long_only_candidate.yaml")
RUNTIME_CONFIG = Path("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")


def test_final_strategy_config_contains_selected_baseline():
    config = yaml.safe_load(CONFIG.read_text())
    assert config["strategy"]["name"] == "fx_swing_trend_reclaim_v1"
    assert config["strategy"]["market"] == "USDJPY"
    assert config["strategy"]["direction_mode"] == "short_only"
    assert config["strategy"]["status"] == "historical_research_only"
    assert config["strategy"]["production_ready"] is False
    assert config["broker_guardrails"]["selected_guardrail_candidate"] == "min_risk_3pips"
    assert config["broker_guardrails"]["min_initial_risk_pips"] == 3.0
    assert config["broker_guardrails"]["min_stop_distance_pips"] == 2.0
    assert config["weekend_policy"]["name"] == "force_close_friday_20_30"
    assert config["time_guards"]["block_new_entries_after"] == "21:30"
    assert config["time_guards"]["overnight_funding_cutoff"] == "22:00"
    assert config["candidate_decision"]["backup"] == "ig_min_stop_only"
    assert config["candidate_decision"]["not_selected"] == "recommended_research_guardrail"
    assert set(config["validation_status"]) == {
        "fx_2a_integrity", "fx_2b_weekend_policy", "fx_2c_stability", "fx_2d_walk_forward",
        "fx_2e_parameter_robustness", "fx_2f_stress_testing", "fx_2g_broker_guardrails",
        "fx_2h_candidate_bakeoff",
    }


def test_executable_runtime_matches_selected_guardrail():
    config = yaml.safe_load(RUNTIME_CONFIG.read_text())
    guardrails = config["broker_execution_guardrails"]
    assert guardrails["minimum_initial_risk"]["default_min_initial_risk_pips"] == 3.0
    assert guardrails["spread_to_risk_filter"]["enabled"] is False
    assert guardrails["abnormal_spread_filter"]["max_entry_spread_pips"] == 2.0
    assert guardrails["entry_time_guard"]["block_new_entries_after"] == "21:30"


def test_pip_first_long_only_candidate_is_research_only():
    config = yaml.safe_load(PIP_FIRST_CONFIG.read_text())
    assert config["strategy"]["direction_mode"] == "long_only"
    assert config["strategy"]["live_trading_approved"] is False
    assert config["position_sizing"]["mode"] == "fixed_deal_size"
    assert config["position_sizing"]["fixed_deal_size"] == 0.5
    assert config["research_scope"]["dynamic_risk_sizing_selected"] is False
    assert config["research_scope"]["modifies_demo_bot"] is False
    assert config["candidate_decision"]["selected_for_next_validation"] is True
    assert config["candidate_decision"]["not_live_approval"] is True
