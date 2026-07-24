import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from src.broker.ig.ig_bot import (
    BotRunResult,
    IGDemoBotRunner,
    NewsCalendarRefreshGuard,
    active_session_windows,
    latest_closed_hour,
    within_run_duration,
    write_bot_audit_event,
)
from src.broker.ig.ig_candle_cache import CandleCachePaths
from src.broker.ig.ig_trade_lifecycle import IGTradeLifecycleManager, ManagedPosition


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
