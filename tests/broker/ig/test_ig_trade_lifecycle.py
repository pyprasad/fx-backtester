from datetime import datetime, timezone
from types import SimpleNamespace

from src.broker.ig.ig_trade_lifecycle import (
    IGTradeLifecycleExecutor,
    IGTradeLifecycleManager,
    LifecycleAction,
    ManagedPosition,
)
from src.broker.ig.models import InternalTick


def _config():
    return {
        "max_trade_duration_days": 7,
        "weekend_policy": {
            "enabled": True,
            "force_close_on_friday": {
                "enabled": True,
                "close_time_utc": "20:30",
                "close_reason": "weekend_force_close",
            },
        },
        "exit": {
            "move_stop_to_breakeven": {"enabled": True, "after_r": 1.2},
            "partial_take_profit": {"enabled": True, "at_r": 2.0, "close_percent": 50},
            "runner": {
                "enabled": True,
                "final_target_r": 4.0,
                "trailing_stop": {"atr_multiplier": 1.5},
            },
        },
        "broker_execution_guardrails": {
            "trade_lifecycle": {
                "enabled": True,
                "stop_amend_min_interval_seconds": 10,
                "stop_amend_min_move_pips": 1.0,
                "max_stop_amends_per_minute": 4,
                "max_stop_amends_per_trade": 50,
            }
        },
    }


def _position():
    return ManagedPosition(
        deal_id="DEAL1",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="SELL",
        size=12.0,
        remaining_size=12.0,
        entry_price=160.0,
        initial_stop=160.06,
        current_stop=160.06,
        target_price=159.76,
        initial_risk=0.06,
        atr=0.04,
        opened_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    )


def _tick(bid, ask):
    return _tick_at(datetime(2026, 6, 18, 12, tzinfo=timezone.utc), bid, ask)


def _tick_at(timestamp, bid, ask):
    return InternalTick(
        timestamp,
        bid,
        ask,
        (bid + ask) / 2,
        1.0,
        "IG_DEMO_PRICE",
        "CS.D.USDJPY.TODAY.IP",
        False,
        raw={"normalization_price_scale_divisor": 100},
    )


def test_lifecycle_emits_breakeven_and_partial_close_actions():
    manager = IGTradeLifecycleManager(config=_config())
    position = _position()
    manager.attach(position)

    action = manager.on_tick(_tick(159.91, 159.92))
    assert action.action_type == "AMEND_STOP"
    assert action.reason == "breakeven"
    manager.mark_action_applied(action)

    action = manager.on_tick(_tick(159.86, 159.87))
    assert action.action_type == "PARTIAL_CLOSE"
    assert action.size == 6.0
    manager.mark_action_applied(action)

    assert manager.position.current_stop == 160.0
    assert manager.position.remaining_size == 6.0
    assert manager.position.partial_close_request_count == 1


def test_lifecycle_throttles_rapid_trailing_stop_updates():
    manager = IGTradeLifecycleManager(config=_config())
    position = _position()
    position.partial_close_applied = True
    position.remaining_size = 6.0
    manager.attach(position)

    action = manager.on_tick(_tick(159.80, 159.81))
    assert action.action_type == "AMEND_STOP"
    manager.mark_action_applied(action)

    assert manager.on_tick(_tick(159.78, 159.79)) is None
    assert manager.position.stop_amend_skipped_count == 1
    assert "STOP_AMEND_INTERVAL_THROTTLED" in manager.position.stop_amend_skip_reasons


def test_lifecycle_executor_scales_stop_level_and_closes_opposite_direction():
    calls = []
    client = SimpleNamespace()
    client.amend_position = lambda deal_id, payload: calls.append(("amend", deal_id, payload)) or {"dealReference": "A"}
    client.close_position = lambda payload: calls.append(("close", payload)) or {"dealReference": "C"}
    executor = IGTradeLifecycleExecutor(client=client, config=SimpleNamespace(), price_scale_divisor=100)
    manager = IGTradeLifecycleManager(config=_config())
    position = _position()
    manager.attach(position)

    amend = LifecycleAction("AMEND_STOP", "trailing", "DEAL1", "REF1", level=159.87)
    executor.execute(amend, position)
    close = LifecycleAction("PARTIAL_CLOSE", "partial_take_profit", "DEAL1", "REF1", size=6.0)
    executor.execute(close, position)

    assert calls[0] == ("amend", "DEAL1", {"stopLevel": 15987.0})
    assert calls[1][0] == "close"
    assert calls[1][1]["direction"] == "BUY"
    assert calls[1][1]["size"] == 6.0


def test_lifecycle_emits_full_close_for_max_duration():
    manager = IGTradeLifecycleManager(config=_config())
    position = _position()
    manager.attach(position)

    action = manager.on_tick(_tick_at(datetime(2026, 6, 24, 0, 1, tzinfo=timezone.utc), 159.9, 159.91))

    assert action.action_type == "FULL_CLOSE"
    assert action.reason == "max_duration"
    assert action.size == 12.0


def test_lifecycle_emits_full_close_for_friday_weekend_cutoff():
    manager = IGTradeLifecycleManager(config=_config())
    position = _position()
    manager.attach(position)

    action = manager.on_tick(_tick_at(datetime(2026, 6, 19, 20, 31, tzinfo=timezone.utc), 159.9, 159.91))

    assert action.action_type == "FULL_CLOSE"
    assert action.reason == "weekend_force_close"
    assert action.size == 12.0
