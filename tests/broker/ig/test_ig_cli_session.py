from types import SimpleNamespace

from src.broker.ig import ig_cli


def test_release_session_keeps_cached_session(monkeypatch):
    calls = []
    monkeypatch.setattr(ig_cli, "logout", lambda session, config: calls.append(session))

    ig_cli._release_session(SimpleNamespace(token_cache_enabled=True), object())

    assert calls == []


def test_release_session_logs_out_uncached_session(monkeypatch):
    session = object()
    calls = []
    monkeypatch.setattr(ig_cli, "logout", lambda value, config: calls.append(value))

    ig_cli._release_session(SimpleNamespace(token_cache_enabled=False), session)

    assert calls == [session]


def test_streaming_uses_rest_client_refreshed_session(monkeypatch):
    original_session = SimpleNamespace(account_id="OLD")
    refreshed_session = SimpleNamespace(account_id="NEW")
    config = SimpleNamespace(
        token_cache_enabled=True,
        tick_output_path="unused",
        price_scale_divisor=None,
    )

    class Client:
        session = original_session

        def get_market(self, epic):
            self.session = refreshed_session
            return {"instrument": {"epic": epic}}

    seen = {}

    class Streaming:
        def __init__(self, _config, session):
            seen["session"] = session
            self.status = "CONNECTED"

        def connect(self):
            pass

        def subscribe_price(self, epic, listener):
            pass

        def disconnect(self):
            pass

    monkeypatch.setattr(ig_cli, "_connect", lambda _env: (config, original_session, Client()))
    monkeypatch.setattr(ig_cli, "IGDemoTickStore", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(ig_cli, "extract_market_rules", lambda _market: SimpleNamespace(pip_size=0.01))
    monkeypatch.setattr(ig_cli, "IGStreamingClient", Streaming)
    monkeypatch.setattr(ig_cli.time, "sleep", lambda _seconds: None)

    ig_cli.stream_ticks(".env.demo", "USDJPY", 0)

    assert seen["session"] is refreshed_session
