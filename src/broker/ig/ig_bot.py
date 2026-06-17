import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from .ig_candle_cache import CandleCachePaths, load_cached_candles, refresh_candle_cache
from .ig_demo_execution import place_demo_test_order, write_demo_execution_report
from .ig_live_signal import (
    evaluate_live_signal_from_candles,
    runtime_config_from_contract,
    write_signal_dry_run_report,
)
from .ig_market_rules import extract_market_rules
from .ig_streaming_client import IGStreamingClient
from .ig_subscriptions import PriceUpdateListener, TradeUpdateListener
from .ig_trade_lifecycle import (
    IGTradeLifecycleExecutor,
    IGTradeLifecycleManager,
    LifecycleJSONWriter,
    ManagedPosition,
)
from .models import DryRunOrder, InternalTick
from .telegram_notifier import TelegramNotifier, control_state

logger = logging.getLogger(__name__)


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


def _parse_hhmm(value: str) -> datetime_time:
    hour, minute = value.split(":", 1)
    return datetime_time(int(hour), int(minute))


def active_session_windows(windows: list[dict], now_utc: datetime) -> list[dict]:
    active = []
    for window in windows:
        tz_name = window.get("timezone", "UTC")
        local_now = now_utc.astimezone(ZoneInfo(tz_name))
        start = _parse_hhmm(window["start"])
        end = _parse_hhmm(window["end"])
        in_session = start <= local_now.time() < end
        if in_session:
            active.append({
                "name": window["name"],
                "timezone": tz_name,
                "start": window["start"],
                "end": window["end"],
                "local_now": local_now,
            })
    return active


def within_run_duration(started: datetime, duration_seconds: int, monotonic_deadline: float,
                        now: datetime | None = None, monotonic_now: float | None = None) -> bool:
    if duration_seconds <= 0:
        return True
    now = now or datetime.now(timezone.utc)
    monotonic_now = time.monotonic() if monotonic_now is None else monotonic_now
    wall_clock_deadline = started + timedelta(seconds=duration_seconds)
    return monotonic_now < monotonic_deadline and now < wall_clock_deadline


