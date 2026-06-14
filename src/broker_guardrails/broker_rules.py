from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class BrokerMarketRules:
    broker: str
    market: str
    pip_size: float
    min_stop_distance_pips: float
    min_take_profit_distance_pips: float
    overnight_cutoff_time: str
    overnight_cutoff_timezone: str
    wednesday_triple_rollover: bool
    default_spread_pips: float
    default_slippage_pips: float


@dataclass
class GuardrailDecision:
    accepted: bool = True
    rejection_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    initial_risk_pips: float = 0
    entry_spread_pips: float = 0
    spread_to_risk_ratio: float = 0
    min_stop_distance_pips: float = 0
    min_take_profit_distance_pips: float = 0
    timestamp_utc: datetime | None = None
    timestamp_local: datetime | None = None
    notes: str = ""

    def reject(self, reason: str) -> None:
        self.accepted = False
        self.rejection_reasons.append(reason)


def rules_from_config(config: dict) -> BrokerMarketRules:
    distances = config["broker_distance_rules"]
    funding = config["overnight_funding"]
    costs = config["execution_cost_model"]
    return BrokerMarketRules(
        config["broker"], config["market"], float(config["pip_size"]),
        float(distances["min_stop_distance_pips"]), float(distances["min_take_profit_distance_pips"]),
        funding["cutoff_time"], funding["timezone"],
        bool(funding["apply_wednesday_triple_rollover"]), float(costs["default_spread_pips"]),
        float(costs["default_slippage_pips"]),
    )
