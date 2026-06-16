import json
from dataclasses import replace
from io import BytesIO
from urllib.error import HTTPError

import pytest

from src.broker.ig.config import IGDemoConfig
from src.broker.ig.ig_auth import create_session
from src.broker.ig.ig_rest_client import IGAuthenticationError, IGRestClient, request_json


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


def test_rest_client_sends_session_headers(tmp_path):
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


def test_create_demo_position_requires_execution_mode_and_posts_v2(tmp_path):
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return Response({"dealReference": "demo-reference"})

    cfg = config(tmp_path)
    session = create_session(cfg, lambda *_args, **_kwargs: Response(
        {"currentAccountId": "ABC123"}, {"CST": "cst", "X-SECURITY-TOKEN": "xst"}
    ))
    with pytest.raises(ValueError, match="not enabled"):
        IGRestClient(cfg, session, opener).create_demo_position({})

    execution = replace(cfg, order_execution_enabled=True, dry_run_only=False)
    response = IGRestClient(execution, session, opener).create_demo_position({"epic": "USDJPY"})

    assert response["dealReference"] == "demo-reference"
    assert requests[0].method == "POST"
    assert requests[0].headers["Version"] == "2"


def test_historical_prices_uses_resolution_numpoints_path(tmp_path):
    requests = []

    def opener(request, timeout):
        requests.append(request)
        return Response({"prices": []})

    cfg = config(tmp_path)
    session = create_session(cfg, lambda *_args, **_kwargs: Response(
        {"currentAccountId": "ABC123"}, {"CST": "cst", "X-SECURITY-TOKEN": "xst"}
    ))

    IGRestClient(cfg, session, opener).get_historical_prices("EPIC", "HOUR", 300)

    assert requests[0].full_url.endswith("/prices/EPIC/HOUR/300")
    assert requests[0].headers["Version"] == "2"


def test_authentication_error_includes_ig_error_code():
    def opener(request, timeout):
        raise HTTPError(
            request.full_url, 401, "Unauthorized", {},
            BytesIO(b'{"errorCode":"error.security.client-token-invalid"}'),
        )

    with pytest.raises(
        IGAuthenticationError, match=r"401.*error\.security\.client-token-invalid"
    ) as raised:
        request_json("https://demo/session", "POST", {}, {}, opener=opener)
    assert raised.value.status_code == 401
    assert raised.value.error_code == "error.security.client-token-invalid"
