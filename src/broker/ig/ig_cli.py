import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import load_ig_demo_config
from .ig_auth import create_session, logout
from .ig_bot import IGDemoBotRunner
from .ig_candle_cache import CandleCachePaths, load_cached_candles, refresh_candle_cache
from .ig_demo_readiness import evaluate_demo_readiness, write_readiness_report
from .ig_demo_execution import place_demo_test_order, write_demo_execution_report
from .ig_market_discovery import (
    discover_usdjpy,
    write_market_discovery_report,
    write_market_rules_report,
)
from .ig_market_rules import extract_market_rules
from .ig_live_signal import (
    evaluate_live_signal,
    evaluate_live_signal_from_candles,
    runtime_config_from_contract,
    write_live_signal_report,
    write_signal_dry_run_report,
)
from .ig_order_dry_run import build_dry_run_order, write_dry_run_report
from .ig_position_sizing import account_balance, active_account, dynamic_deal_size
from .ig_rest_client import IGRestClient
from .ig_streaming_client import IGStreamingClient
from .ig_subscriptions import ChartTickListener, PriceUpdateListener
from .ig_tick_store import IGDemoTickStore, latest_tick
from .token_store import load_session, save_session

logger = logging.getLogger(__name__)


class HistoricalPriceOnlyClient:
    def __init__(self, client):
        self._client = client

    def get_historical_prices(self, epic: str, resolution: str, num_points: int):
        return self._client.get_historical_prices(epic, resolution, num_points)


def _connect(env_file):
    config = load_ig_demo_config(env_file)
    session = load_session(config.token_cache_path) if config.token_cache_enabled else None
    session = session or create_session(config)
    if config.token_cache_enabled:
        save_session(session, config.token_cache_path)
    return config, session, IGRestClient(config, session)


def _connect_historical_data_client(config):
    if not config.historical_data_override_enabled:
        return None, None, None
    historical_config = config.historical_data_config()
    session = (
        load_session(historical_config.token_cache_path)
        if historical_config.token_cache_enabled else None
    )
    session = session or create_session(historical_config)
    if historical_config.token_cache_enabled:
        save_session(session, historical_config.token_cache_path)
    client = HistoricalPriceOnlyClient(IGRestClient(historical_config, session))
    return historical_config, session, client


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


def _summarize_position(item):
    position = item.get("position", {})
    market = item.get("market", {})
    return {
        "deal_id": position.get("dealId"),
        "deal_reference": position.get("dealReference"),
        "epic": market.get("epic"),
        "instrument_name": market.get("instrumentName"),
        "expiry": market.get("expiry"),
        "market_status": market.get("marketStatus"),
        "direction": position.get("direction"),
        "size": position.get("dealSize") or position.get("size"),
        "level": position.get("level"),
        "currency": position.get("currency"),
        "created_date": position.get("createdDate"),
        "created_date_utc": position.get("createdDateUTC"),
        "controlled_risk": position.get("controlledRisk"),
    }


