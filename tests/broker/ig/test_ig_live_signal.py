from datetime import datetime, timezone

import json

from src.broker.ig.ig_live_signal import (
    prices_to_candles,
    runtime_config_from_contract,
    write_signal_dry_run_report,
)


def test_prices_to_candles_scales_ig_historical_prices():
    frame = prices_to_candles({
        "prices": [{
            "snapshotTimeUTC": "2026-06-16T08:00:00",
            "openPrice": {"bid": 16022.8, "ask": 16023.8},
            "closePrice": {"bid": 16031.2, "ask": 16032.2},
            "highPrice": {"bid": 16032.3, "ask": 16033.3},
            "lowPrice": {"bid": 16022.2, "ask": 16023.2},
            "lastTradedVolume": 2231,
        }],
    }, scale_divisor=100)

    row = frame.row(0, named=True)
    assert row["timestamp"] == datetime(2026, 6, 16, 8, tzinfo=timezone.utc)
    assert row["bid_close"] == 160.312
    assert row["ask_close"] == 160.322
    assert row["mid_close"] == 160.317
    assert round(row["spread_avg"], 6) == 0.01


def test_prices_to_candles_converts_snapshot_time_from_london_when_utc_missing():
    frame = prices_to_candles({
        "prices": [{
            "snapshotTime": "2026/06/16 10:00:00",
            "openPrice": {"bid": 16022.8, "ask": 16023.8},
            "closePrice": {"bid": 16031.2, "ask": 16032.2},
            "highPrice": {"bid": 16032.3, "ask": 16033.3},
            "lowPrice": {"bid": 16022.2, "ask": 16023.2},
        }],
    }, scale_divisor=100)

    assert frame.row(0, named=True)["timestamp"] == datetime(2026, 6, 16, 9, tzinfo=timezone.utc)


def test_prices_to_candles_skips_partial_bid_ask_candles():
    frame = prices_to_candles({
        "prices": [
            {
                "snapshotTimeUTC": "2026-06-16T08:00:00",
                "openPrice": {"bid": 16022.8, "ask": 16023.8},
                "closePrice": {"bid": 16031.2, "ask": None},
                "highPrice": {"bid": 16032.3, "ask": 16033.3},
                "lowPrice": {"bid": 16022.2, "ask": 16023.2},
            },
            {
                "snapshotTimeUTC": "2026-06-16T09:00:00",
                "openPrice": {"bid": 16042.8, "ask": 16043.8},
                "closePrice": {"bid": 16051.2, "ask": 16052.2},
                "highPrice": {"bid": 16052.3, "ask": 16053.3},
                "lowPrice": {"bid": 16042.2, "ask": 16043.2},
            },
        ],
    }, scale_divisor=100)

    assert frame.height == 1
    assert frame.row(0, named=True)["timestamp"] == datetime(2026, 6, 16, 9, tzinfo=timezone.utc)
    assert frame.row(0, named=True)["mid_close"] == 160.517


def test_runtime_config_from_strict_contract_applies_combined_sessions_and_spread_guardrail():
    config, contract = runtime_config_from_contract(
        "config/strategies/usdjpy_fx_swing_trend_reclaim_v1_strict_combined_demo.yaml",
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml",
    )

    assert contract["broker_guardrails"]["selected_guardrail_candidate"] == "min_risk_3pips_spread_ratio_20pct"
    assert config.session_filter["entry_windows"][-1]["name"] == "Tokyo"
    assert config.broker_execution_guardrails["spread_to_risk_filter"]["enabled"] is True
    assert config.broker_execution_guardrails["spread_to_risk_filter"]["default_max_spread_to_initial_risk_ratio"] == 0.20


def test_write_signal_dry_run_report_never_marks_order_sent(tmp_path):
    report = write_signal_dry_run_report(tmp_path, {
        "status": "SIGNAL_READY_FOR_DEMO_DRY_RUN",
        "epic": "CS.D.USDJPY.TODAY.IP",
        "latest_closed_1h_candle": "2026-06-16T08:00:00+00:00",
        "current_signal": {"direction": "SHORT"},
        "dry_run_order": {"validation_status": "READY_FOR_DEMO_DRY_RUN"},
        "order_sent": False,
    })

    payload = json.loads(report.read_text())
    assert report.name == "signal_dry_run_order_usdjpy.json"
    assert payload["status"] == "SIGNAL_READY_FOR_DEMO_DRY_RUN"
    assert payload["dry_run_order"]["validation_status"] == "READY_FOR_DEMO_DRY_RUN"
    assert payload["order_sent"] is False
