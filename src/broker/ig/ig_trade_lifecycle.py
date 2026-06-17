import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .models import InternalTick


@dataclass
class ManagedPosition:
    deal_id: str
    deal_reference: str
    epic: str
    direction: str
    size: float
    remaining_size: float
    entry_price: float
    initial_stop: float
    current_stop: float
    target_price: float
    initial_risk: float
    atr: float
    opened_at: datetime
    currency: str
    expiry: str
    breakeven_applied: bool = False
    partial_close_applied: bool = False
    trailing_active: bool = False
    highest_price: float | None = None
    lowest_price: float | None = None
    stop_amend_count: int = 0
    stop_amend_skipped_count: int = 0
    stop_amend_skip_reasons: list[str] = field(default_factory=list)
    partial_close_request_count: int = 0
    last_stop_amend_at_monotonic: float = 0
    stop_amend_monotonic_times: list[float] = field(default_factory=list)
    lifecycle_events: list[dict] = field(default_factory=list)


@dataclass
class LifecycleAction:
    action_type: str
    reason: str
    deal_id: str
    deal_reference: str
    level: float | None = None
    size: float | None = None


def _opposite(direction: str) -> str:
    return "BUY" if direction.upper() == "SELL" else "SELL"


def _broker_level(level: float, price_scale_divisor: float | None) -> float:
    return round(level * price_scale_divisor, 8) if price_scale_divisor else round(level, 8)


