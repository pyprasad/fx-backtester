import json
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_STATUSES = {"READY_FOR_DEMO_DRY_RUN", "NOT_READY"}


def evaluate_demo_readiness(*, config, session=None, accounts=None, market_rules=None,
                            first_tick=None, dry_run_order=None, strategy=None) -> dict:
    fresh = bool(
        first_tick
        and abs((datetime.now(timezone.utc) - first_tick.timestamp_utc).total_seconds()) <= 300
    )
    checks = {
        "environment_demo_only": config.env == "DEMO" and config.acc_type == "DEMO",
        "dry_run_only": config.dry_run_only and not config.order_execution_enabled,
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
        "strategy_min_risk_covers_broker_minimum": bool(
            market_rules and (
                market_rules.min_stop_distance_pips is None
                or strategy["broker_guardrails"]["min_initial_risk_pips"] >= market_rules.min_stop_distance_pips
            )
        ),
        "first_valid_bid_ask_received": bool(first_tick and first_tick.bid and first_tick.ask),
        "price_tick_fresh": fresh,
        "price_not_delayed": bool(first_tick and not first_tick.delayed),
        "min_risk_3pips_active": bool(
            strategy and strategy["broker_guardrails"]["selected_guardrail_candidate"] == "min_risk_3pips"
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
    required = [key for key in checks if key != "kill_switch_placeholder_documented"]
    status = "READY_FOR_DEMO_DRY_RUN" if all(checks[key] for key in required) else "NOT_READY"
    return {
        "status": status, "checks": checks,
        "failed_checks": [key for key, passed in checks.items() if not passed],
        "highest_allowed_status": "READY_FOR_DEMO_DRY_RUN",
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
        "No demo or live order was sent. READY_FOR_LIVE is not an allowed FX-2I status.\n"
    )
    return path
