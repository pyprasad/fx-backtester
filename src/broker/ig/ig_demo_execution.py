import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .ig_rest_client import IGAPIError
from .models import DryRunOrder

DEMO_CONFIRMATION_PHRASE = "PLACE_DEMO_ORDER"
LIVE_CONFIRMATION_PHRASE = "PLACE_LIVE_ORDER"


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
    required_confirmation = (
        LIVE_CONFIRMATION_PHRASE if client.config.is_live else DEMO_CONFIRMATION_PHRASE
    )
    if confirmation != required_confirmation:
        raise ValueError(f"Explicit confirmation required: {required_confirmation}")
    payload = create_position_payload(order, currency_code)
    if client.config.is_live:
        payload["dealReference"] = order.deal_reference.replace("dry-", "live-", 1)
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
    deal_id = None
    deal_status = None
    reason = None
    if confirmation_response:
        deal_id = confirmation_response.get("dealId")
        affected = confirmation_response.get("affectedDeals") or []
        if not deal_id and affected:
            deal_id = affected[0].get("dealId")
        deal_status = confirmation_response.get("dealStatus")
        reason = confirmation_response.get("reason")
    return {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "environment": client.config.env,
        "execution_type": (
            "LIVE_STRATEGY_SIGNAL_ORDER" if client.config.is_live
            else "MINIMUM_SIZE_EXECUTION_PLUMBING_TEST"
        ),
        "strategy_signal_used": False,
        "deal_reference": deal_reference,
        "deal_id": deal_id,
        "deal_status": deal_status,
        "reason": reason,
        "confirmed": deal_status in {"ACCEPTED", "REJECTED"},
        "accepted": deal_status == "ACCEPTED",
        "request": payload,
        "submission_response": response,
        "confirmation": confirmation_response,
    }


def write_demo_execution_report(output: str | Path, result: dict, *, symbol: str = "usdjpy") -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"demo_execution_{symbol}.json"
    path.write_text(json.dumps(result, indent=2, default=str))
    return path
