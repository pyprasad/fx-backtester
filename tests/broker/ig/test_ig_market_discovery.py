from types import SimpleNamespace

from src.broker.ig.ig_market_discovery import discover_usdjpy


class Client:
    def search_markets(self, _term):
        return {"markets": [
            {"epic": "BAD", "instrumentName": "USD/JPY Forward", "marketStatus": "CLOSED", "expiry": "JUN-26"},
            {"epic": "GOOD", "instrumentName": "USD/JPY", "marketStatus": "TRADEABLE", "expiry": "-", "instrumentType": "CURRENCIES"},
        ]}

    def get_market(self, epic):
        return {"instrument": {"epic": epic}}


def test_discovery_selects_tradeable_currency_market():
    metadata, warnings = discover_usdjpy(Client(), SimpleNamespace(market_epic="", market_search_term="USD/JPY"))
    assert metadata["instrument"]["epic"] == "GOOD"
    assert not warnings
