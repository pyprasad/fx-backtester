from src.broker_guardrails.guardrail_metrics import score_guardrail


def test_guardrail_score_verdict(strategy_config):
    row = {
        "accepted_signals": 100, "rejected_signals": 10, "return_percent_before_funding": 20,
        "return_percent_after_funding": 19, "profit_factor_after_funding": 2,
        "worst_trade_r_after_funding": -2, "max_drawdown_percent": 2,
        "max_spread_to_risk_ratio": .2, "accepted_below_broker_minimum": 0,
        "accepted_below_configured_minimum": 0, "accepted_above_configured_ratio": 0,
        "wednesday_triple_rollover_count": 1, "total_trades": 100,
    }
    score, verdict = score_guardrail(row, strategy_config.broker_execution_guardrails)
    assert score == 100
    assert verdict == "STRONG_GUARDRAIL"
