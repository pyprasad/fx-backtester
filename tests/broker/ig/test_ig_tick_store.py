from datetime import datetime, timezone

from src.broker.ig.ig_subscriptions import normalise_price_update
from src.broker.ig.ig_tick_store import IGDemoTickStore, latest_tick
from src.data.tick_loader import load_ticks


def test_tick_store_appends_and_calculates_spread(tmp_path):
    tick = normalise_price_update({
        "BIDPRICE1": "150.00", "ASKPRICE1": "150.01", "TIMESTAMP": "12:00:00", "DELAY": "0",
    }, "USDJPY")
    tick.timestamp_utc = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    store = IGDemoTickStore(tmp_path, jsonl=True)
    path = store.append(tick)
    store.append(tick)
    assert tick.spread_pips == 1
    assert len(path.read_text().splitlines()) == 3
    assert latest_tick(tmp_path).epic == "USDJPY"
    assert load_ticks(path.parent, path.name).height == 2
