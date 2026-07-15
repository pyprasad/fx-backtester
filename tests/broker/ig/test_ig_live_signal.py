from datetime import datetime, timezone

import json

from src.broker.ig.ig_live_signal import (
    _executable_target_from_tick,
    prices_to_candles,
    runtime_config_from_contract,
    write_signal_dry_run_report,
)
from src.broker.ig.models import InternalTick


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
    assert config.entry["short"]["enabled"] is True
    assert config.entry["long"]["enabled"] is False


def test_runtime_config_from_long_short_intraday_contract_enables_long_and_intraday():
    config, contract = runtime_config_from_contract(
        "config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_long_short_demo.yaml",
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml",
    )

    assert contract["strategy"]["direction_mode"] == "long_short"
    assert config.entry["short"]["enabled"] is True
    assert config.entry["long"]["enabled"] is True
    assert config.risk["risk_per_trade_percent"] == 0.25
    assert config.stop_loss["atr_multiplier"] == 1.5
    assert config.max_trade_duration_days == 1
    assert config.execution["default_slippage_points"] == 0.005
    assert config.broker_execution_guardrails["intraday_mode"]["enabled"] is True
    assert config.broker_execution_guardrails["swing_mode"]["allow_overnight_holding"] is False
    assert contract["broker_guardrails"]["selected_guardrail_candidate"] == "intraday_long_short_ig_realistic_risk025_ig6"
    assert config.broker_execution_guardrails["minimum_initial_risk"]["default_min_initial_risk_pips"] == 6.0
    assert config.broker_execution_guardrails["broker_distance_rules"]["min_stop_distance_pips"] == 6.0
    assert config.broker_execution_guardrails["broker_distance_rules"]["min_take_profit_distance_pips"] == 6.0
    assert config.broker_execution_guardrails["trade_lifecycle"]["stop_amend_skip_log_interval_seconds"] == 60
    assert config.news_guard["enabled"] is True
    assert config.news_guard["calendar_file"] == "data/macro_calendar/usd_jpy_events_live_nasdaq.csv"


def test_runtime_config_from_six_pip_demo_contract_enables_fixed_attached_take_profit():
    config, contract = runtime_config_from_contract(
        "config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_6pip_attached_demo.yaml",
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml",
    )

    assert contract["strategy"]["direction_mode"] == "long_short"
    assert contract["risk_management"]["fixed_take_profit_pips"] == 6.0
    assert config.entry["short"]["enabled"] is True
    assert config.entry["long"]["enabled"] is True
    assert config.exit["fixed_take_profit"] == {
        "enabled": True,
        "target_pips": 6.0,
        "execution_mode": "attached_limit",
        "disable_partial_take_profit": True,
        "disable_move_stop_to_breakeven": True,
        "disable_runner": True,
    }
    assert config.exit["partial_take_profit"]["enabled"] is False
    assert config.exit["move_stop_to_breakeven"]["enabled"] is False
    assert config.exit["runner"]["enabled"] is False
    assert config.broker_execution_guardrails["broker_distance_rules"]["min_stop_distance_pips"] == 6.0
    assert config.broker_execution_guardrails["broker_distance_rules"]["min_take_profit_distance_pips"] == 6.0
    assert config.broker_execution_guardrails["minimum_initial_risk"]["default_min_initial_risk_pips"] == 6.0
    assert config.news_guard["enabled"] is True


def test_runtime_config_from_final_contract_accepts_london_session_contract_shape():
    config, contract = runtime_config_from_contract(
        "config/strategies/usdjpy_fx_swing_trend_reclaim_v1_final.yaml",
        "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml",
    )

    assert contract["broker_guardrails"]["selected_guardrail_candidate"] == "min_risk_3pips"
    assert [item["name"] for item in config.session_filter["entry_windows"]] == [
        "London morning",
        "London New York overlap",
    ]
    assert all(item["timezone"] == "Europe/London" for item in config.session_filter["entry_windows"])
    assert config.weekend_policy["enabled"] is True
    assert config.weekend_policy["policy_name"] == "force_close_friday_20_30"
    assert config.weekend_policy["force_close_on_friday"]["enabled"] is True
    assert config.weekend_policy["force_close_on_friday"]["close_time_utc"] == "20:30"
    assert config.risk["max_open_trades_total"] == 1
    assert config.execution["default_slippage_points"] == 0.002


def test_executable_target_uses_current_tick_entry_risk_like_backtest():
    signal = type("SignalStub", (), {
        "direction": "SHORT",
        "proposed_stop": 160.30,
        "proposed_target": 159.00,
    })()
    tick = InternalTick(
        datetime(2026, 6, 15, 8, tzinfo=timezone.utc),
        bid=160.10,
        ask=160.11,
        mid=160.105,
        spread_pips=1,
        source="test",
        epic="USDJPY",
        delayed=False,
    )
    contract = {"risk_management": {"final_target_r": 4.0}}

    assert round(_executable_target_from_tick(signal, tick, contract), 6) == 159.30


def test_executable_target_uses_ask_entry_risk_for_long():
    signal = type("SignalStub", (), {
        "direction": "LONG",
        "proposed_stop": 159.90,
        "proposed_target": 161.00,
    })()
    tick = InternalTick(
        datetime(2026, 6, 15, 8, tzinfo=timezone.utc),
        bid=160.10,
        ask=160.11,
        mid=160.105,
        spread_pips=1,
        source="test",
        epic="USDJPY",
        delayed=False,
    )
    contract = {"risk_management": {"final_target_r": 4.0}}

    assert round(_executable_target_from_tick(signal, tick, contract), 6) == 160.95


def test_executable_target_uses_fixed_six_pip_target_for_short_and_long():
    tick = InternalTick(
        datetime(2026, 6, 15, 8, tzinfo=timezone.utc),
        bid=160.10,
        ask=160.11,
        mid=160.105,
        spread_pips=1,
        source="test",
        epic="USDJPY",
        delayed=False,
    )
    contract = {
        "strategy": {"pip_size": 0.01},
        "risk_management": {"fixed_take_profit_pips": 6.0, "final_target_r": 4.0},
    }
    short_signal = type("SignalStub", (), {
        "direction": "SHORT",
        "proposed_stop": 160.30,
        "proposed_target": 159.00,
    })()
    long_signal = type("SignalStub", (), {
        "direction": "LONG",
        "proposed_stop": 159.90,
        "proposed_target": 161.00,
    })()

    assert round(_executable_target_from_tick(short_signal, tick, contract), 6) == 160.04
    assert round(_executable_target_from_tick(long_signal, tick, contract), 6) == 160.17


def test_write_signal_dry_run_report_never_marks_order_sent(tmp_path):
    report = write_signal_dry_run_report(tmp_path, {
        "status": "SIGNAL_READY_FOR_DEMO_DRY_RUN",
        "epic": "CS.D.USDJPY.TODAY.IP",
        "latest_closed_1h_candle": "2026-06-16T08:00:00+00:00",
        "signal_count": 3,
        "rejection_count": 5,
        "current_signal": {"direction": "SHORT"},
        "dry_run_order": {"validation_status": "READY_FOR_DEMO_DRY_RUN"},
        "order_sent": False,
    })

    payload = json.loads(report.read_text())
    assert report.name == "signal_dry_run_order_usdjpy.json"
    assert payload["status"] == "SIGNAL_READY_FOR_DEMO_DRY_RUN"
    assert payload["signal_count"] == 3
    assert payload["rejection_count"] == 5
    assert payload["dry_run_order"]["validation_status"] == "READY_FOR_DEMO_DRY_RUN"
    assert payload["order_sent"] is False
