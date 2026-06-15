import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import load_ig_demo_config
from .ig_auth import create_session, logout
from .ig_demo_readiness import evaluate_demo_readiness, write_readiness_report
from .ig_demo_execution import place_demo_test_order, write_demo_execution_report
from .ig_market_discovery import (
    discover_usdjpy,
    write_market_discovery_report,
    write_market_rules_report,
)
from .ig_market_rules import extract_market_rules
from .ig_order_dry_run import build_dry_run_order, write_dry_run_report
from .ig_rest_client import IGRestClient
from .ig_streaming_client import IGStreamingClient
from .ig_subscriptions import ChartTickListener, PriceUpdateListener
from .ig_tick_store import IGDemoTickStore, latest_tick
from .token_store import load_session, save_session

logger = logging.getLogger(__name__)


def _connect(env_file):
    config = load_ig_demo_config(env_file)
    session = load_session(config.token_cache_path) if config.token_cache_enabled else None
    session = session or create_session(config)
    if config.token_cache_enabled:
        save_session(session, config.token_cache_path)
    return config, session, IGRestClient(config, session)


def _release_session(config, session):
    if not config.token_cache_enabled:
        logout(session, config)


def auth_check(env_file):
    config, session, client = _connect(env_file)
    try:
        accounts = client.get_accounts()
        result = {"config": config.redacted(), "session": session.redacted(), "accounts_retrieved": bool(accounts)}
        print(json.dumps(result, indent=2))
        return result
    finally:
        _release_session(config, client.session)


def market_discovery(env_file, market):
    config, session, client = _connect(env_file)
    try:
        metadata, warnings = discover_usdjpy(client, config, market)
        report = write_market_discovery_report(config.audit_output_path, metadata, warnings)
        print(f"IG DEMO market discovery report: {report}")
        return metadata
    finally:
        _release_session(config, client.session)


def market_rules(env_file, epic):
    config, session, client = _connect(env_file)
    try:
        rules = extract_market_rules(client.get_market(epic))
        report = write_market_rules_report(config.audit_output_path, rules)
        print(f"IG DEMO market rules report: {report}")
        return rules
    finally:
        _release_session(config, client.session)


def stream_ticks(env_file, epic, duration_seconds, chart=False):
    config, session, client = _connect(env_file)
    store, count = IGDemoTickStore(config.tick_output_path, jsonl=True), 0

    def on_tick(tick):
        nonlocal count
        store.append(tick)
        count += 1
        if count == 1:
            logger.info(
                "First IG DEMO tick | epic=%s | source=%s | spread_pips=%.4f | delayed=%s",
                epic, tick.source, tick.spread_pips, tick.delayed,
            )

    streaming = None
    try:
        rules = extract_market_rules(client.get_market(epic))
        streaming = IGStreamingClient(config, client.session)
        streaming.connect()
        if chart:
            streaming.subscribe_chart_ticks(epic, ChartTickListener(
                epic, on_tick, rules.pip_size, config.price_scale_divisor
            ))
        else:
            streaming.subscribe_price(epic, PriceUpdateListener(
                epic, on_tick, rules.pip_size, config.price_scale_divisor
            ))
        time.sleep(duration_seconds)
        print(json.dumps({"epic": epic, "tick_count": count, "status": streaming.status}, default=str))
        return count
    finally:
        if streaming:
            streaming.disconnect()
        _release_session(config, client.session)


def dry_run_order(env_file, strategy_path, epic):
    config, session, client = _connect(env_file)
    try:
        strategy = yaml.safe_load(Path(strategy_path).read_text())
        rules = extract_market_rules(client.get_market(epic))
        tick = latest_tick(config.tick_output_path)
        if tick is None or tick.epic != epic:
            raise RuntimeError("No stored latest tick exists for the requested EPIC; run streaming first")
        if abs((datetime.now(timezone.utc) - tick.timestamp_utc).total_seconds()) > 300:
            raise RuntimeError("DEMO order blocked because the latest stored tick is stale")
        risk_pips = max(
            float(strategy["broker_guardrails"]["min_initial_risk_pips"]),
            float(rules.min_stop_distance_pips or 0),
        )
        stop = tick.bid + risk_pips * strategy["strategy"]["pip_size"]
        target = tick.bid - risk_pips * strategy["risk_management"]["final_target_r"] * strategy["strategy"]["pip_size"]
        positions = client.get_open_positions().get("positions", [])
        order = build_dry_run_order(
            signal={"direction": "SELL", "stop_price": stop, "target_price": target},
            market_rules=rules, strategy=strategy, latest_tick=tick, size=rules.min_deal_size or 1,
            open_positions=len(positions),
        )
        report = write_dry_run_report(config.audit_output_path / "dry_run_order_usdjpy.json", order)
        print(f"IG DEMO dry-run order report: {report}")
        return order
    finally:
        _release_session(config, client.session)


