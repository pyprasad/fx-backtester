import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from src.broker.ig.ig_bot import (
    BotRunResult,
    IGDemoBotRunner,
    NewsCalendarRefreshGuard,
    SessionProgressTracker,
    _bot_label,
    active_session_windows,
    latest_closed_hour,
    within_run_duration,
    write_bot_audit_event,
)
from src.broker.ig.ig_candle_cache import CandleCachePaths
from src.broker.ig.models import DryRunOrder
from src.broker.ig.ig_trade_lifecycle import IGTradeLifecycleManager, LifecycleAction, ManagedPosition
from src.broker_guardrails.time_guard import weekend_market_hibernate_window


def test_latest_closed_hour_returns_previous_complete_hour():
    assert latest_closed_hour(datetime(2026, 6, 16, 10, 4, 30, tzinfo=timezone.utc)) == (
        datetime(2026, 6, 16, 9, tzinfo=timezone.utc)
    )


def test_active_session_windows_respects_per_session_timezones():
    windows = [
        {"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
        {
            "name": "London New York overlap",
            "start": "13:00",
            "end": "16:30",
            "timezone": "Europe/London",
        },
    ]

    tokyo = active_session_windows(
        windows,
        datetime(2026, 6, 17, 0, 30, tzinfo=timezone.utc),
    )
    london_overlap = active_session_windows(
        windows,
        datetime(2026, 6, 17, 12, 30, tzinfo=timezone.utc),
    )

    assert [item["name"] for item in tokyo] == ["Tokyo"]
    assert [item["name"] for item in london_overlap] == ["London New York overlap"]


def test_session_tracker_suppresses_weekend_session_notifications(tmp_path):
    sends = []
    tracker = SessionProgressTracker(
        windows=[{"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"}],
        audit_output=tmp_path,
        telegram=SimpleNamespace(send=lambda text, *, category="system": sends.append(text)),
    )
    now_utc = datetime(2026, 7, 25, 0, 0, 1, tzinfo=timezone.utc)

    tracker.check(now_utc, weekend_market_hibernate_window(now_utc))

    assert len(sends) == 1
    assert "market hibernating" in sends[0]
    assert "session started" not in sends[0]
    rows = (tmp_path / "bot_audit_events_usdjpy.jsonl").read_text()
    assert "MARKET_HIBERNATE_STARTED" in rows
    assert "SESSION_STARTED" not in rows


def test_write_bot_audit_event_appends_jsonl(tmp_path):
    path = write_bot_audit_event(tmp_path, {"event": "SIGNAL_EVALUATED", "status": "NO_SIGNAL"})
    write_bot_audit_event(tmp_path, {"event": "FIRST_TICK"})

    rows = path.read_text().splitlines()
    assert len(rows) == 2
    assert "SIGNAL_EVALUATED" in rows[0]
    assert "FIRST_TICK" in rows[1]


def test_write_bot_audit_event_can_include_run_context(tmp_path):
    path = write_bot_audit_event(
        tmp_path,
        {"event": "SIGNAL_EVALUATED", "status": "NO_SIGNAL"},
        run_id="run-123",
        run_started_at="2026-07-15T23:31:42+00:00",
    )

    row = json.loads(path.read_text())
    assert row["run_id"] == "run-123"
    assert row["run_started_at"] == "2026-07-15T23:31:42+00:00"
    assert row["event"] == "SIGNAL_EVALUATED"


def test_within_run_duration_respects_wall_clock_and_monotonic_deadlines():
    started = datetime(2026, 6, 17, 0, tzinfo=timezone.utc)

    assert within_run_duration(
        started,
        duration_seconds=60,
        monotonic_deadline=100,
        now=datetime(2026, 6, 17, 0, 0, 59, tzinfo=timezone.utc),
        monotonic_now=99,
    )
    assert not within_run_duration(
        started,
        duration_seconds=60,
        monotonic_deadline=100,
        now=datetime(2026, 6, 17, 0, 1, 1, tzinfo=timezone.utc),
        monotonic_now=50,
    )
    assert not within_run_duration(
        started,
        duration_seconds=60,
        monotonic_deadline=100,
        now=datetime(2026, 6, 17, 0, 0, 30, tzinfo=timezone.utc),
        monotonic_now=101,
    )


def test_within_run_duration_zero_means_indefinite():
    started = datetime(2026, 6, 17, 0, tzinfo=timezone.utc)

    assert within_run_duration(
        started,
        duration_seconds=0,
        monotonic_deadline=0,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
        monotonic_now=999999,
    )


def test_news_calendar_refresh_guard_waits_until_before_first_session(tmp_path):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "future,2026-07-31T10:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
    )
    events = []
    guard = NewsCalendarRefreshGuard(
        config=SimpleNamespace(
            news_guard_calendar_refresh_enabled=True,
            news_guard_calendar_min_forward_days=7,
            news_guard_calendar_refresh_minutes_before_session=30,
        ),
        contract={"news_guard": {"enabled": True, "calendar_file": str(calendar)}},
        audit_callback=events.append,
        first_session={"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
    )

    assert guard.check(datetime(2026, 7, 22, 23, 29, tzinfo=timezone.utc))
    assert events == []
    assert guard.check(datetime(2026, 7, 22, 23, 30, tzinfo=timezone.utc))
    assert events[0]["event"] == "NEWS_CALENDAR_REFRESH_CHECK"
    assert events[0]["status"] == "CURRENT"
    assert events[0]["session"] == "Tokyo"
    assert events[0]["scheduled_refresh_at_utc"] == "2026-07-22T23:30:00+00:00"
    assert events[0]["session_start_utc"] == "2026-07-23T00:00:00+00:00"


def test_news_calendar_refresh_guard_refreshes_stale_calendar(tmp_path, monkeypatch):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "old,2026-07-23T10:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
    )
    events = []

    def refresh(**kwargs):
        calendar.write_text(
            "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
            "future,2026-08-10T10:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
        )
        return {"status": "REFRESHED", "output": str(kwargs["output"])}

    monkeypatch.setattr("src.broker.ig.ig_bot.refresh_calendar", refresh)
    guard = NewsCalendarRefreshGuard(
        config=SimpleNamespace(
            news_guard_calendar_refresh_enabled=True,
            news_guard_calendar_forward_days=21,
            news_guard_calendar_min_forward_days=7,
            news_guard_calendar_refresh_minutes_before_session=30,
            news_guard_calendar_cache_dir=tmp_path / "cache",
        ),
        contract={"news_guard": {"enabled": True, "calendar_file": str(calendar)}},
        audit_callback=events.append,
        first_session={"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
    )

    assert guard.check(datetime(2026, 7, 22, 23, 30, tzinfo=timezone.utc))
    assert [event["event"] for event in events] == [
        "NEWS_CALENDAR_REFRESH_CHECK",
        "NEWS_CALENDAR_REFRESHED",
    ]
    assert events[0]["status"] == "STALE"
    assert events[1]["status"] == "CURRENT"


def test_news_calendar_refresh_guard_uses_gbpusd_refresher_for_gbp_usd(tmp_path, monkeypatch):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "old,2026-07-23T10:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
    )
    calls = []

    def refresh(**kwargs):
        calls.append(kwargs)
        calendar.write_text(
            "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
            "future,2026-08-10T10:00:00Z,United Kingdom,GBP,CPI,HIGH,,,,test\n"
        )
        return {"status": "REFRESHED", "output": str(kwargs["output"])}

    monkeypatch.setattr("src.broker.ig.ig_bot.refresh_gbpusd_calendar", refresh)
    guard = NewsCalendarRefreshGuard(
        config=SimpleNamespace(
            news_guard_calendar_refresh_enabled=True,
            news_guard_calendar_forward_days=21,
            news_guard_calendar_min_forward_days=7,
            news_guard_calendar_refresh_minutes_before_session=30,
            news_guard_calendar_cache_dir=tmp_path / "cache",
        ),
        contract={
            "news_guard": {
                "enabled": True,
                "calendar_file": str(calendar),
                "affected_currencies": ["GBP", "USD"],
            }
        },
        audit_callback=lambda _event: None,
        first_session={"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
    )

    assert guard.check(datetime(2026, 7, 22, 23, 30, tzinfo=timezone.utc))
    assert calls


def test_news_calendar_refresh_guard_fails_closed_and_does_not_retry_same_day(tmp_path, monkeypatch):
    calendar = tmp_path / "events.csv"
    calendar.write_text(
        "event_id,event_time_utc,country,currency,event_name,impact,actual,forecast,previous,source\n"
        "old,2026-07-23T10:00:00Z,United States,USD,CPI,HIGH,,,,test\n"
    )
    events = []

    def refresh(**_kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("src.broker.ig.ig_bot.refresh_calendar", refresh)
    guard = NewsCalendarRefreshGuard(
        config=SimpleNamespace(
            news_guard_calendar_refresh_enabled=True,
            news_guard_calendar_forward_days=21,
            news_guard_calendar_min_forward_days=7,
            news_guard_calendar_refresh_minutes_before_session=30,
            news_guard_calendar_cache_dir=tmp_path / "cache",
        ),
        contract={"news_guard": {"enabled": True, "calendar_file": str(calendar)}},
        audit_callback=events.append,
        first_session={"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
    )

    assert not guard.check(datetime(2026, 7, 22, 23, 30, tzinfo=timezone.utc))
    assert not guard.check(datetime(2026, 7, 22, 23, 35, tzinfo=timezone.utc))
    assert [event["event"] for event in events] == [
        "NEWS_CALENDAR_REFRESH_CHECK",
        "NEWS_CALENDAR_REFRESH_FAILED",
    ]
    assert events[-1]["status"] == "BLOCK_NEW_ENTRIES"


def test_evaluate_blocks_when_target_candle_is_newer_than_cache(tmp_path, monkeypatch):
    cache = CandleCachePaths(tmp_path / "cache")
    cache.root.mkdir(parents=True)
    frame = pl.DataFrame({
        "timestamp": [datetime(2026, 6, 16, 10, tzinfo=timezone.utc)],
        "timestamp_london": [datetime(2026, 6, 16, 11, tzinfo=timezone.utc)],
        "symbol": ["USDJPY"],
        "bid_close": [160.0],
    })
    frame.write_parquet(cache.path("HOUR"))
    frame.write_parquet(cache.path("HOUR_4"))
    config = SimpleNamespace(audit_output_path=tmp_path / "audit", price_scale_divisor=100)
    runner = IGDemoBotRunner(
        config=config,
        session=SimpleNamespace(),
        client=SimpleNamespace(),
        env_file=".env.demo",
        strategy_path="contract.yaml",
        epic="CS.D.USDJPY.TODAY.IP",
        runtime_strategy_config="runtime.yaml",
        cache_path=cache.root,
    )
    runner.runtime_config = SimpleNamespace()
    runner.contract = {}
    runner.market_rules = SimpleNamespace()
    monkeypatch.setattr("src.broker.ig.ig_bot.refresh_candle_cache", lambda **_: {"fallback": True})

    result = runner._evaluate(datetime(2026, 6, 16, 11, tzinfo=timezone.utc))

    assert result["status"] == "BLOCKED_STALE_CANDLE_CACHE"
    assert result["target_closed_1h_candle"] == "2026-06-16T11:00:00+00:00"
    assert result["latest_closed_1h_candle"] == "2026-06-16T10:00:00+00:00"
    assert Path(config.audit_output_path / "signal_dry_run_order_usdjpy.json").exists()


def test_write_run_snapshot_updates_status_file(tmp_path):
    config = SimpleNamespace(
        audit_output_path=tmp_path / "audit",
        price_scale_divisor=100,
        telegram_enabled=False,
    )
    runner = IGDemoBotRunner(
        config=config,
        session=SimpleNamespace(),
        client=SimpleNamespace(),
        env_file=".env.demo",
        strategy_path="contract.yaml",
        epic="CS.D.USDJPY.TODAY.IP",
        runtime_strategy_config="runtime.yaml",
    )
    runner.price_state.tick_count = 42
    result = BotRunResult(
        status="RUNNING",
        started_at="2026-06-18T00:00:00+00:00",
        run_id="run-abc",
    )

    path = runner._write_run_snapshot(result)

    assert path.exists()
    assert '"status": "RUNNING"' in path.read_text()
    assert '"run_id": "run-abc"' in path.read_text()
    assert '"tick_count": 42' in path.read_text()


def test_gbpusd_runner_uses_gbpusd_report_filenames(tmp_path):
    config = SimpleNamespace(
        audit_output_path=tmp_path / "audit",
        price_scale_divisor=None,
        telegram_enabled=False,
    )
    runner = IGDemoBotRunner(
        config=config,
        session=SimpleNamespace(),
        client=SimpleNamespace(),
        env_file=".env.demo",
        strategy_path="contract.yaml",
        epic="CS.D.GBPUSD.TODAY.IP",
        runtime_strategy_config="runtime.yaml",
    )
    result = BotRunResult(status="RUNNING", started_at="2026-06-18T00:00:00+00:00")

    snapshot = runner._write_run_snapshot(result)
    audit = runner._write_audit_event({"event": "TEST"})
    lifecycle = runner.lifecycle_writer.clear(reason="TEST")

    assert snapshot.name == "bot_run_gbpusd.json"
    assert audit.name == "bot_audit_events_gbpusd.jsonl"
    assert lifecycle.name == "trade_lifecycle_gbpusd.json"


def test_bot_label_uses_contract_market_before_epic_fallback():
    assert _bot_label("CS.D.GBPUSD.TODAY.IP", {"strategy": {"market": "GBPUSD"}}) == "GBPUSD"
    assert _bot_label("CS.D.GBPUSD.TODAY.IP") == "GBPUSD"


def test_bot_subscribes_to_chart_tick_stream_when_configured(tmp_path):
    class Streaming:
        def __init__(self):
            self.price_calls = []
            self.chart_calls = []

        def subscribe_price(self, epic, listener):
            self.price_calls.append((epic, listener))

        def subscribe_chart_ticks(self, epic, listener):
            self.chart_calls.append((epic, listener))

    config = SimpleNamespace(
        audit_output_path=tmp_path / "audit",
        price_scale_divisor=100,
        streaming_mode="CHART_TICK",
        telegram_enabled=False,
    )
    runner = IGDemoBotRunner(
        config=config,
        session=SimpleNamespace(),
        client=SimpleNamespace(),
        env_file=".env.demo",
        strategy_path="contract.yaml",
        epic="CS.D.USDJPY.TODAY.IP",
        runtime_strategy_config="runtime.yaml",
    )
    runner.market_rules = SimpleNamespace(pip_size=0.01)
    streaming = Streaming()

    runner._subscribe_price_stream(streaming)

    assert streaming.price_calls == []
    assert len(streaming.chart_calls) == 1
    assert streaming.chart_calls[0][0] == "CS.D.USDJPY.TODAY.IP"


def _runner_for_reconciliation(tmp_path, client):
    config = SimpleNamespace(
        audit_output_path=tmp_path / "audit",
        price_scale_divisor=100,
        streaming_mode="CHART_TICK",
        telegram_enabled=False,
    )
    runner = IGDemoBotRunner(
        config=config,
        session=SimpleNamespace(),
        client=client,
        env_file=".env.demo",
        strategy_path="contract.yaml",
        epic="CS.D.USDJPY.TODAY.IP",
        runtime_strategy_config="runtime.yaml",
    )
    runner.market_rules = SimpleNamespace(pip_size=0.01)
    runner.runtime_config = SimpleNamespace(model_dump=lambda: {
        "max_trade_duration_days": 1,
        "weekend_policy": {"enabled": False},
        "exit": {
            "move_stop_to_breakeven": {"enabled": False},
            "partial_take_profit": {"enabled": False},
            "runner": {"enabled": False, "trailing_stop": {"atr_multiplier": 1.5}},
        },
        "broker_execution_guardrails": {
            "trade_lifecycle": {"enabled": True},
            "intraday_mode": {"enabled": False},
            "overnight_funding": {"timezone": "Europe/London"},
        },
    })
    return runner


def test_reconciliation_recovers_single_open_broker_position(tmp_path):
    client = SimpleNamespace(get_open_positions=lambda: {"positions": [{
        "market": {"epic": "CS.D.USDJPY.TODAY.IP", "expiry": "DFB"},
        "position": {
            "dealId": "DEAL1",
            "dealReference": "REF1",
            "direction": "BUY",
            "dealSize": 4.13,
            "level": 16381.4,
            "stopLevel": 16363.4,
            "limitLevel": 16387.4,
            "currency": "GBP",
            "createdDateUTC": "2026-07-24T04:00:01.307",
        },
    }]})
    runner = _runner_for_reconciliation(tmp_path, client)

    runner._reconcile_lifecycle_state()

    assert runner.lifecycle_reconciled is True
    assert runner.lifecycle_manager.position.deal_id == "DEAL1"
    assert runner.lifecycle_manager.position.entry_price == 163.814
    assert runner.lifecycle_manager.position.current_stop == 163.634
    assert runner.lifecycle_manager.position.target_price == 163.874
    assert (tmp_path / "audit" / "trade_lifecycle_usdjpy.json").exists()


def test_reconciliation_clears_local_lifecycle_when_broker_has_no_position(tmp_path):
    client = SimpleNamespace(get_open_positions=lambda: {"positions": []})
    runner = _runner_for_reconciliation(tmp_path, client)
    lifecycle = tmp_path / "audit" / "trade_lifecycle_usdjpy.json"
    lifecycle.parent.mkdir(parents=True)
    lifecycle.write_text(json.dumps({"deal_id": "OLD", "remaining_size": 4.13}))

    runner._reconcile_lifecycle_state()

    assert runner.lifecycle_reconciled is True
    assert runner.lifecycle_manager is None
    snapshot = json.loads(lifecycle.read_text())
    assert snapshot["position"] is None
    assert snapshot["reason"] == "NO_OPEN_BROKER_POSITION"


def test_stale_open_trade_update_for_closed_position_is_not_notified(tmp_path):
    client = SimpleNamespace()
    runner = _runner_for_reconciliation(tmp_path, client)
    sends = []
    runner.telegram = SimpleNamespace(send=lambda text, *, category="system": sends.append((category, text)))
    manager = IGTradeLifecycleManager(config=runner.runtime_config.model_dump())
    manager.attach(ManagedPosition(
        deal_id="DEAL1",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=4.13,
        remaining_size=0,
        entry_price=163.814,
        initial_stop=163.634,
        current_stop=163.634,
        target_price=163.874,
        initial_risk=0.18,
        atr=0.0,
        opened_at=datetime(2026, 7, 24, 4, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    ))
    runner.lifecycle_manager = manager

    runner._on_trade_update("CONFIRMS", {
        "dealId": "DEAL1",
        "status": "OPEN",
        "direction": "BUY",
        "size": 4.13,
        "date": "2026-07-24T04:00:01.307",
    })

    assert sends == []
    rows = (tmp_path / "audit" / "bot_audit_events_usdjpy.jsonl").read_text()
    assert "TRADE_STREAM_UPDATE_SUPPRESSED" in rows


def test_lifecycle_close_is_skipped_when_broker_position_already_closed(tmp_path):
    client = SimpleNamespace(get_open_positions=lambda: {"positions": []})
    runner = _runner_for_reconciliation(tmp_path, client)
    sends = []
    runner.telegram = SimpleNamespace(send=lambda text, *, category="system": sends.append((category, text)))
    manager = IGTradeLifecycleManager(config=runner.runtime_config.model_dump())
    manager.attach(ManagedPosition(
        deal_id="DEAL1",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=4.13,
        remaining_size=4.13,
        entry_price=163.814,
        initial_stop=163.634,
        current_stop=163.634,
        target_price=163.874,
        initial_risk=0.18,
        atr=0.0,
        opened_at=datetime(2026, 7, 24, 4, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    ))
    manager.pending_action = LifecycleAction(
        "FULL_CLOSE", "INTRADAY_FUNDING_AVOIDANCE_CLOSE", "DEAL1", "REF1", size=4.13
    )
    executor_calls = []
    runner.lifecycle_manager = manager
    runner.lifecycle_executor = SimpleNamespace(
        execute=lambda action, position: executor_calls.append((action, position)) or {}
    )

    result = runner._process_lifecycle_action()

    assert result == {
        "skipped": True,
        "reason": "BROKER_POSITION_ALREADY_CLOSED",
        "action": "FULL_CLOSE",
    }
    assert executor_calls == []
    assert runner.lifecycle_manager is None
    assert runner.lifecycle_executor is None
    snapshot = json.loads((tmp_path / "audit" / "trade_lifecycle_usdjpy.json").read_text())
    assert snapshot["position"] is None
    assert snapshot["reason"] == "BROKER_POSITION_ALREADY_CLOSED"
    rows = (tmp_path / "audit" / "bot_audit_events_usdjpy.jsonl").read_text()
    assert "LIFECYCLE_ACTION_SKIPPED" in rows
    assert sends[0][0] == "trade"


def test_lifecycle_close_preflight_failure_backs_off_without_close_attempt(tmp_path):
    def get_open_positions():
        raise RuntimeError("temporary broker read failure")

    client = SimpleNamespace(get_open_positions=get_open_positions)
    runner = _runner_for_reconciliation(tmp_path, client)
    runner.telegram = SimpleNamespace(send=lambda *_args, **_kwargs: None)
    manager = IGTradeLifecycleManager(config=runner.runtime_config.model_dump())
    manager.attach(ManagedPosition(
        deal_id="DEAL1",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=4.13,
        remaining_size=4.13,
        entry_price=163.814,
        initial_stop=163.634,
        current_stop=163.634,
        target_price=163.874,
        initial_risk=0.18,
        atr=0.0,
        opened_at=datetime(2026, 7, 24, 4, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    ))
    manager.pending_action = LifecycleAction(
        "FULL_CLOSE", "INTRADAY_FUNDING_AVOIDANCE_CLOSE", "DEAL1", "REF1", size=4.13
    )
    executor_calls = []
    runner.lifecycle_manager = manager
    runner.lifecycle_executor = SimpleNamespace(
        execute=lambda action, position: executor_calls.append((action, position)) or {"dealReference": "REF2"}
    )

    result = runner._process_lifecycle_action()

    assert result == {
        "skipped": True,
        "reason": "LIFECYCLE_POSITION_PREFLIGHT_FAILED",
        "action": "FULL_CLOSE",
    }
    assert executor_calls == []
    rows = (tmp_path / "audit" / "bot_audit_events_usdjpy.jsonl").read_text()
    assert "LIFECYCLE_POSITION_PREFLIGHT_FAILED" in rows
    assert "LIFECYCLE_ACTION_SUBMITTED" not in rows


def test_trade_update_deal_id_origin_closes_managed_position(tmp_path):
    client = SimpleNamespace()
    runner = _runner_for_reconciliation(tmp_path, client)
    runner.telegram = SimpleNamespace(send=lambda *_args, **_kwargs: None)
    manager = IGTradeLifecycleManager(config=runner.runtime_config.model_dump())
    manager.attach(ManagedPosition(
        deal_id="OPEN_DEAL",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=4.13,
        remaining_size=4.13,
        entry_price=163.814,
        initial_stop=163.634,
        current_stop=163.634,
        target_price=163.874,
        initial_risk=0.18,
        atr=0.0,
        opened_at=datetime(2026, 7, 24, 4, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    ))
    runner.lifecycle_manager = manager

    runner._on_trade_update("OPU", {
        "dealId": "CLOSING_DEAL",
        "dealIdOrigin": "OPEN_DEAL",
        "status": "DELETED",
        "direction": "SELL",
        "size": 0,
    })

    assert manager.position.remaining_size == 0


def test_lifecycle_failure_enters_cooldown_without_repeated_broker_calls(tmp_path):
    broker_reads = []

    def get_open_positions():
        broker_reads.append("read")
        return {"positions": [{
            "position": {"dealId": "DEAL1", "dealSize": 4.13},
            "market": {"epic": "CS.D.USDJPY.TODAY.IP"},
        }]}

    client = SimpleNamespace(get_open_positions=get_open_positions)
    runner = _runner_for_reconciliation(tmp_path, client)
    runner.telegram = SimpleNamespace(send=lambda *_args, **_kwargs: None)
    manager = IGTradeLifecycleManager(config=runner.runtime_config.model_dump())
    manager.attach(ManagedPosition(
        deal_id="DEAL1",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=4.13,
        remaining_size=4.13,
        entry_price=163.814,
        initial_stop=163.634,
        current_stop=163.634,
        target_price=163.874,
        initial_risk=0.18,
        atr=0.0,
        opened_at=datetime(2026, 7, 24, 4, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    ))
    runner.lifecycle_manager = manager
    runner.lifecycle_executor = SimpleNamespace(
        execute=lambda _action, _position: (_ for _ in ()).throw(RuntimeError("IG rejected"))
    )

    manager.pending_action = LifecycleAction("FULL_CLOSE", "cutoff", "DEAL1", "REF1", size=4.13)
    first = runner._process_lifecycle_action()
    manager.pending_action = LifecycleAction("FULL_CLOSE", "cutoff", "DEAL1", "REF1", size=4.13)
    second = runner._process_lifecycle_action()

    assert first == {"error": "IG rejected", "action": "FULL_CLOSE"}
    assert second["reason"] == "LIFECYCLE_ACTION_COOLDOWN"
    assert broker_reads == ["read"]


def test_partial_close_skips_when_broker_size_is_already_below_requested_size(tmp_path):
    client = SimpleNamespace(get_open_positions=lambda: {"positions": [{
        "position": {"dealId": "DEAL1", "dealSize": 2.0},
        "market": {"epic": "CS.D.USDJPY.TODAY.IP"},
    }]})
    runner = _runner_for_reconciliation(tmp_path, client)
    runner.telegram = SimpleNamespace(send=lambda *_args, **_kwargs: None)
    manager = IGTradeLifecycleManager(config=runner.runtime_config.model_dump())
    manager.attach(ManagedPosition(
        deal_id="DEAL1",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=4.13,
        remaining_size=4.13,
        entry_price=163.814,
        initial_stop=163.634,
        current_stop=163.634,
        target_price=163.874,
        initial_risk=0.18,
        atr=0.0,
        opened_at=datetime(2026, 7, 24, 4, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    ))
    manager.pending_action = LifecycleAction("PARTIAL_CLOSE", "partial_take_profit", "DEAL1", "REF1", size=2.5)
    executor_calls = []
    runner.lifecycle_manager = manager
    runner.lifecycle_executor = SimpleNamespace(
        execute=lambda action, position: executor_calls.append((action, position)) or {}
    )

    result = runner._process_lifecycle_action()

    assert result["reason"] == "BROKER_SIZE_BELOW_PARTIAL_CLOSE_SIZE"
    assert executor_calls == []
    assert manager.position.remaining_size == 2.0
    assert manager.position.partial_close_applied is True


def test_lifecycle_action_skips_when_broker_position_size_is_zero(tmp_path):
    client = SimpleNamespace(get_open_positions=lambda: {"positions": [{
        "position": {"dealId": "DEAL1", "dealSize": 0},
        "market": {"epic": "CS.D.USDJPY.TODAY.IP"},
    }]})
    runner = _runner_for_reconciliation(tmp_path, client)
    runner.telegram = SimpleNamespace(send=lambda *_args, **_kwargs: None)
    manager = IGTradeLifecycleManager(config=runner.runtime_config.model_dump())
    manager.attach(ManagedPosition(
        deal_id="DEAL1",
        deal_reference="REF1",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=4.13,
        remaining_size=4.13,
        entry_price=163.814,
        initial_stop=163.634,
        current_stop=163.634,
        target_price=163.874,
        initial_risk=0.18,
        atr=0.0,
        opened_at=datetime(2026, 7, 24, 4, tzinfo=timezone.utc),
        currency="GBP",
        expiry="DFB",
    ))
    manager.pending_action = LifecycleAction("FULL_CLOSE", "cutoff", "DEAL1", "REF1", size=4.13)
    executor_calls = []
    runner.lifecycle_manager = manager
    runner.lifecycle_executor = SimpleNamespace(
        execute=lambda action, position: executor_calls.append((action, position)) or {}
    )

    result = runner._process_lifecycle_action()

    assert result["reason"] == "BROKER_POSITION_ALREADY_CLOSED"
    assert executor_calls == []
    assert runner.lifecycle_manager is None


def test_order_submission_blocks_if_order_epic_does_not_match_bot_epic(tmp_path):
    client = SimpleNamespace(create_demo_position=lambda _payload: (_ for _ in ()).throw(
        AssertionError("broker submission should not be called")
    ))
    runner = _runner_for_reconciliation(tmp_path, client)
    runner.epic = "CS.D.GBPUSD.TODAY.IP"
    runner.contract = {"strategy": {"market": "GBPUSD"}}
    runner.lifecycle_reconciled = True
    sends = []
    runner.telegram = SimpleNamespace(send=lambda text, *, category="system": sends.append((category, text)))
    order = DryRunOrder(
        deal_reference="dry-1234567890123456789012345",
        epic="CS.D.USDJPY.TODAY.IP",
        direction="BUY",
        size=0.1,
        order_type="MARKET",
        level=None,
        stop_distance=6,
        stop_level=1.2492,
        limit_distance=6,
        limit_level=1.25068,
        currency="GBP",
        force_open=True,
        guaranteed_stop=False,
        time_in_force="FILL_OR_KILL",
        expiry="-",
        validation_status="READY_FOR_DEMO_DRY_RUN",
    )
    result = {
        "status": "SIGNAL_READY_FOR_DEMO_DRY_RUN",
        "dry_run_order": {
            "payload": order.payload(),
            "validation_status": order.validation_status,
            "validation_errors": [],
            "validation_warnings": [],
        },
    }

    assert runner._maybe_execute(result, "PLACE_DEMO_ORDER") is None
    audit = (tmp_path / "audit" / "bot_audit_events_gbpusd.jsonl").read_text()
    assert "ORDER_EPIC_MISMATCH" in audit
    assert "CS.D.GBPUSD.TODAY.IP" in audit
    assert "CS.D.USDJPY.TODAY.IP" in audit
    assert "GBPUSD order blocked: epic mismatch" in sends[0][1]
