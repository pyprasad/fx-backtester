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
