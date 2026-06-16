import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ig_candle_cache import CandleCachePaths, load_cached_candles, refresh_candle_cache
from .ig_demo_execution import place_demo_test_order, write_demo_execution_report
from .ig_live_signal import (
    evaluate_live_signal_from_candles,
    runtime_config_from_contract,
    write_signal_dry_run_report,
)
from .ig_market_rules import extract_market_rules
from .ig_streaming_client import IGStreamingClient
from .ig_subscriptions import PriceUpdateListener
from .models import DryRunOrder, InternalTick


@dataclass
class BotPriceState:
    latest_tick: InternalTick | None = None
    tick_count: int = 0
    first_tick_seen: bool = False


@dataclass
class BotRunResult:
    status: str
    started_at: str
    completed_at: str | None = None
    tick_count: int = 0
    last_evaluated_candle: str | None = None
    last_signal_result: dict | None = None
    order_execution: dict | None = None
    reports: dict = field(default_factory=dict)


def latest_closed_hour(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)


def write_bot_audit_event(output: str | Path, event: dict) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "bot_audit_events_usdjpy.jsonl"
    with path.open("a") as handle:
        handle.write(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }, default=str) + "\n")
    return path


def _order_from_result(result: dict) -> DryRunOrder:
    order = result["dry_run_order"]
    payload = dict(order["payload"])
    return DryRunOrder(
        **payload,
        validation_status=order["validation_status"],
        validation_errors=order["validation_errors"],
        validation_warnings=order["validation_warnings"],
    )


