import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .ig_rest_client import IGAPIError
from .models import DryRunOrder

DEMO_CONFIRMATION_PHRASE = "PLACE_DEMO_ORDER"


def create_position_payload(order: DryRunOrder, currency_code: str) -> dict:
    if order.validation_status != "READY_FOR_DEMO_DRY_RUN":
        raise ValueError("Refusing to create payload for an invalid dry-run order")
    return {
        "currencyCode": currency_code,
        "dealReference": order.deal_reference.replace("dry-", "demo-", 1),
        "direction": order.direction,
        "epic": order.epic,
        "expiry": order.expiry,
        "forceOpen": True,
        "guaranteedStop": False,
        "limitDistance": order.limit_distance,
        "orderType": "MARKET",
        "size": order.size,
        "stopDistance": order.stop_distance,
        "timeInForce": "FILL_OR_KILL",
        "trailingStop": False,
    }


def place_demo_test_order(client, order: DryRunOrder, *, currency_code: str,
                          confirmation: str, attempts: int = 10,
                          poll_interval_seconds: float = 1) -> dict:
    if confirmation != DEMO_CONFIRMATION_PHRASE:
        raise ValueError(f"Explicit confirmation required: {DEMO_CONFIRMATION_PHRASE}")
    payload = create_position_payload(order, currency_code)
    response = client.create_demo_position(payload)
    deal_reference = response.get("dealReference") or payload["dealReference"]
    confirmation_response = None
    for _ in range(attempts):
        try:
            confirmation_response = client.get_confirms(deal_reference)
        except IGAPIError as exc:
            if "404" not in str(exc):
                raise
            time.sleep(poll_interval_seconds)
            continue
        if confirmation_response.get("dealStatus") in {"ACCEPTED", "REJECTED"}:
            break
        time.sleep(poll_interval_seconds)
    return {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "environment": "DEMO",
        "execution_type": "MINIMUM_SIZE_EXECUTION_PLUMBING_TEST",
        "strategy_signal_used": False,
        "request": payload,
        "submission_response": response,
        "confirmation": confirmation_response,
    }


def write_demo_execution_report(output: str | Path, result: dict) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "demo_execution_test.json"
    path.write_text(json.dumps(result, indent=2, default=str))
    return path