def place_demo_test_order_cli(env_file, strategy_path, epic, confirmation):
    config, session, client = _connect(env_file)
    try:
        if not config.order_execution_enabled or config.dry_run_only:
            raise RuntimeError(
                "Enable IG_ORDER_EXECUTION_ENABLED=true and IG_DRY_RUN_ONLY=false "
                "to permit an explicitly confirmed DEMO test order"
            )
        if config.account_id and config.account_id != client.session.account_id:
            raise RuntimeError("Configured account does not match the authenticated IG DEMO account")
        strategy = yaml.safe_load(Path(strategy_path).read_text())
        rules = extract_market_rules(client.get_market(epic))
        tick = latest_tick(config.tick_output_path)
        if tick is None or tick.epic != epic:
            raise RuntimeError("No stored latest tick exists for the requested EPIC; run streaming first")
        if abs((datetime.now(timezone.utc) - tick.timestamp_utc).total_seconds()) > 300:
            raise RuntimeError("DEMO order blocked because the latest stored tick is stale")
        positions = client.get_open_positions().get("positions", [])
        accounts = client.get_accounts().get("accounts", [])
        account = next(
            (item for item in accounts if item.get("accountId") == client.session.account_id),
            None,
        )
        if not account or not account.get("currency"):
            raise RuntimeError("Unable to resolve active IG DEMO account currency")
        risk_pips = max(
            float(strategy["broker_guardrails"]["min_initial_risk_pips"]),
            float(rules.min_stop_distance_pips or 0),
        )
        order = build_dry_run_order(
            signal={
                "direction": "SELL",
                "stop_price": tick.bid + risk_pips * strategy["strategy"]["pip_size"],
                "target_price": tick.bid - risk_pips * strategy["risk_management"]["final_target_r"]
                * strategy["strategy"]["pip_size"],
            },
            market_rules=rules,
            strategy=strategy,
            latest_tick=tick,
            size=rules.min_deal_size or 1,
            open_positions=len(positions),
        )
        if order.validation_status != "READY_FOR_DEMO_DRY_RUN":
            raise RuntimeError(
                f"DEMO order blocked by validation: {', '.join(order.validation_errors)}"
            )
        result = place_demo_test_order(
            client, order, currency_code=account["currency"], confirmation=confirmation
        )
        report = write_demo_execution_report(config.audit_output_path, result)
        print(f"IG DEMO execution test report: {report}")
        return result
    finally:
        _release_session(config, client.session)


def readiness(env_file, strategy_path):
    config = load_ig_demo_config(env_file, require_credentials=False)
    strategy = yaml.safe_load(Path(strategy_path).read_text())
    session = accounts = rules = order = None
    tick = latest_tick(config.tick_output_path)
    client = None
    try:
        if config.api_key and config.username and config.password:
            session = load_session(config.token_cache_path) if config.token_cache_enabled else None
            session = session or create_session(config)
            if config.token_cache_enabled:
                save_session(session, config.token_cache_path)
            client = IGRestClient(config, session)
            accounts = client.get_accounts()
            metadata, _warnings = discover_usdjpy(client, config)
            rules = extract_market_rules(metadata)
            if tick and tick.epic == rules.epic:
                risk = max(strategy["broker_guardrails"]["min_initial_risk_pips"], rules.min_stop_distance_pips or 0)
                order = build_dry_run_order(
                    signal={
                        "direction": "SELL",
                        "stop_price": tick.bid + risk * strategy["strategy"]["pip_size"],
                        "target_price": tick.bid - risk * strategy["risk_management"]["final_target_r"] * strategy["strategy"]["pip_size"],
                    },
                    market_rules=rules, strategy=strategy, latest_tick=tick,
                    size=rules.min_deal_size or 1,
                    open_positions=len(client.get_open_positions().get("positions", [])),
                )
    except Exception as exc:
        logger.warning("IG DEMO readiness dependency failed | error=%s", exc)
    finally:
        if session:
            _release_session(config, client.session if client else session)
    result = evaluate_demo_readiness(
        config=config, session=session, accounts=accounts, market_rules=rules,
        first_tick=tick, dry_run_order=order, strategy=strategy,
    )
    report = write_readiness_report(config.audit_output_path, result)
    print(f"IG DEMO readiness report: {report}")
    return result
