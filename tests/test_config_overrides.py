from types import SimpleNamespace

from src.config.config_loader import (
    apply_data_quality_overrides,
    apply_strategy_overrides,
    load_data_quality_config,
    load_strategy_config,
)
from src.main import strategy_config as cli_strategy_config


def test_external_data_and_output_overrides():
    data = apply_data_quality_overrides(
        load_data_quality_config("config/data_quality.usdjpy.yaml"),
        raw_tick_path="/external/ticks",
        file_pattern="usdjpy_ticks_202[2-5].csv",
        normalised_output_path="data/normalised_ticks/USDJPY_2022_2025.parquet",
    )
    strategy = apply_strategy_overrides(
        load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml"),
        normalised_tick_path="data/normalised_ticks/USDJPY_2022_2025.parquet",
        candle_path="data/candles/USDJPY_2022_2025",
    )
    assert data.input["raw_tick_path"] == "/external/ticks"
    assert data.input["file_pattern"] == "usdjpy_ticks_202[2-5].csv"
    assert strategy.data["candle_path"] == "data/candles/USDJPY_2022_2025"


def test_news_guard_env_overrides_are_optional(monkeypatch):
    for key in (
        "NEWS_GUARD_ENABLED",
        "NEWS_GUARD_CALENDAR_FILE",
        "NEWS_GUARD_BEFORE_MINUTES",
        "NEWS_GUARD_AFTER_MINUTES",
        "SIGNAL_TIMING_MODE",
    ):
        monkeypatch.delenv(key, raising=False)

    config = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")

    assert config.news_guard["enabled"] is False


def test_news_guard_env_overrides_strategy_config(monkeypatch):
    monkeypatch.setenv("NEWS_GUARD_ENABLED", "true")
    monkeypatch.setenv(
        "NEWS_GUARD_CALENDAR_FILE",
        "data/macro_calendar/usd_jpy_events_2022_2025_nasdaq.csv",
    )
    monkeypatch.setenv("NEWS_GUARD_BEFORE_MINUTES", "45")
    monkeypatch.setenv("NEWS_GUARD_AFTER_MINUTES", "30")

    config = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")

    assert config.news_guard["enabled"] is True
    assert (
        config.news_guard["calendar_file"]
        == "data/macro_calendar/usd_jpy_events_2022_2025_nasdaq.csv"
    )
    assert config.news_guard["before_minutes"] == 45
    assert config.news_guard["after_minutes"] == 30


def test_cli_news_guard_override_wins_after_env(monkeypatch):
    monkeypatch.setenv("NEWS_GUARD_ENABLED", "true")

    config = apply_strategy_overrides(
        load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml"),
        news_guard_enabled=False,
    )

    assert config.news_guard["enabled"] is False


def test_signal_timing_mode_overrides_strategy_config(monkeypatch):
    monkeypatch.setenv("SIGNAL_TIMING_MODE", "legacy_open_timestamp")
    config = load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")

    assert config.execution["signal_timing_mode"] == "legacy_open_timestamp"

    config = apply_strategy_overrides(config, signal_timing_mode="candle_close_timestamp")

    assert config.execution["signal_timing_mode"] == "candle_close_timestamp"


def test_cli_strategy_contract_config_preserves_intraday_contract_with_fixed_tp():
    args = SimpleNamespace(
        strategy_contract_config="config/strategies/usdjpy_fx_swing_trend_reclaim_v1_intraday_long_short_demo.yaml",
        normalised_tick_path="data/normalised_ticks/USDJPY_2021_2026.parquet",
        candle_path="data/candles/USDJPY_2021_2026_intraday_fixed_tp",
        report_output_path="reports/fixed_take_profit_research/intraday_tp_5_pips",
        fixed_take_profit_pips=5.0,
        fixed_take_profit_execution_mode="managed_market_close",
        news_guard_enabled=None,
        news_calendar_file=None,
        news_before_minutes=None,
        news_after_minutes=None,
        weekend_policy_name=None,
    )

    config = cli_strategy_config(args, "config/strategy.usdjpy.fx_swing_trend_reclaim.yaml")

    assert config.entry["short"]["enabled"] is True
    assert config.entry["long"]["enabled"] is True
    assert [item["name"] for item in config.session_filter["entry_windows"]] == [
        "Tokyo",
        "London morning",
        "London New York overlap",
    ]
    assert config.stop_loss["atr_multiplier"] == 1.5
    assert config.max_trade_duration_days == 1
    assert config.execution["default_slippage_points"] == 0.005
    assert config.broker_execution_guardrails["minimum_initial_risk"]["default_min_initial_risk_pips"] == 6.0
    assert config.broker_execution_guardrails["broker_distance_rules"]["min_take_profit_distance_pips"] == 6.0
    assert config.exit["fixed_take_profit"] == {
        "enabled": True,
        "target_pips": 5.0,
        "execution_mode": "managed_market_close",
        "disable_partial_take_profit": True,
        "disable_move_stop_to_breakeven": True,
        "disable_runner": True,
    }
