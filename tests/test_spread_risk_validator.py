from src.broker_guardrails.broker_rules import GuardrailDecision
from src.broker_guardrails.spread_risk_validator import validate_spread_risk


def test_spread_to_risk_and_abnormal_spread(strategy_config):
    settings = strategy_config.broker_execution_guardrails
    settings["spread_to_risk_filter"]["enabled"] = True
    accepted = validate_spread_risk(1, settings, GuardrailDecision(initial_risk_pips=5))
    rejected = validate_spread_risk(1, settings, GuardrailDecision(initial_risk_pips=4))
    abnormal = validate_spread_risk(2.1, settings, GuardrailDecision(initial_risk_pips=20))
    assert accepted.accepted
    assert "REJECT_SPREAD_TO_RISK_RATIO_TOO_HIGH" in rejected.rejection_reasons
    assert "REJECT_ENTRY_SPREAD_ABOVE_MAX" in abnormal.rejection_reasons
