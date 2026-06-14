from pathlib import Path

import yaml


CONFIG = Path("config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml")


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
