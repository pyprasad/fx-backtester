#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.broker.ig.config import load_ig_demo_config
from src.broker.ig.ig_auth import create_session, logout
from src.broker.ig.ig_demo_execution import DEMO_CONFIRMATION_PHRASE, place_demo_test_order
from src.broker.ig.ig_market_rules import IGMarketRules, extract_market_rules
from src.broker.ig.ig_position_sizing import active_account
from src.broker.ig.ig_rest_client import IGRestClient
from src.broker.ig.models import DryRunOrder
from src.broker.ig.token_store import load_session, save_session


DEFAULT_EPIC = "CS.D.USDJPY.TODAY.IP"
DEFAULT_DISTANCE_PIPS = 6.0
REPORT_NAME = "six_pip_demo_order_test.json"


def _open_positions_for_epic(positions: dict, epic: str) -> list[dict]:
    result = []
    for item in positions.get("positions", []):
        market = item.get("market", {})
        if market.get("epic") == epic:
            result.append(item)
    return result


def build_six_pip_order(
    *,
    rules: IGMarketRules,
    direction: str,
    size: float | None,
    distance_pips: float = DEFAULT_DISTANCE_PIPS,
) -> DryRunOrder:
    direction = direction.upper()
    errors = []
    if direction not in {"BUY", "SELL"}:
        errors.append("DIRECTION_MUST_BE_BUY_OR_SELL")
    if rules.status.upper() != "TRADEABLE":
        errors.append("MARKET_NOT_TRADEABLE")
    if rules.delayed:
        errors.append("DELAYED_PRICES")
    if rules.min_stop_distance_pips is None:
        errors.append("MIN_STOP_DISTANCE_UNAVAILABLE")
    elif distance_pips < rules.min_stop_distance_pips:
        errors.append("STOP_DISTANCE_BELOW_BROKER_MINIMUM")
    if rules.min_limit_distance_pips is None:
        errors.append("MIN_LIMIT_DISTANCE_UNAVAILABLE")
    elif distance_pips < rules.min_limit_distance_pips:
        errors.append("LIMIT_DISTANCE_BELOW_BROKER_MINIMUM")
    if rules.unit and rules.unit != "AMOUNT":
        errors.append(f"UNSUPPORTED_IG_UNIT_{rules.unit}")

    min_size = float(rules.min_deal_size or 0)
    deal_size = float(size) if size is not None else min_size
    if deal_size <= 0:
        errors.append("INVALID_DEAL_SIZE")
    if min_size and deal_size < min_size:
        errors.append("SIZE_BELOW_BROKER_MINIMUM")

    order = DryRunOrder(
        deal_reference=f"dry-{uuid4().hex[:25]}",
        epic=rules.epic,
        direction=direction,
        size=deal_size,
        order_type="MARKET",
        level=None,
        stop_distance=distance_pips,
        stop_level=None,
        limit_distance=distance_pips,
        limit_level=None,
        currency=rules.currency or "GBP",
        force_open=True,
        guaranteed_stop=False,
        time_in_force="FILL_OR_KILL",
        expiry=rules.expiry or "-",
        validation_errors=errors,
        validation_warnings=[],
    )
    order.validation_status = "READY_FOR_DEMO_DRY_RUN" if not errors else "NOT_READY"
    return order


def write_report(output_dir: Path, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / REPORT_NAME
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place a fail-closed IG DEMO-only USDJPY order with 6-pip stop and limit distances."
    )
    parser.add_argument("--env-file", default=".env.demo")
    parser.add_argument("--epic", default=DEFAULT_EPIC)
    parser.add_argument("--direction", choices=["BUY", "SELL"], default="SELL")
    parser.add_argument("--distance-pips", type=float, default=DEFAULT_DISTANCE_PIPS)
    parser.add_argument("--size", type=float, help="IG AMOUNT size. Defaults to broker minimum deal size.")
    parser.add_argument("--confirm", required=True)
    parser.add_argument(
        "--allow-existing-position",
        action="store_true",
        help="Allow placing the test order even if an open position already exists for the EPIC.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_ig_demo_config(args.env_file)
    if not config.order_execution_enabled or config.dry_run_only:
        raise RuntimeError(
            "Set IG_ORDER_EXECUTION_ENABLED=true and IG_DRY_RUN_ONLY=false in .env.demo "
            "before placing an explicitly confirmed DEMO order."
        )
    if args.confirm != DEMO_CONFIRMATION_PHRASE:
        raise RuntimeError(f"Explicit confirmation required: {DEMO_CONFIRMATION_PHRASE}")

    session = load_session(config.token_cache_path) if config.token_cache_enabled else None
    session = session or create_session(config)
    if config.token_cache_enabled:
        save_session(session, config.token_cache_path)
    client = IGRestClient(config, session)
    try:
        if config.account_id and config.account_id != client.session.account_id:
            raise RuntimeError("Configured account does not match the authenticated IG DEMO account")

        accounts = client.get_accounts()
        if not active_account(accounts, client.session.account_id):
            raise RuntimeError("Unable to resolve active IG DEMO account")

        rules = extract_market_rules(client.get_market(args.epic))
        open_positions = _open_positions_for_epic(client.get_open_positions(), args.epic)
        if open_positions and not args.allow_existing_position:
            raise RuntimeError(
                f"Refusing to place DEMO test order because {len(open_positions)} open position(s) "
                f"already exist for {args.epic}. Pass --allow-existing-position only if intentional."
            )

        order = build_six_pip_order(
            rules=rules,
            direction=args.direction,
            size=args.size,
            distance_pips=args.distance_pips,
        )
        context = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "environment": "DEMO",
            "execution_type": "SIX_PIP_ATTACHED_STOP_LIMIT_DEMO_TEST",
            "strategy_signal_used": False,
            "epic": args.epic,
            "direction": args.direction,
            "distance_pips": args.distance_pips,
            "market_rules": {
                "status": rules.status,
                "currency": rules.currency,
                "unit": rules.unit,
                "min_stop_distance_pips": rules.min_stop_distance_pips,
                "min_limit_distance_pips": rules.min_limit_distance_pips,
                "min_deal_size": rules.min_deal_size,
            },
            "open_positions_for_epic_before_order": len(open_positions),
            "dry_run_order": {
                "payload": order.payload(),
                "validation_status": order.validation_status,
                "validation_errors": order.validation_errors,
                "validation_warnings": order.validation_warnings,
            },
        }
        if order.validation_status != "READY_FOR_DEMO_DRY_RUN":
            report = write_report(config.audit_output_path, {**context, "order_sent": False})
            raise RuntimeError(
                f"DEMO order blocked by validation: {', '.join(order.validation_errors)}. "
                f"Report: {report}"
            )

        result = place_demo_test_order(
            client,
            order,
            currency_code=order.currency,
            confirmation=args.confirm,
        )
        report = write_report(config.audit_output_path, {**context, "order_sent": True, "execution": result})
        print(f"IG DEMO six-pip order test report: {report}")
        print(json.dumps({
            "accepted": result.get("accepted"),
            "deal_status": result.get("deal_status"),
            "deal_id": result.get("deal_id"),
            "deal_reference": result.get("deal_reference"),
            "reason": result.get("reason"),
            "report": str(report),
        }, indent=2))
        return 0
    finally:
        if not config.token_cache_enabled:
            logout(client.session, config)


if __name__ == "__main__":
    raise SystemExit(main())
