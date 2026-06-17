import logging
import json
from datetime import datetime, timezone

from .models import InternalTick

logger = logging.getLogger(__name__)


def _fields(update, names: tuple[str, ...]) -> dict:
    if isinstance(update, dict):
        return update
    values = {}
    for name in names:
        try:
            values[name] = update.getValue(name)
        except Exception:
            # Lightstreamer raises when a fallback field was not part of this subscription.
            continue
    return values


def _timestamp(value, *, epoch_ms: bool = False) -> datetime:
    if value not in (None, ""):
        text = str(value)
        if epoch_ms or text.replace(".", "", 1).isdigit():
            return datetime.fromtimestamp(float(value) / 1000, timezone.utc)
    if value:
        for fmt in ("%H:%M:%S", "%H:%M:%S.%f"):
            try:
                parsed = datetime.strptime(value, fmt).time()
                return datetime.combine(datetime.now(timezone.utc).date(), parsed, timezone.utc)
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def _normalise_bid_ask(raw: dict, bid_fields: tuple[str, ...], ask_fields: tuple[str, ...],
                       price_scale_divisor: float | None) -> tuple[float, float]:
    def first(fields):
        return next((raw[field] for field in fields if raw.get(field) not in (None, "")), None)

    raw_bid, raw_ask = first(bid_fields), first(ask_fields)
    if raw_bid is None or raw_ask is None:
        raise ValueError(f"Bid/ask fields missing; expected {bid_fields} and {ask_fields}")
    divisor = price_scale_divisor or 1.0
    bid, ask = float(raw_bid) / divisor, float(raw_ask) / divisor
    if bid <= 0 or ask <= 0 or ask < bid:
        raise ValueError(f"Invalid normalized bid/ask: {bid}/{ask}")
    if max(bid, ask) > 1000:
        raise ValueError(
            "Unconfirmed scaled FX price; set IG_PRICE_SCALE_DIVISOR after verifying broker metadata"
        )
    raw["normalization_price_scale_divisor"] = divisor
    return bid, ask


def normalise_price_update(update, epic: str, pip_size: float = 0.01,
                           price_scale_divisor: float | None = None) -> InternalTick:
    names = ("BIDPRICE1", "ASKPRICE1", "BID", "OFFER", "OFR", "TIMESTAMP", "UPDATE_TIME",
             "DELAY", "MARKET_DELAY", "DLG_FLAG", "HIGH", "LOW", "MID_OPEN", "MARKET_STATE")
    raw = _fields(update, names)
    bid, ask = _normalise_bid_ask(
        raw, ("BIDPRICE1", "BID"), ("ASKPRICE1", "OFFER", "OFR"), price_scale_divisor
    )
    return InternalTick(
        _timestamp(raw.get("TIMESTAMP") or raw.get("UPDATE_TIME")), bid, ask, (bid + ask) / 2,
        round((ask - bid) / pip_size, 8), "IG_DEMO_PRICE", epic,
        str(raw.get("DELAY", raw.get("MARKET_DELAY", "0"))) == "1", raw=raw,
    )


def normalise_chart_tick(update, epic: str, pip_size: float = 0.01,
                         price_scale_divisor: float | None = None) -> InternalTick:
    raw = _fields(update, ("BID", "OFR", "LTP", "UTM"))
    bid, ask = _normalise_bid_ask(raw, ("BID",), ("OFR",), price_scale_divisor)
    return InternalTick(
        _timestamp(raw.get("UTM"), epoch_ms=True), bid, ask, (bid + ask) / 2,
        round((ask - bid) / pip_size, 8), "IG_DEMO_CHART_TICK", epic, False, raw=raw,
    )


class PriceUpdateListener:
    def __init__(self, epic: str, callback, pip_size: float = 0.01,
                 price_scale_divisor: float | None = None):
        self.epic, self.callback, self.pip_size = epic, callback, pip_size
        self.price_scale_divisor = price_scale_divisor

    def onItemUpdate(self, update):
        try:
            self.callback(normalise_price_update(
                update, self.epic, self.pip_size, self.price_scale_divisor
            ))
        except Exception:
            logger.exception("IG PRICE update rejected | epic=%s", self.epic)

    def onSubscription(self):
        logger.info("IG PRICE subscription active | epic=%s", self.epic)

    def onSubscriptionError(self, code, message):
        logger.error(
            "IG PRICE subscription failed | epic=%s | code=%s | message=%s",
            self.epic, code, message,
        )


class ChartTickListener:
    def __init__(self, epic: str, callback, pip_size: float = 0.01,
                 price_scale_divisor: float | None = None):
        self.epic, self.callback, self.pip_size = epic, callback, pip_size
        self.price_scale_divisor = price_scale_divisor

    def onItemUpdate(self, update):
        try:
            self.callback(normalise_chart_tick(
                update, self.epic, self.pip_size, self.price_scale_divisor
            ))
        except Exception:
            logger.exception("IG CHART:TICK update rejected | epic=%s", self.epic)

    def onSubscription(self):
        logger.info("IG CHART:TICK subscription active | epic=%s", self.epic)

    def onSubscriptionError(self, code, message):
        logger.error(
            "IG CHART:TICK subscription failed | epic=%s | code=%s | message=%s",
            self.epic, code, message,
        )


class AccountUpdateListener:
    def __init__(self, callback):
        self.callback = callback

    def onItemUpdate(self, update):
        self.callback(update)


class TradeUpdateListener(AccountUpdateListener):
    """Read-only listener; never submits or amends orders."""

    def onItemUpdate(self, update):
        raw = _fields(update, ("CONFIRMS", "OPU", "WOU"))
        for update_type in ("CONFIRMS", "OPU", "WOU"):
            payload = raw.get(update_type)
            if payload in (None, ""):
                continue
            try:
                parsed = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                parsed = {"raw": payload}
            self.callback(update_type, parsed)
