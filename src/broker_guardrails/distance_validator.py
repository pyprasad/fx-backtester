from .broker_rules import BrokerMarketRules, GuardrailDecision
from .broker_rules import rules_from_config
from .spread_risk_validator import validate_spread_risk
from .time_guard import validate_entry_time


def price_distance_pips(first: float, second: float, pip_size: float = 0.01) -> float:
    return round(abs(first - second) / pip_size, 8)


def validate_distances(entry: float, stop: float, target: float | None, settings: dict,
                       rules: BrokerMarketRules, decision: GuardrailDecision | None = None) -> GuardrailDecision:
    decision = decision or GuardrailDecision()
    risk = price_distance_pips(entry, stop, rules.pip_size)
    target_pips = price_distance_pips(entry, target, rules.pip_size) if target is not None else None
    decision.initial_risk_pips = risk
    decision.min_stop_distance_pips = rules.min_stop_distance_pips
    decision.min_take_profit_distance_pips = rules.min_take_profit_distance_pips
    distance = settings["broker_distance_rules"]
    minimum = settings["minimum_initial_risk"]
    if distance.get("enabled") and distance.get("reject_if_stop_distance_below_broker_minimum") and risk < rules.min_stop_distance_pips:
        decision.reject("REJECT_BELOW_BROKER_MIN_STOP_DISTANCE")
    if minimum.get("enabled") and minimum.get("reject_if_below_minimum") and risk < float(minimum["default_min_initial_risk_pips"]):
        decision.reject("REJECT_BELOW_MIN_INITIAL_RISK_PIPS")
    if target_pips is not None and distance.get("enabled") and distance.get("reject_if_take_profit_distance_below_broker_minimum") and target_pips < rules.min_take_profit_distance_pips:
        decision.reject("REJECT_BELOW_BROKER_MIN_TP_DISTANCE")
    if risk <= rules.min_stop_distance_pips + 1:
        decision.warnings.append("WARN_INITIAL_RISK_CLOSE_TO_BROKER_MINIMUM")
    if target_pips is not None and target_pips <= rules.min_take_profit_distance_pips + 1:
        decision.warnings.append("WARN_TP_DISTANCE_CLOSE_TO_BROKER_MINIMUM")
    return decision


def evaluate_proposed_signal(timestamp_utc, entry: float, stop: float, target: float | None,
                             entry_spread_pips: float, settings: dict) -> GuardrailDecision:
    decision = validate_entry_time(timestamp_utc, settings)
    decision = validate_distances(entry, stop, target, settings, rules_from_config(settings), decision)
    return validate_spread_risk(entry_spread_pips, settings, decision)
