from src.config.config_loader import (
    apply_data_quality_overrides,
    apply_strategy_overrides,
    load_data_quality_config,
    load_strategy_config,
)


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


def test_strategy_research_parameter_overrides():
    config = apply_strategy_overrides(
        load_strategy_config("config/strategy.usdjpy.fx_swing_trend_reclaim.yaml"),
        risk_per_trade_percent=0.5,
        atr_stop_multiplier=1.5,
        rsi_short_trigger=55,
        ema_mid=60,
        ema_slow=220,
        final_target_r=5.0,
        partial_take_profit_r=2.5,
        breakeven_after_r=1.5,
        trailing_atr_multiplier=1.8,
        enable_long=True,
        session_timezone="UTC",
        session_windows=[
            {"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
        ],
    )

    assert config.risk["risk_per_trade_percent"] == 0.5
    assert config.stop_loss["atr_multiplier"] == 1.5
    assert config.entry["short"]["rsi_cross_down_level"] == 55
    assert config.indicators["ema_mid"] == 60
    assert config.indicators["ema_slow"] == 220
    assert config.exit["runner"]["final_target_r"] == 5.0
    assert config.exit["partial_take_profit"]["at_r"] == 2.5
    assert config.exit["move_stop_to_breakeven"]["after_r"] == 1.5
    assert config.exit["runner"]["trailing_stop"]["atr_multiplier"] == 1.8
    assert config.entry["long"]["enabled"] is True
    assert config.session_filter["timezone"] == "UTC"
    assert config.session_filter["entry_windows"] == [
        {"name": "Tokyo", "start": "09:00", "end": "18:00", "timezone": "Asia/Tokyo"},
    ]
