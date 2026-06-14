from types import SimpleNamespace

from src.broker.ig.ig_streaming_client import IGStreamingClient


class FakeDetails:
    def setUser(self, value):
        self.user = value

    def setPassword(self, value):
        self.password = value


class FakeClient:
    def __init__(self, endpoint, adapter):
        self.endpoint, self.adapter = endpoint, adapter
        self.connectionDetails = FakeDetails()
        self.subscriptions = []

    def addListener(self, listener):
        self.listener = listener

    def connect(self):
        pass

    def subscribe(self, subscription):
        self.subscriptions.append(subscription)

    def disconnect(self):
        pass


class FakeSubscription:
    def __init__(self, mode, items, fields):
        self.mode, self.items, self.fields = mode, items, fields

    def addListener(self, listener):
        self.listener = listener


def test_streaming_uses_price_and_chart_items(monkeypatch):
    config = SimpleNamespace(
        streaming_mode="PRICE", stream_price_fields=("BIDPRICE1", "ASKPRICE1"),
        stream_chart_tick_fields=("BID", "OFR"),
    )
    session = SimpleNamespace(
        lightstreamer_endpoint="https://stream", account_id="ABC", cst="cst", security_token="xst"
    )
    client = IGStreamingClient(config, session)
    monkeypatch.setattr(client, "_library", lambda: (FakeClient, FakeSubscription))
    client.connect()
    price = client.subscribe_price("USDJPY", object())
    chart = client.subscribe_chart_ticks("USDJPY", object())
    assert price.items == ["PRICE:ABC:USDJPY"]
    assert chart.items == ["CHART:USDJPY:TICK"]
    assert all("MARKET:" not in item for subscription in (price, chart) for item in subscription.items)
