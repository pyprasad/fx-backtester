from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from src.broker.ig.ig_bot import (
    IGDemoBotRunner,
    active_session_windows,
    latest_closed_hour,
    within_run_duration,
    write_bot_audit_event,
)
from src.broker.ig.ig_candle_cache import CandleCachePaths


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