class IGDemoBotRunner:
    def __init__(self, *, config, session, client, env_file: str, strategy_path: str,
                 epic: str, runtime_strategy_config: str, history_points: int = 1000,
                 cache_path: str | Path = "data/live_cache/ig",
                 poll_seconds: float = 5,
                 refresh_points: int = 10,
                 historical_client=None):
        self.config = config
        self.session = session
        self.client = client
        self.historical_client = historical_client or client
        self.env_file = env_file
        self.strategy_path = strategy_path
        self.epic = epic
        self.runtime_strategy_config = runtime_strategy_config
        self.history_points = history_points
        self.cache = CandleCachePaths(Path(cache_path))
        self.poll_seconds = poll_seconds
        self.refresh_points = refresh_points
        self.price_state = BotPriceState()
        self.runtime_config = None
        self.contract = None
        self.market_rules = None

    def _on_tick(self, tick: InternalTick) -> None:
        self.price_state.latest_tick = tick
        self.price_state.tick_count += 1
        if not self.price_state.first_tick_seen:
            self.price_state.first_tick_seen = True
            write_bot_audit_event(self.config.audit_output_path, {
                "event": "FIRST_TICK",
                "epic": tick.epic,
                "bid": tick.bid,
                "ask": tick.ask,
                "spread_pips": tick.spread_pips,
                "delayed": tick.delayed,
            })

    def _prepare(self) -> dict:
        self.runtime_config, self.contract = runtime_config_from_contract(
            self.strategy_path,
            self.runtime_strategy_config,
        )
        self.market_rules = extract_market_rules(self.client.get_market(self.epic))
        points = self.history_points if not self.cache.exists() else self.refresh_points
        return refresh_candle_cache(
            client=self.historical_client,
            epic=self.epic,
            paths=self.cache,
            scale_divisor=self.config.price_scale_divisor,
            history_points=points,
            keep_last=self.history_points,
        )

    def _evaluate(self, candle: datetime, *, refresh_cache: bool = True) -> dict:
        refresh = None
        if refresh_cache:
            refresh = refresh_candle_cache(
                client=self.historical_client,
                epic=self.epic,
                paths=self.cache,
                scale_divisor=self.config.price_scale_divisor,
                history_points=self.refresh_points,
                keep_last=self.history_points,
            )
        hour, four_hour = load_cached_candles(self.cache)
        latest_cached_hour = hour["timestamp"].max() if hour.height else None
        if latest_cached_hour is None or latest_cached_hour < candle:
            result = {
                "status": "BLOCKED_STALE_CANDLE_CACHE",
                "epic": self.epic,
                "target_closed_1h_candle": candle.isoformat(),
                "latest_closed_1h_candle": latest_cached_hour.isoformat() if latest_cached_hour else None,
                "current_signal": None,
                "dry_run_order": None,
                "order_sent": False,
            }
        else:
            result = evaluate_live_signal_from_candles(
                client=self.client,
                config=self.runtime_config,
                contract=self.contract,
                epic=self.epic,
                market_rules=self.market_rules,
                hour=hour,
                four_hour=four_hour,
                execution_tick=self.price_state.latest_tick,
            )
        report = write_signal_dry_run_report(self.config.audit_output_path, result)
        write_bot_audit_event(self.config.audit_output_path, {
            "event": "SIGNAL_EVALUATED",
            "candle": candle.isoformat(),
            "status": result["status"],
            "report": str(report),
            "cache": refresh,
            "used_cached_candles_without_refresh": refresh is None,
        })
        return result

    def _maybe_execute(self, result: dict, confirmation: str | None) -> dict | None:
        if result.get("status") != "SIGNAL_READY_FOR_DEMO_DRY_RUN":
            return None
        if not confirmation:
            return None
        order = _order_from_result(result)
        execution = place_demo_test_order(
            self.client,
            order,
            currency_code=order.currency,
            confirmation=confirmation,
        )
        execution["execution_type"] = "STRATEGY_SIGNAL_DEMO_ORDER"
        execution["strategy_signal_used"] = True
        execution["signal"] = result.get("current_signal")
        report = write_demo_execution_report(self.config.audit_output_path, execution)
        write_bot_audit_event(self.config.audit_output_path, {
            "event": "ORDER_SUBMITTED",
            "deal_reference": execution.get("deal_reference"),
            "deal_id": execution.get("deal_id"),
            "deal_status": execution.get("deal_status"),
            "report": str(report),
        })
        return execution

    def run(self, *, duration_seconds: int, execute_confirmation: str | None = None) -> BotRunResult:
        started = datetime.now(timezone.utc)
        result = BotRunResult(status="RUNNING", started_at=started.isoformat())
        cache_summary = self._prepare()
        write_bot_audit_event(self.config.audit_output_path, {
            "event": "CANDLE_CACHE_READY",
            "cache": cache_summary,
        })
        streaming = IGStreamingClient(self.config, self.session)
        last_evaluated: datetime | None = None
        first_evaluation = True
        try:
            streaming.connect()
            streaming.subscribe_price(
                self.epic,
                PriceUpdateListener(
                    self.epic,
                    self._on_tick,
                    self.market_rules.pip_size,
                    self.config.price_scale_divisor,
                ),
            )
            deadline = time.monotonic() + duration_seconds
            while time.monotonic() < deadline:
                candle = latest_closed_hour()
                if self.price_state.latest_tick and candle != last_evaluated:
                    signal_result = self._evaluate(
                        candle,
                        refresh_cache=not first_evaluation,
                    )
                    execution = self._maybe_execute(signal_result, execute_confirmation)
                    result.last_evaluated_candle = candle.isoformat()
                    result.last_signal_result = signal_result
                    result.order_execution = execution
                    last_evaluated = candle
                    first_evaluation = False
                    if execution and execution.get("accepted"):
                        break
                time.sleep(self.poll_seconds)
            result.status = "COMPLETED"
            return result
        finally:
            streaming.disconnect()
            result.completed_at = datetime.now(timezone.utc).isoformat()
            result.tick_count = self.price_state.tick_count
            report = Path(self.config.audit_output_path) / "bot_run_usdjpy.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            result.reports["bot_run"] = str(report)
            report.write_text(json.dumps(result.__dict__, indent=2, default=str))
