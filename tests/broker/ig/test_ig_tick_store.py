from datetime import datetime, timezone

from src.broker.ig.ig_subscriptions import (
    ChartTickListener,
    IncompleteTickUpdate,
    normalise_chart_tick,
    normalise_price_update,
)
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


def test_chart_tick_can_merge_partial_updates_with_previous_quote():
    first = normalise_chart_tick(
        {"BID": "16286.8", "OFR": "16287.8", "UTM": "1784725201000"},
        "USDJPY",
        price_scale_divisor=100,
    )
    partial = normalise_chart_tick(
        {"UTM": "1784725202000"},
        "USDJPY",
        price_scale_divisor=100,
        previous_raw=first.raw,
    )

    assert partial.bid == 162.868
    assert partial.ask == 162.878
    assert partial.timestamp_utc.isoformat() == "2026-07-22T13:00:02+00:00"


def test_chart_tick_without_quote_state_is_incomplete():
    with pytest.raises(IncompleteTickUpdate):
        normalise_chart_tick({"UTM": "1784725202000"}, "USDJPY", price_scale_divisor=100)


def test_chart_tick_listener_ignores_initial_partial_then_uses_state():
    ticks = []
    listener = ChartTickListener(
        "USDJPY",
        ticks.append,
        price_scale_divisor=100,
    )

    listener.onItemUpdate({"UTM": "1784725200000"})
    listener.onItemUpdate({"BID": "16286.8", "OFR": "16287.8", "UTM": "1784725201000"})
    listener.onItemUpdate({"UTM": "1784725202000"})

    assert [tick.timestamp_utc.isoformat() for tick in ticks] == [
        "2026-07-22T13:00:01+00:00",
        "2026-07-22T13:00:02+00:00",
    ]
    assert [(tick.bid, tick.ask) for tick in ticks] == [
        (162.868, 162.878),
        (162.868, 162.878),
    ]


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
