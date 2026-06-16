from dataclasses import asdict, dataclass
from typing import Any


def _value(data: dict, *paths, default=None):
    for path in paths:
        current = data
        for key in path.split("."):
            current = current.get(key, {}) if isinstance(current, dict) else {}
        if current not in ({}, None, ""):
            return current
    return default


def _distance(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        value = value.get("value")
    return float(value) if value not in (None, "") else None


@dataclass
class IGMarketRules:
    epic: str
    name: str
    status: str
    expiry: str
    currency: str
    pip_size: float
    unit: str
    lot_size: float | None
    min_stop_distance_pips: float | None
    min_limit_distance_pips: float | None
    min_deal_size: float | None
    max_deal_size: float | None
    margin_factor: float | None
    controlled_risk_allowed: bool | None
    streaming_prices_available: bool | None
    delayed: bool
    decimal_places_factor: int | None
    scaling_factor: float | None
    raw: dict[str, Any]

    def validation(self, strategy_min_risk_pips: float = 3.0) -> dict:
        errors, warnings = [], []
        if self.status.upper() != "TRADEABLE":
            errors.append("MARKET_NOT_TRADEABLE")
        if self.delayed:
            errors.append("DELAYED_PRICES")
        if self.min_stop_distance_pips is None:
            warnings.append("MIN_STOP_DISTANCE_UNAVAILABLE")
        elif self.min_stop_distance_pips > strategy_min_risk_pips:
            errors.append("BROKER_MIN_STOP_EXCEEDS_STRATEGY_MIN_RISK")
        elif self.min_stop_distance_pips < 2:
            warnings.append("BROKER_MIN_STOP_BELOW_RESEARCH_ASSUMPTION")
        if self.pip_size != 0.01:
            errors.append("UNEXPECTED_PIP_SIZE")
        if self.streaming_prices_available is False:
            errors.append("STREAMING_PRICES_UNAVAILABLE")
        return {"ready": not errors, "errors": errors, "warnings": warnings}

    def to_dict(self) -> dict:
        return asdict(self)


def extract_market_rules(metadata: dict, expected_pip_size: float = 0.01) -> IGMarketRules:
    instrument, snapshot, dealing = (
        metadata.get("instrument", {}), metadata.get("snapshot", {}), metadata.get("dealingRules", {})
    )
    currencies = instrument.get("currencies") or []
    default_currency = next(
        (item for item in currencies if isinstance(item, dict) and item.get("isDefault")),
        None,
    )
    currency_source = default_currency or (currencies[0] if currencies and isinstance(currencies[0], dict) else {})
    currency = currency_source.get("code", "")
    return IGMarketRules(
        epic=_value(metadata, "instrument.epic", "epic", default=""),
        name=_value(metadata, "instrument.name", "instrumentName", default=""),
        status=_value(metadata, "snapshot.marketStatus", "marketStatus", default="UNKNOWN"),
        expiry=_value(metadata, "instrument.expiry", "expiry", default="-"),
        currency=currency or _value(metadata, "currency", default=""),
        pip_size=float(_value(metadata, "instrument.pipSize", default=expected_pip_size)),
        unit=_value(metadata, "instrument.unit", default=""),
        lot_size=_distance(instrument.get("lotSize")),
        min_stop_distance_pips=_distance(dealing.get("minNormalStopOrLimitDistance")),
        min_limit_distance_pips=_distance(dealing.get("minNormalStopOrLimitDistance")),
        min_deal_size=_distance(dealing.get("minDealSize")),
        max_deal_size=_distance(dealing.get("maxStopOrLimitDistance")),
        margin_factor=_distance(instrument.get("marginFactor")),
        controlled_risk_allowed=instrument.get("controlledRiskAllowed"),
        streaming_prices_available=instrument.get("streamingPricesAvailable"),
        delayed=bool(snapshot.get("delayTime", 0)),
        decimal_places_factor=_value(metadata, "instrument.decimalPlacesFactor", "decimalPlacesFactor"),
        scaling_factor=_distance(_value(metadata, "instrument.scalingFactor", "scalingFactor")),
        raw=metadata,
    )