def open_positions(env_file, epic=None):
    config, session, client = _connect(env_file)
    try:
        positions = client.get_open_positions().get("positions", [])
        rows = [_summarize_position(item) for item in positions]
        if epic:
            rows = [row for row in rows if row["epic"] == epic]
        result = {"open_position_count": len(rows), "epic_filter": epic, "positions": rows}
        path = config.audit_output_path / "open_positions.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, default=str))
        print(json.dumps(result, indent=2, default=str))
        print(f"IG DEMO open positions report: {path}")
        return result
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
        accounts = client.get_accounts()
        account = active_account(accounts, client.session.account_id)
        if not account:
            raise RuntimeError("Unable to resolve active IG DEMO account")
        size, sizing = dynamic_deal_size(
            balance=account_balance(account),
            risk_percent=float(strategy["risk_management"]["risk_per_trade_percent"]),
            stop_distance_pips=risk_pips,
            min_deal_size=rules.min_deal_size,
            instrument_unit=rules.unit,
        )
        order = build_dry_run_order(
            signal={"direction": "SELL", "stop_price": stop, "target_price": target},
            market_rules=rules, strategy=strategy, latest_tick=tick, size=size,
            open_positions=len(positions),
        )
        report = write_dry_run_report(config.audit_output_path / "dry_run_order_usdjpy.json", order, {
            "open_positions": len(positions),
            "broker_min_stop_distance_pips": rules.min_stop_distance_pips,
            "configured_min_initial_risk_pips": strategy["broker_guardrails"]["min_initial_risk_pips"],
            "effective_order_risk_pips": risk_pips,
            "sizing": sizing,
        })
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
        accounts = client.get_accounts()
        account = active_account(accounts, client.session.account_id)
        if not account:
            raise RuntimeError("Unable to resolve active IG DEMO account")
        risk_pips = max(
            float(strategy["broker_guardrails"]["min_initial_risk_pips"]),
            float(rules.min_stop_distance_pips or 0),
        )
        size, sizing = dynamic_deal_size(
            balance=account_balance(account),
            risk_percent=float(strategy["risk_management"]["risk_per_trade_percent"]),
            stop_distance_pips=risk_pips,
            min_deal_size=rules.min_deal_size,
            instrument_unit=rules.unit,
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
            size=size,
            open_positions=len(positions),
        )
        if order.validation_status != "READY_FOR_DEMO_DRY_RUN":
            raise RuntimeError(
                f"DEMO order blocked by validation: {', '.join(order.validation_errors)}"
            )
        if not order.currency:
            raise RuntimeError("Unable to resolve IG market currency for the DEMO order")
        result = place_demo_test_order(
            client, order, currency_code=order.currency, confirmation=confirmation
        )
        result["sizing"] = sizing
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
                account = active_account(accounts, client.session.account_id)
                size, _sizing = dynamic_deal_size(
                    balance=account_balance(account),
                    risk_percent=float(strategy["risk_management"]["risk_per_trade_percent"]),
                    stop_distance_pips=risk,
                    min_deal_size=rules.min_deal_size,
                    instrument_unit=rules.unit,
                ) if account else (rules.min_deal_size or 1, {})
                order = build_dry_run_order(
                    signal={
                        "direction": "SELL",
                        "stop_price": tick.bid + risk * strategy["strategy"]["pip_size"],
                        "target_price": tick.bid - risk * strategy["risk_management"]["final_target_r"] * strategy["strategy"]["pip_size"],
                    },
                    market_rules=rules, strategy=strategy, latest_tick=tick,
                    size=size,
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


def _evaluate_live_signal_with_cache(
    *,
    config,
    client,
    historical_client,
    strategy_path,
    epic,
    runtime_strategy_config,
    history_points,
    cache_path,
    refresh_points,
):
    runtime_config, contract = runtime_config_from_contract(strategy_path, runtime_strategy_config)
    rules = extract_market_rules(client.get_market(epic))
    paths = CandleCachePaths(Path(cache_path))
    points = history_points if not paths.exists() else refresh_points
    cache_summary = refresh_candle_cache(
        client=historical_client or client,
        epic=epic,
        paths=paths,
        scale_divisor=config.price_scale_divisor,
        history_points=points,
        keep_last=history_points,
    )
    hour, four_hour = load_cached_candles(paths)
    result = evaluate_live_signal_from_candles(
        client=client,
        config=runtime_config,
        contract=contract,
        epic=epic,
        market_rules=rules,
        hour=hour,
        four_hour=four_hour,
        execution_tick=latest_tick(config.tick_output_path),
    )
    result["cache"] = cache_summary
    return result


def live_signal_check(env_file, strategy_path, epic, runtime_strategy_config, history_points,
                      cache_path="data/live_cache/ig", refresh_points=10):
    config, session, client = _connect(env_file)
    historical_config = historical_session = historical_client = None
    try:
        historical_config, historical_session, historical_client = _connect_historical_data_client(config)
        result = _evaluate_live_signal_with_cache(
            config=config,
            client=client,
            historical_client=historical_client,
            strategy_path=strategy_path,
            epic=epic,
            runtime_strategy_config=runtime_strategy_config,
            history_points=history_points,
            cache_path=cache_path,
            refresh_points=refresh_points,
        )
        report = write_live_signal_report(config.audit_output_path, result)
        print(f"IG DEMO live signal report: {report}")
        print(json.dumps({
            "status": result["status"],
            "latest_closed_1h_candle": result.get("latest_closed_1h_candle"),
            "signal_count": result.get("signal_count"),
            "order_sent": result.get("order_sent", False),
        }, indent=2))
        return result
    finally:
        if historical_session and historical_config:
            _release_session(historical_config, historical_session)
        _release_session(config, client.session)


def signal_dry_run_order(env_file, strategy_path, epic, runtime_strategy_config, history_points,
                         cache_path="data/live_cache/ig", refresh_points=10):
    config, session, client = _connect(env_file)
    historical_config = historical_session = historical_client = None
    try:
        historical_config, historical_session, historical_client = _connect_historical_data_client(config)
        result = _evaluate_live_signal_with_cache(
            config=config,
            client=client,
            historical_client=historical_client,
            strategy_path=strategy_path,
            epic=epic,
            runtime_strategy_config=runtime_strategy_config,
            history_points=history_points,
            cache_path=cache_path,
            refresh_points=refresh_points,
        )
        report = write_signal_dry_run_report(config.audit_output_path, result)
        print(f"IG DEMO signal dry-run order report: {report}")
        print(json.dumps({
            "status": result["status"],
            "latest_closed_1h_candle": result.get("latest_closed_1h_candle"),
            "has_current_signal": result.get("current_signal") is not None,
            "dry_run_status": (
                result.get("dry_run_order", {}).get("validation_status")
                if result.get("dry_run_order") else None
            ),
            "order_sent": False,
        }, indent=2))
        return result
    finally:
        if historical_session and historical_config:
            _release_session(historical_config, historical_session)
        _release_session(config, client.session)


def run_bot(env_file, strategy_path, epic, runtime_strategy_config, history_points,
            duration_seconds, poll_seconds, cache_path, refresh_points=10, confirmation=None):
    config, session, client = _connect(env_file)
    historical_config = historical_session = historical_client = None
    try:
        historical_config, historical_session, historical_client = _connect_historical_data_client(config)
        if historical_client:
            logger.info(
                "Using IG historical-data override account for candle cache only | username=%s",
                historical_config.redacted()["historical_username"] or historical_config.redacted()["username"],
            )
        runner = IGDemoBotRunner(
            config=config,
            session=session,
            client=client,
            historical_client=historical_client,
            env_file=env_file,
            strategy_path=strategy_path,
            epic=epic,
            runtime_strategy_config=runtime_strategy_config,
            history_points=history_points,
            cache_path=cache_path,
            poll_seconds=poll_seconds,
            refresh_points=refresh_points,
        )
        result = runner.run(
            duration_seconds=duration_seconds,
            execute_confirmation=confirmation,
        )
        print(json.dumps({
            "status": result.status,
            "tick_count": result.tick_count,
            "last_evaluated_candle": result.last_evaluated_candle,
            "last_signal_status": (
                result.last_signal_result.get("status")
                if result.last_signal_result else None
            ),
            "order_sent": bool(result.order_execution),
            "accepted": (
                result.order_execution.get("accepted")
                if result.order_execution else False
            ),
            "reports": result.reports,
        }, indent=2, default=str))
        return result
    finally:
        if historical_session and historical_config:
            _release_session(historical_config, historical_session)
        _release_session(config, client.session)
