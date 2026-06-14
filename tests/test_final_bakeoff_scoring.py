from copy import deepcopy

from src.bakeoff.candidate_config import load_bakeoff_config
from src.bakeoff.candidate_scoring import hard_fail_reasons, rank_candidates, score_candidates


def _row(name, ret=50, pf=2, drawdown=2, worst=-2):
    return {
        "candidate_name": name, "return_after_funding": ret, "profit_factor_after_funding": pf,
        "average_r_after_funding": .4, "max_drawdown_percent": drawdown, "worst_trade_r": worst,
        "bootstrap_p5_return": 30, "bootstrap_p95_drawdown": 4,
        "bootstrap_probability_of_loss": 0, "bootstrap_probability_drawdown_above_10": 0,
        "execution_stress_failure_count": 0, "worst_execution_stress_trade_r": -4,
        "total_trades": 400, "max_spread_to_risk_ratio": .2, "missing_validation_layers": "",
    }


def test_hard_fail_rules():
    rules = load_bakeoff_config("config/final_guardrail_bakeoff.usdjpy.yaml")["hard_fail_rules"]
    assert "worst_trade_r" in hard_fail_reasons(_row("ig_min_stop_only", worst=-3), rules)
    assert "profit_factor_after_funding" in hard_fail_reasons(_row("ig_min_stop_only", pf=1.2), rules)
    assert "return_after_funding" in hard_fail_reasons(_row("ig_min_stop_only", ret=0), rules)


def test_score_normalization_and_safety_tie_breaker():
    config = load_bakeoff_config("config/final_guardrail_bakeoff.usdjpy.yaml")
    rows = [_row("ig_min_stop_only", ret=60, drawdown=2, worst=-2.1),
            _row("min_risk_3pips", ret=55, drawdown=1.5, worst=-2),
            _row("recommended_research_guardrail", ret=50, drawdown=1, worst=-2)]
    scored, breakdowns = score_candidates(deepcopy(rows), config)
    assert breakdowns[0]["return_score"] > breakdowns[1]["return_score"]
    assert breakdowns[2]["drawdown_score"] >= breakdowns[0]["drawdown_score"]
    ranked = rank_candidates(scored, config)
    assert ranked[0]["candidate_name"] == "recommended_research_guardrail"