class IGTradeLifecycleManager:
    def __init__(self, *, config: dict, pip_size: float = 0.01):
        self.config = config
        self.pip_size = pip_size
        lifecycle = config.get("broker_execution_guardrails", {}).get("trade_lifecycle", {})
        self.enabled = bool(lifecycle.get("enabled", True))
        self.min_amend_interval = float(lifecycle.get("stop_amend_min_interval_seconds", 10))
        self.min_amend_move = float(lifecycle.get("stop_amend_min_move_pips", 1.0)) * pip_size
        self.max_amends_per_minute = int(lifecycle.get("max_stop_amends_per_minute", 4))
        self.max_amends_per_trade = int(lifecycle.get("max_stop_amends_per_trade", 50))
        self.position: ManagedPosition | None = None
        self.pending_action: LifecycleAction | None = None

    def attach(self, position: ManagedPosition) -> None:
        if position.direction.upper() == "BUY":
            position.highest_price = position.entry_price
        else:
            position.lowest_price = position.entry_price
        position.lifecycle_events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "POSITION_ATTACHED",
            "deal_id": position.deal_id,
            "direction": position.direction,
            "entry_price": position.entry_price,
            "initial_stop": position.initial_stop,
            "target_price": position.target_price,
        })
        self.position = position

    def has_position(self) -> bool:
        return self.position is not None

    def on_tick(self, tick: InternalTick) -> LifecycleAction | None:
        if not self.enabled or not self.position or tick.epic != self.position.epic:
            return None
        position = self.position
        if position.remaining_size <= 0:
            return None
        action = self._maybe_full_close(position, tick)
        if action:
            return self._queue(action)
        is_short = position.direction.upper() == "SELL"
        close_side = tick.ask if is_short else tick.bid
        favourable_move = (
            position.entry_price - close_side if is_short else close_side - position.entry_price
        )
        if is_short:
            position.lowest_price = min(position.lowest_price or close_side, close_side)
        else:
            position.highest_price = max(position.highest_price or close_side, close_side)

        action = self._maybe_breakeven(position, favourable_move)
        if action:
            return self._queue(action)
        action = self._maybe_partial_close(position, favourable_move)
        if action:
            return self._queue(action)
        action = self._maybe_trailing_stop(position, close_side)
        if action:
            return self._queue(action)
        return None

    def _maybe_full_close(self, position: ManagedPosition, tick: InternalTick) -> LifecycleAction | None:
        max_days = self.config.get("max_trade_duration_days")
        if max_days is not None and tick.timestamp_utc >= position.opened_at + timedelta(days=int(max_days)):
            return LifecycleAction(
                "FULL_CLOSE", "max_duration", position.deal_id, position.deal_reference,
                size=position.remaining_size,
            )
        weekend = self.config.get("weekend_policy", {})
        force = weekend.get("force_close_on_friday", {})
        if weekend.get("enabled") and force.get("enabled") and tick.timestamp_utc.weekday() == 4:
            close_time = datetime.strptime(force["close_time_utc"], "%H:%M").time()
            if tick.timestamp_utc.time() >= close_time:
                return LifecycleAction(
                    "FULL_CLOSE",
                    force.get("close_reason", "weekend_force_close"),
                    position.deal_id,
                    position.deal_reference,
                    size=position.remaining_size,
                )
        return None

    def pop_pending_action(self) -> LifecycleAction | None:
        action, self.pending_action = self.pending_action, None
        return action

    def mark_action_applied(self, action: LifecycleAction, result: dict | None = None) -> None:
        if not self.position:
            return
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "ACTION_APPLIED",
            "action": asdict(action),
            "result": result or {},
        }
        self.position.lifecycle_events.append(event)
        if action.action_type == "AMEND_STOP" and action.level is not None:
            self.position.current_stop = action.level
            self.position.stop_amend_count += 1
            now = time.monotonic()
            self.position.last_stop_amend_at_monotonic = now
            self.position.stop_amend_monotonic_times.append(now)
        elif action.action_type == "PARTIAL_CLOSE" and action.size is not None:
            self.position.partial_close_applied = True
            self.position.partial_close_request_count += 1
            self.position.remaining_size = max(0, self.position.remaining_size - action.size)
        elif action.action_type == "FULL_CLOSE":
            self.position.remaining_size = 0

    def mark_action_rejected(self, action: LifecycleAction, result: dict | None = None) -> None:
        if not self.position:
            return
        self.position.lifecycle_events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "ACTION_REJECTED",
            "action": asdict(action),
            "result": result or {},
        })

    def on_trade_update(self, update_type: str, payload: dict) -> None:
        if not self.position:
            return
        self.position.lifecycle_events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "TRADE_STREAM_UPDATE",
            "update_type": update_type,
            "payload": payload,
        })
        if update_type == "OPU" and payload.get("dealId") == self.position.deal_id:
            status = str(payload.get("status", "")).upper()
            if status in {"DELETED", "CLOSED", "FULLY_CLOSED"}:
                self.position.remaining_size = 0

    def snapshot(self) -> dict:
        return asdict(self.position) if self.position else {"position": None}

    def _maybe_breakeven(self, position: ManagedPosition, favourable_move: float) -> LifecycleAction | None:
        if position.breakeven_applied:
            return None
        cfg = self.config["exit"]["move_stop_to_breakeven"]
        if not cfg.get("enabled") or favourable_move < position.initial_risk * float(cfg["after_r"]):
            return None
        candidate = position.entry_price
        if position.direction.upper() == "SELL" and candidate >= position.current_stop:
            return None
        if position.direction.upper() == "BUY" and candidate <= position.current_stop:
            return None
        if not self._can_amend_stop(position, candidate):
            return None
        position.breakeven_applied = True
        return LifecycleAction("AMEND_STOP", "breakeven", position.deal_id, position.deal_reference, level=candidate)

    def _maybe_partial_close(self, position: ManagedPosition, favourable_move: float) -> LifecycleAction | None:
        if position.partial_close_applied:
            return None
        cfg = self.config["exit"]["partial_take_profit"]
        if not cfg.get("enabled") or favourable_move < position.initial_risk * float(cfg["at_r"]):
            return None
        close_size = round(position.size * float(cfg["close_percent"]) / 100, 2)
        if close_size <= 0 or close_size >= position.remaining_size:
            return None
        return LifecycleAction(
            "PARTIAL_CLOSE", "partial_take_profit", position.deal_id,
            position.deal_reference, size=close_size,
        )

    def _maybe_trailing_stop(self, position: ManagedPosition, close_side: float) -> LifecycleAction | None:
        if not position.partial_close_applied or not self.config["exit"]["runner"].get("enabled"):
            return None
        trail_distance = position.atr * float(
            self.config["exit"]["runner"]["trailing_stop"]["atr_multiplier"]
        )
        is_short = position.direction.upper() == "SELL"
        if is_short:
            candidate = (position.lowest_price or close_side) + trail_distance
            if candidate >= position.current_stop:
                return None
        else:
            candidate = (position.highest_price or close_side) - trail_distance
            if candidate <= position.current_stop:
                return None
        if not self._can_amend_stop(position, candidate):
            return None
        position.trailing_active = True
        return LifecycleAction("AMEND_STOP", "trailing", position.deal_id, position.deal_reference, level=candidate)

    def _can_amend_stop(self, position: ManagedPosition, candidate: float) -> bool:
        reason = None
        now = time.monotonic()
        recent = [item for item in position.stop_amend_monotonic_times if now - item < 60]
        if position.stop_amend_count >= self.max_amends_per_trade:
            reason = "MAX_STOP_AMENDS_PER_TRADE"
        elif position.last_stop_amend_at_monotonic and now - position.last_stop_amend_at_monotonic < self.min_amend_interval:
            reason = "STOP_AMEND_INTERVAL_THROTTLED"
        elif abs(candidate - position.current_stop) < self.min_amend_move:
            reason = "STOP_AMEND_MOVE_BELOW_MINIMUM"
        elif len(recent) >= self.max_amends_per_minute:
            reason = "STOP_AMEND_PER_MINUTE_THROTTLED"
        if reason:
            position.stop_amend_skipped_count += 1
            position.stop_amend_skip_reasons.append(reason)
            position.lifecycle_events.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "STOP_AMEND_SKIPPED",
                "reason": reason,
                "candidate": candidate,
                "current_stop": position.current_stop,
            })
            return False
        return True

    def _queue(self, action: LifecycleAction) -> LifecycleAction:
        self.pending_action = action
        return action


