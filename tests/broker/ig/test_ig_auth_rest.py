import json

from src.broker.ig.config import IGDemoConfig
from src.broker.ig.ig_auth import create_session
from src.broker.ig.ig_rest_client import IGRestClient


class Response:
    def __init__(self, body, headers=None):
        self.body = json.dumps(body).encode()
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def config(tmp_path):
    return IGDemoConfig(
        "DEMO", "api", "user", "password", "ABC123", "DEMO", "https://demo", True, "PRICE",
        "USD/JPY", "", False, True, tmp_path / "ticks", tmp_path / "audit", "INFO",
    )


def test_auth_extracts_session_tokens_without_exposing_password(tmp_path):
    seen = {}

    def opener(request, timeout):
        seen["request"] = request
        return Response(
            {"currentAccountId": "ABC123", "lightstreamerEndpoint": "https://stream"},
            {"CST": "cst-secret", "X-SECURITY-TOKEN": "xst-secret"},
        )

    session = create_session(config(tmp_path), opener)
    assert session.account_id == "ABC123"
    assert session.redacted()["cst"] == "***"
    assert b"password" not in repr(seen["request"].headers).encode()


def test_rest_client_sends_session_headers_and_only_reads(tmp_path):
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return Response({"accounts": []})

    cfg = config(tmp_path)
    session = create_session(cfg, lambda *_args, **_kwargs: Response(
        {"currentAccountId": "ABC123"}, {"CST": "cst", "X-SECURITY-TOKEN": "xst"}
    ))
    client = IGRestClient(cfg, session, opener)
    assert client.get_accounts() == {"accounts": []}
    assert requests[0].method == "GET"
    assert requests[0].headers["Cst"] == "cst"
    assert not any(hasattr(client, name) for name in ("create_position", "place_order", "open_position"))
