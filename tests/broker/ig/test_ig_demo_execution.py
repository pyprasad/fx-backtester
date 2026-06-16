from types import SimpleNamespace

import pytest

from src.broker.ig.ig_demo_execution import create_position_payload, place_demo_test_order
from src.broker.ig.models import DryRunOrder


def order(status="READY_FOR_DEMO_DRY_RUN"):
    return DryRunOrder(
        deal_reference="dry-1234567890123456789012345",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="SELL",
        size=0.04,
        order_type="MARKET",
        level=None,
        stop_distance=3,
        stop_level=160.38,
        limit_distance=12,
        limit_level=160.23,
        currency="GBP",
        force_open=True,
        guaranteed_stop=False,
        time_in_force="FILL_OR_KILL",
        expiry="DFB",
        validation_status=status,
    )


def test_create_position_payload_matches_ig_v2_contract():
    payload = create_position_payload(order(), "GBP")

    assert payload["currencyCode"] == "GBP"
    assert payload["forceOpen"] is True
    assert payload["stopDistance"] == 3
    assert payload["limitDistance"] == 12
    assert "stopLevel" not in payload
    assert "limitLevel" not in payload
    assert len(payload["dealReference"]) <= 30


def test_create_position_payload_rejects_invalid_order():
    with pytest.raises(ValueError, match="invalid dry-run"):
        create_position_payload(order("NOT_READY"), "GBP")


def test_place_demo_test_order_requires_confirmation_and_audits_result():
    client = SimpleNamespace()
    client.create_demo_position = lambda payload: {"dealReference": payload["dealReference"]}
    client.get_confirms = lambda reference: {
        "dealReference": reference, "dealStatus": "ACCEPTED", "dealId": "DEAL1"
    }

    with pytest.raises(ValueError, match="Explicit confirmation"):
        place_demo_test_order(client, order(), currency_code="GBP", confirmation="no")

    result = place_demo_test_order(
        client, order(), currency_code="GBP", confirmation="PLACE_DEMO_ORDER",
        poll_interval_seconds=0,
    )

    assert result["environment"] == "DEMO"
    assert result["strategy_signal_used"] is False
    assert result["deal_reference"] == "demo-1234567890123456789012345"
    assert result["deal_id"] == "DEAL1"
    assert result["deal_status"] == "ACCEPTED"
    assert result["accepted"] is True
    assert result["confirmation"]["dealStatus"] == "ACCEPTED"


def test_place_demo_test_order_extracts_deal_id_from_affected_deals():
    client = SimpleNamespace()
    client.create_demo_position = lambda payload: {"dealReference": payload["dealReference"]}
    client.get_confirms = lambda reference: {
        "dealReference": reference,
        "dealStatus": "ACCEPTED",
        "affectedDeals": [{"dealId": "AFFECTED1", "status": "OPENED"}],
    }

    result = place_demo_test_order(
        client, order(), currency_code="GBP", confirmation="PLACE_DEMO_ORDER",
        poll_interval_seconds=0,
    )

    assert result["deal_id"] == "AFFECTED1"