class IGTradeLifecycleExecutor:
    def __init__(self, *, client, config, price_scale_divisor: float | None):
        self.client = client
        self.config = config
        self.price_scale_divisor = price_scale_divisor

    def execute(self, action: LifecycleAction, position: ManagedPosition) -> dict:
        if action.action_type == "AMEND_STOP":
            payload = {"stopLevel": _broker_level(action.level, self.price_scale_divisor)}
            response = self.client.amend_position(action.deal_id, payload)
        elif action.action_type in {"PARTIAL_CLOSE", "FULL_CLOSE"}:
            size = action.size if action.action_type == "PARTIAL_CLOSE" else position.remaining_size
            payload = {
                "dealId": action.deal_id,
                "direction": _opposite(position.direction),
                "epic": position.epic,
                "expiry": position.expiry,
                "size": size,
                "orderType": "MARKET",
                "timeInForce": "FILL_OR_KILL",
            }
            response = self.client.close_position(payload)
        else:
            raise ValueError(f"Unsupported lifecycle action: {action.action_type}")
        return {
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "deal_reference": response.get("dealReference") or f"lifecycle-{uuid4().hex[:20]}",
            "action": asdict(action),
            "response": response,
        }


class LifecycleJSONWriter:
    def __init__(self, output: str | Path):
        self.output = Path(output)

    def write(self, manager: IGTradeLifecycleManager) -> Path:
        self.output.mkdir(parents=True, exist_ok=True)
        path = self.output / "trade_lifecycle_usdjpy.json"
        path.write_text(json.dumps(manager.snapshot(), indent=2, default=str))
        return path
