from datetime import datetime, timezone

from src.broker.ig.ig_subscriptions import normalise_price_update
from src.broker.ig.ig_tick_store import IGDemoTickStore, latest_tick
from src.data.tick_loader import load_ticks
import pytest


class PriceUpdate:
    values = {"BIDPRICE1": "150", "ASKPRICE1": "150.01", "TIMESTAMP": "1718472000000"}

    def getValue(self, name):
        if name not in self.values:
            raise ValueError("unknown field")
        return self.values[name]


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
    stored = latest_tick(tmp_path)
    assert stored.epic == "USDJPY"
    assert stored.raw["normalization_price_scale_divisor"] == 1
    assert load_ticks(path.parent, path.name).height == 2


def test_scaled_bid_offer_is_normalised_and_spread_is_seven_pips():
    tick = normalise_price_update(
        {"BID": "16018", "OFFER": "16025", "UPDATE_TIME": "21:58:59"},
        "USDJPY", price_scale_divisor=100,
    )
    assert tick.bid == 160.18
    assert tick.ask == 160.25
    assert tick.spread_pips == 7
    assert tick.raw["normalization_price_scale_divisor"] == 100


def test_price_timestamp_accepts_epoch_milliseconds():
    tick = normalise_price_update(
        {"BIDPRICE1": "150", "ASKPRICE1": "150.01", "TIMESTAMP": "1718472000000"},
        "USDJPY",
    )

    assert tick.timestamp_utc.isoformat() == "2024-06-15T17:20:00+00:00"


def test_price_update_ignores_unsubscribed_fallback_fields():
    tick = normalise_price_update(PriceUpdate(), "USDJPY")

    assert tick.bid == 150
    assert tick.ask == 150.01


def test_unconfirmed_scaled_fx_price_is_rejected():
    with pytest.raises(ValueError, match="Unconfirmed scaled FX price"):
        normalise_price_update({"BID": "16018", "OFFER": "16025"}, "USDJPY")


def test_tick_store_moves_to_v2_file_when_existing_csv_has_legacy_schema(tmp_path):
    tick = normalise_price_update({"BIDPRICE1": "150", "ASKPRICE1": "150.01"}, "USDJPY")
    tick.timestamp_utc = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)
    folder = tmp_path / "2026-06-15"
    folder.mkdir()
    (folder / "usdjpy_demo_ticks_20260615.csv").write_text("timestamp,bid,ask\n")

    path = IGDemoTickStore(tmp_path).append(tick)

    assert path.name == "usdjpy_demo_ticks_20260615_v2.csv"
    assert latest_tick(tmp_path).raw["normalization_price_scale_divisor"] == 1
