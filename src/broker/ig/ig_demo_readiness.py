import json
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_STATUSES = {"READY_FOR_DEMO_DRY_RUN", "READY_FOR_DEMO_ORDER", "NOT_READY"}


def evaluate_demo_readiness(*, config, session=None, accounts=None, market_rules=None,
                            first_tick=None, dry_run_order=None, strategy=None) -> dict:
    fresh = bool(
        first_tick
        and abs((datetime.now(timezone.utc) - first_tick.timestamp_utc).total_seconds()) <= 300
    )
    selected_guardrail = strategy["broker_guardrails"]["selected_guardrail_candidate"] if strategy else ""
    spread_reject = strategy["spread_guardrails"].get("reject_spread_to_risk_ratio_above") if strategy else None
    strict_candidate = selected_guardrail == "min_risk_3pips_spread_ratio_20pct"
    broker_min_stop = market_rules.min_stop_distance_pips if market_rules else None
    configured_min_risk = strategy["broker_guardrails"]["min_initial_risk_pips"] if strategy else None
    prepared_stop_distance = getattr(dry_run_order, "stop_distance", None)
    effective_risk_covers_broker_minimum = bool(
        market_rules and (
            broker_min_stop is None
            or (configured_min_risk is not None and configured_min_risk >= broker_min_stop)
            or (prepared_stop_distance is not None and prepared_stop_distance >= broker_min_stop)
        )
    )
    checks = {
        "environment_demo_only": config.env == "DEMO" and config.acc_type == "DEMO",
        "dry_run_mode": config.dry_run_only and not config.order_execution_enabled,
        "demo_order_mode": config.order_execution_enabled and not config.dry_run_only,
        "credentials_loaded": bool(config.api_key and config.username and config.password),
        "session_created": session is not None,
        "accounts_retrieved": bool(accounts),
        "active_account_resolved": bool(session and session.account_id),
        "configured_account_matches_session": bool(
            session and (not config.account_id or config.account_id == session.account_id)
        ),
        "lightstreamer_endpoint_available": bool(session and session.lightstreamer_endpoint),
        "market_details_retrieved": market_rules is not None,
        "market_tradeable": bool(market_rules and market_rules.status.upper() == "TRADEABLE"),
        "pip_size_confirmed": bool(market_rules and market_rules.pip_size == 0.01),
        "streaming_prices_not_disabled": bool(
            market_rules and market_rules.streaming_prices_available is not False
        ),
        "min_stop_available_or_research_fallback_documented": bool(market_rules),
        "effective_order_risk_covers_broker_minimum": effective_risk_covers_broker_minimum,
        "first_valid_bid_ask_received": bool(first_tick and first_tick.bid and first_tick.ask),
        "price_scaling_confirmed": bool(
            first_tick and first_tick.raw.get("normalization_price_scale_divisor")
        ),
        "price_tick_fresh": fresh,
        "price_not_delayed": bool(first_tick and not first_tick.delayed),
        "selected_guardrail_candidate_approved": bool(
            selected_guardrail in {"min_risk_3pips", "min_risk_3pips_spread_ratio_20pct"}
        ),
        "strict_spread_to_risk_rejection_active": bool(
            not strict_candidate or spread_reject == 0.20
        ),
        "entry_cutoff_active": bool(strategy and strategy["time_guards"]["block_new_entries_after"] == "21:30"),
        "weekend_force_close_active": bool(
            strategy and strategy["weekend_policy"]["name"] == "force_close_friday_20_30"
        ),
        "funding_awareness_active": bool(strategy and strategy["funding_awareness"]["enabled"]),
        "dry_run_order_valid": bool(dry_run_order and dry_run_order.validation_status == "READY_FOR_DEMO_DRY_RUN"),
        "dry_run_order_not_sent": bool(dry_run_order and dry_run_order.dry_run_only),
        "max_open_positions_one": bool(strategy and strategy["execution"]["max_open_positions"] == 1),
        "risk_per_trade_set": bool(strategy and strategy["risk_management"]["risk_per_trade_percent"] > 0),
        "audit_logging_enabled": bool(config.audit_output_path),
        "kill_switch_placeholder_documented": True,
        "live_account_support_disabled": config.env == "DEMO",
    }
    required = [
        key for key in checks
        if key not in {"kill_switch_placeholder_documented", "dry_run_mode", "demo_order_mode"}
    ]
    shared_ready = all(checks[key] for key in required)
    if shared_ready and checks["demo_order_mode"]:
        status = "READY_FOR_DEMO_ORDER"
    elif shared_ready and checks["dry_run_mode"]:
        status = "READY_FOR_DEMO_DRY_RUN"
    else:
        status = "NOT_READY"
    failed_checks = [key for key in required if not checks[key]]
    if not checks["dry_run_mode"] and not checks["demo_order_mode"]:
        failed_checks.extend(["dry_run_mode", "demo_order_mode"])
    return {
        "status": status, "checks": checks,
        "failed_checks": failed_checks,
        "highest_allowed_status": "READY_FOR_DEMO_ORDER" if checks["demo_order_mode"] else "READY_FOR_DEMO_DRY_RUN",
        "broker_min_stop_distance_pips": broker_min_stop,
        "configured_min_initial_risk_pips": configured_min_risk,
        "prepared_order_stop_distance_pips": prepared_stop_distance,
        "dry_run_validation_errors": getattr(dry_run_order, "validation_errors", []),
        "ready_for_live": False, "orders_sent": False,
    }


def write_readiness_report(output: str | Path, result: dict) -> Path:
    if result["status"] not in ALLOWED_STATUSES:
        raise ValueError("FX-2I readiness must never produce a live-trading status")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "ig_demo_readiness_report.json").write_text(json.dumps(result, indent=2))
    path = output / "ig_demo_readiness_report.md"
    checks = "\n".join(f"- [{'x' if value else ' '}] {key}" for key, value in result["checks"].items())
    path.write_text(
        f"# IG DEMO Readiness Report\n\nStatus: **{result['status']}**\n\n{checks}\n\n"
        "No order was sent by this readiness command. READY_FOR_LIVE is not an allowed FX-2I status.\n"
    )
    return path
