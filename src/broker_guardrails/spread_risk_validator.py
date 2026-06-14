from .broker_rules import GuardrailDecision


def validate_spread_risk(entry_spread_pips: float, settings: dict,
                         decision: GuardrailDecision) -> GuardrailDecision:
    abnormal = settings["abnormal_spread_filter"]
    ratio_settings = settings["spread_to_risk_filter"]
    ratio = entry_spread_pips / decision.initial_risk_pips if decision.initial_risk_pips > 0 else float("inf")
    decision.entry_spread_pips = entry_spread_pips
    decision.spread_to_risk_ratio = ratio
    if abnormal.get("enabled") and abnormal.get("reject_if_entry_spread_above_max") and entry_spread_pips > float(abnormal["max_entry_spread_pips"]):
        decision.reject("REJECT_ENTRY_SPREAD_ABOVE_MAX")
    if ratio_settings.get("enabled") and ratio_settings.get("reject_if_above_ratio") and ratio > float(ratio_settings["default_max_spread_to_initial_risk_ratio"]):
        decision.reject("REJECT_SPREAD_TO_RISK_RATIO_TOO_HIGH")
    if entry_spread_pips > float(abnormal.get("warning_entry_spread_pips", float("inf"))):
        decision.warnings.append("WARN_ENTRY_SPREAD_ABOVE_WARNING_LEVEL")
    if ratio_settings.get("enabled") and ratio > float(ratio_settings["default_max_spread_to_initial_risk_ratio"]) * .8:
        decision.warnings.append("WARN_SPREAD_TO_RISK_RATIO_ELEVATED")
    return decision