class SessionProgressTracker:
    def __init__(self, *, windows: list[dict], audit_output: str | Path, telegram: TelegramNotifier):
        self.windows = windows
        self.audit_output = audit_output
        self.telegram = telegram
        self.active_names: set[str] | None = None

    def check(self, now_utc: datetime | None = None) -> None:
        now_utc = now_utc or datetime.now(timezone.utc)
        active = active_session_windows(self.windows, now_utc)
        active_names = {item["name"] for item in active}
        active_by_name = {item["name"]: item for item in active}
        if self.active_names is None:
            self.active_names = active_names
            self._log_status(now_utc, active)
            return

        for name in sorted(active_names - self.active_names):
            self._log_transition("SESSION_STARTED", now_utc, active_by_name[name])
        for name in sorted(self.active_names - active_names):
            window = next(item for item in self.windows if item["name"] == name)
            local_now = now_utc.astimezone(ZoneInfo(window.get("timezone", "UTC")))
            self._log_transition("SESSION_ENDED", now_utc, {
                "name": window["name"],
                "timezone": window.get("timezone", "UTC"),
                "start": window["start"],
                "end": window["end"],
                "local_now": local_now,
            })
        self.active_names = active_names

    def _log_status(self, now_utc: datetime, active: list[dict]) -> None:
        names = ", ".join(item["name"] for item in active) if active else "none"
        logger.info(
            "IG bot session status | utc=%s | active_sessions=%s",
            now_utc.isoformat(),
            names,
        )
        write_bot_audit_event(self.audit_output, {
            "event": "SESSION_STATUS",
            "utc": now_utc.isoformat(),
            "active_sessions": [item["name"] for item in active],
        })

    def _log_transition(self, event: str, now_utc: datetime, window: dict) -> None:
        local_now = window["local_now"]
        logger.info(
            "IG bot %s | session=%s | utc=%s | local=%s | timezone=%s | window=%s-%s",
            event,
            window["name"],
            now_utc.isoformat(),
            local_now.isoformat(),
            window["timezone"],
            window["start"],
            window["end"],
        )
        write_bot_audit_event(self.audit_output, {
            "event": event,
            "session": window["name"],
            "utc": now_utc.isoformat(),
            "local": local_now.isoformat(),
            "timezone": window["timezone"],
            "window": f"{window['start']}-{window['end']}",
        })
        self.telegram.send(
            "\n".join([
                f"USDJPY {event.replace('_', ' ').lower()}",
                f"session: {window['name']}",
                f"utc: {now_utc.isoformat()}",
                f"local: {local_now.isoformat()}",
                f"window: {window['start']}-{window['end']} {window['timezone']}",
            ]),
            category="system",
        )


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
        self.lifecycle_manager: IGTradeLifecycleManager | None = None
        self.lifecycle_executor: IGTradeLifecycleExecutor | None = None
        self.lifecycle_writer = LifecycleJSONWriter(self.config.audit_output_path)
        self.telegram = TelegramNotifier(config)
        self._last_control_state = "ACTIVE"
        self._lock = Lock()

    def _on_tick(self, tick: InternalTick) -> None:
        with self._lock:
            self.price_state.latest_tick = tick
            self.price_state.tick_count += 1
            first_tick = not self.price_state.first_tick_seen
            if first_tick:
                self.price_state.first_tick_seen = True
            if self.lifecycle_manager:
                self.lifecycle_manager.on_tick(tick)
        if first_tick:
            write_bot_audit_event(self.config.audit_output_path, {
                "event": "FIRST_TICK",
                "epic": tick.epic,
                "bid": tick.bid,
                "ask": tick.ask,
                "spread_pips": tick.spread_pips,
                "delayed": tick.delayed,
            })

    def _on_trade_update(self, update_type: str, payload: dict) -> None:
        with self._lock:
            if self.lifecycle_manager:
                self.lifecycle_manager.on_trade_update(update_type, payload)
                self.lifecycle_writer.write(self.lifecycle_manager)
        write_bot_audit_event(self.config.audit_output_path, {
            "event": "TRADE_STREAM_UPDATE",
            "update_type": update_type,
            "payload": payload,
        })
        if self.lifecycle_manager and self.lifecycle_manager.position:
            if payload.get("dealId") == self.lifecycle_manager.position.deal_id:
                status = payload.get("status") or payload.get("dealStatus") or update_type
                self.telegram.send(
                    "\n".join([
                        "USDJPY trade update",
                        f"deal_id: {payload.get('dealId')}",
                        f"status: {status}",
                        f"direction: {payload.get('direction')}",
                        f"size: {payload.get('size')}",
                    ]),
                    category="trade",
                )

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

    def _scaled_confirmation_level(self, confirmation: dict | None, fallback: float) -> float:
        if not confirmation or confirmation.get("level") is None:
            return fallback
        level = float(confirmation["level"])
        return level / self.config.price_scale_divisor if self.config.price_scale_divisor else level

    def _attach_lifecycle_manager(self, result: dict, execution: dict, order: DryRunOrder) -> None:
        if not execution.get("accepted") or not execution.get("deal_id"):
            return
        signal = result.get("current_signal") or {}
        indicator = signal.get("indicator_snapshot") or {}
        entry = self._scaled_confirmation_level(execution.get("confirmation"), self.price_state.latest_tick.bid)
        initial_stop = float(signal["proposed_stop"])
        target = float(signal["proposed_target"])
        manager = IGTradeLifecycleManager(config=self.runtime_config.model_dump(), pip_size=self.market_rules.pip_size)
        manager.attach(ManagedPosition(
            deal_id=execution["deal_id"],
            deal_reference=execution["deal_reference"],
            epic=self.epic,
            direction=order.direction,
            size=float(order.size),
            remaining_size=float(order.size),
            entry_price=entry,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            target_price=target,
            initial_risk=abs(initial_stop - entry),
            atr=float(indicator.get("atr") or indicator.get("atr_14")),
            opened_at=datetime.now(timezone.utc),
            currency=order.currency,
            expiry=order.expiry,
        ))
        self.lifecycle_manager = manager
        self.lifecycle_executor = IGTradeLifecycleExecutor(
            client=self.client,
            config=self.config,
            price_scale_divisor=self.config.price_scale_divisor,
        )
        path = self.lifecycle_writer.write(manager)
        write_bot_audit_event(self.config.audit_output_path, {
            "event": "LIFECYCLE_MANAGER_ATTACHED",
            "deal_id": execution["deal_id"],
            "report": str(path),
        })

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
        self._attach_lifecycle_manager(result, execution, order)
        report = write_demo_execution_report(self.config.audit_output_path, execution)
        write_bot_audit_event(self.config.audit_output_path, {
            "event": "ORDER_SUBMITTED",
            "deal_reference": execution.get("deal_reference"),
            "deal_id": execution.get("deal_id"),
            "deal_status": execution.get("deal_status"),
            "report": str(report),
        })
        self.telegram.send(
            "\n".join([
                "USDJPY DEMO order submitted",
                f"status: {execution.get('deal_status')}",
                f"reason: {execution.get('reason')}",
                f"deal_id: {execution.get('deal_id')}",
                f"deal_reference: {execution.get('deal_reference')}",
                f"direction: {order.direction}",
                f"size: {order.size}",
            ]),
            category="trade",
        )
        return execution

    def _process_lifecycle_action(self) -> dict | None:
        with self._lock:
            if not self.lifecycle_manager or not self.lifecycle_executor:
                return None
            action = self.lifecycle_manager.pop_pending_action()
            position = self.lifecycle_manager.position
        if not action or not position:
            return None
        try:
            result = self.lifecycle_executor.execute(action, position)
            with self._lock:
                self.lifecycle_manager.mark_action_applied(action, result)
                report = self.lifecycle_writer.write(self.lifecycle_manager)
            write_bot_audit_event(self.config.audit_output_path, {
                "event": "LIFECYCLE_ACTION_SUBMITTED",
                "action": action.action_type,
                "reason": action.reason,
                "deal_id": action.deal_id,
                "report": str(report),
                "result": result,
            })
            self.telegram.send(
                "\n".join([
                    "USDJPY lifecycle action submitted",
                    f"action: {action.action_type}",
                    f"reason: {action.reason}",
                    f"deal_id: {action.deal_id}",
                    f"level: {action.level}",
                    f"size: {action.size}",
                ]),
                category="trade",
            )
            return result
        except Exception as exc:
            with self._lock:
                if self.lifecycle_manager:
                    self.lifecycle_manager.mark_action_rejected(action, {"error": str(exc)})
                    report = self.lifecycle_writer.write(self.lifecycle_manager)
                else:
                    report = None
            write_bot_audit_event(self.config.audit_output_path, {
                "event": "LIFECYCLE_ACTION_FAILED",
                "action": action.action_type,
                "reason": action.reason,
                "deal_id": action.deal_id,
                "error": str(exc),
                "report": str(report) if report else None,
            })
            self.telegram.send(
                "\n".join([
                    "USDJPY lifecycle action failed",
                    f"action: {action.action_type}",
                    f"reason: {action.reason}",
                    f"deal_id: {action.deal_id}",
                    f"error: {exc}",
                ]),
                category="trade",
            )
            return {"error": str(exc), "action": action.action_type}

    def _control_state(self) -> str:
        state = control_state(self.config.telegram_control_path)
        if state != self._last_control_state:
            self._last_control_state = state
            write_bot_audit_event(self.config.audit_output_path, {
                "event": "CONTROL_STATE_CHANGED",
                "state": state,
                "control_path": str(self.config.telegram_control_path),
            })
            self.telegram.send(f"USDJPY bot control state changed: {state}", category="system")
        return state

    def run(self, *, duration_seconds: int, execute_confirmation: str | None = None) -> BotRunResult:
        started = datetime.now(timezone.utc)
        result = BotRunResult(status="RUNNING", started_at=started.isoformat())
        self.telegram.send(
            "\n".join([
                "USDJPY bot started",
                f"epic: {self.epic}",
                f"duration_seconds: {duration_seconds}",
                f"orders_enabled: {bool(execute_confirmation)}",
            ]),
            category="system",
        )
        cache_summary = self._prepare()
        write_bot_audit_event(self.config.audit_output_path, {
            "event": "CANDLE_CACHE_READY",
            "cache": cache_summary,
        })
        streaming = IGStreamingClient(self.config, self.session)
        last_evaluated: datetime | None = None
        first_evaluation = True
        session_tracker = SessionProgressTracker(
            windows=self.contract["entry_rules"]["allowed_sessions"],
            audit_output=self.config.audit_output_path,
            telegram=self.telegram,
        )
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
            streaming.subscribe_trade_updates(TradeUpdateListener(self._on_trade_update))
            monotonic_deadline = (
                float("inf") if duration_seconds <= 0 else time.monotonic() + duration_seconds
            )
            while within_run_duration(started, duration_seconds, monotonic_deadline):
                self._process_lifecycle_action()
                session_tracker.check()
                state = self._control_state()
                if state == "STOP_REQUESTED":
                    result.status = "STOPPED_BY_CONTROL"
                    break
                candle = latest_closed_hour()
                if state == "PAUSED":
                    time.sleep(self.poll_seconds)
                    continue
                if self.price_state.latest_tick and candle != last_evaluated:
                    signal_result = self._evaluate(
                        candle,
                        refresh_cache=not first_evaluation,
                    )
                    if signal_result.get("status") == "SIGNAL_READY_FOR_DEMO_DRY_RUN":
                        self.telegram.send(
                            "\n".join([
                                "USDJPY signal ready",
                                f"candle: {candle.isoformat()}",
                                f"direction: {(signal_result.get('current_signal') or {}).get('direction')}",
                                f"session: {(signal_result.get('current_signal') or {}).get('session')}",
                                f"order_status: {(signal_result.get('dry_run_order') or {}).get('validation_status')}",
                            ]),
                            category="trade",
                        )
                    execution = self._maybe_execute(signal_result, execute_confirmation)
                    result.last_evaluated_candle = candle.isoformat()
                    result.last_signal_result = signal_result
                    result.order_execution = execution
                    last_evaluated = candle
                    first_evaluation = False
                time.sleep(self.poll_seconds)
            if result.status == "RUNNING":
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
            self.telegram.send(
                "\n".join([
                    "USDJPY bot stopped",
                    f"status: {result.status}",
                    f"tick_count: {result.tick_count}",
                    f"last_evaluated_candle: {result.last_evaluated_candle}",
                    f"last_signal_status: {(result.last_signal_result or {}).get('status')}",
                    f"order_sent: {bool(result.order_execution)}",
                ]),
                category="system",
            )
            self.telegram.close()
