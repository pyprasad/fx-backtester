from datetime import datetime, timezone

from .models import InternalTick


def _fields(update, names: tuple[str, ...]) -> dict:
    if isinstance(update, dict):
        return update
    return {name: update.getValue(name) for name in names}


def _timestamp(value, *, epoch_ms: bool = False) -> datetime:
    if epoch_ms and value not in (None, ""):
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc)
    if value:
        for fmt in ("%H:%M:%S", "%H:%M:%S.%f"):
            try:
                parsed = datetime.strptime(value, fmt).time()
                return datetime.combine(datetime.now(timezone.utc).date(), parsed, timezone.utc)
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def normalise_price_update(update, epic: str, pip_size: float = 0.01) -> InternalTick:
    raw = _fields(update, ("BIDPRICE1", "ASKPRICE1", "TIMESTAMP", "DELAY", "DLG_FLAG", "HIGH", "LOW", "MID_OPEN"))
    bid, ask = float(raw["BIDPRICE1"]), float(raw["ASKPRICE1"])
    return InternalTick(
        _timestamp(raw.get("TIMESTAMP")), bid, ask, (bid + ask) / 2,
        round((ask - bid) / pip_size, 8), "IG_DEMO_PRICE", epic,
        str(raw.get("DELAY", "0")) == "1", raw=raw,
    )


def normalise_chart_tick(update, epic: str, pip_size: float = 0.01) -> InternalTick:
    raw = _fields(update, ("BID", "OFR", "LTP", "UTM"))
    bid, ask = float(raw["BID"]), float(raw["OFR"])
    return InternalTick(
        _timestamp(raw.get("UTM"), epoch_ms=True), bid, ask, (bid + ask) / 2,
        round((ask - bid) / pip_size, 8), "IG_DEMO_CHART_TICK", epic, False, raw=raw,
    )


class PriceUpdateListener:
    def __init__(self, epic: str, callback, pip_size: float = 0.01):
        self.epic, self.callback, self.pip_size = epic, callback, pip_size

    def onItemUpdate(self, update):
        self.callback(normalise_price_update(update, self.epic, self.pip_size))


class ChartTickListener:
    def __init__(self, epic: str, callback, pip_size: float = 0.01):
        self.epic, self.callback, self.pip_size = epic, callback, pip_size

    def onItemUpdate(self, update):
        self.callback(normalise_chart_tick(update, self.epic, self.pip_size))


class AccountUpdateListener:
    def __init__(self, callback):
        self.callback = callback

    def onItemUpdate(self, update):
        self.callback(update)


class TradeUpdateListener(AccountUpdateListener):
    """Read-only listener; never submits or amends orders."""
