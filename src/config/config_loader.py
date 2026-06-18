import os
from pathlib import Path

import yaml

from .schemas import DataQualityConfig, StrategyConfig


def _load(path: str | Path) -> tuple[dict, Path]:
    path = Path(path).resolve()
    with path.open() as handle:
        return yaml.safe_load(handle), path.parent.parent


def load_data_quality_config(path: str | Path) -> DataQualityConfig:
    data, base_dir = _load(path)
    return DataQualityConfig(**data, base_dir=base_dir)


def load_strategy_config(path: str | Path) -> StrategyConfig:
    data, base_dir = _load(path)
    config = StrategyConfig(**data, base_dir=base_dir)
    return apply_news_guard_env_overrides(config)


def _env_bool(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y", "on"}:
        return True
    if lowered in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def apply_news_guard_env_overrides(config: StrategyConfig) -> StrategyConfig:
    enabled = _env_bool("NEWS_GUARD_ENABLED")
    if enabled is not None:
        config.news_guard["enabled"] = enabled

    calendar_file = os.environ.get("NEWS_GUARD_CALENDAR_FILE")
    if calendar_file:
        config.news_guard["calendar_file"] = calendar_file

    before_minutes = _env_int("NEWS_GUARD_BEFORE_MINUTES")
    if before_minutes is not None:
        config.news_guard["before_minutes"] = before_minutes

    after_minutes = _env_int("NEWS_GUARD_AFTER_MINUTES")
    if after_minutes is not None:
        config.news_guard["after_minutes"] = after_minutes

    return config


def resolve(config: DataQualityConfig | StrategyConfig, path: str) -> Path:
    return (config.base_dir / path).resolve()


def apply_data_quality_overrides(
    config: DataQualityConfig,
    *,
    raw_tick_path: str | None = None,
    file_pattern: str | None = None,
    normalised_output_path: str | None = None,
    quality_report_path: str | None = None,
    quality_summary_path: str | None = None,
) -> DataQualityConfig:
    if raw_tick_path:
        config.input["raw_tick_path"] = raw_tick_path
    if file_pattern:
        config.input["file_pattern"] = file_pattern
    if normalised_output_path:
        config.input["normalised_output_path"] = normalised_output_path
    if quality_report_path:
        config.output["report_path"] = quality_report_path
    if quality_summary_path:
        config.output["summary_csv_path"] = quality_summary_path
    return config


def apply_strategy_overrides(
    config: StrategyConfig,
    *,
    normalised_tick_path: str | None = None,
    candle_path: str | None = None,
    report_output_path: str | None = None,
    news_guard_enabled: bool | None = None,
    news_calendar_file: str | None = None,
    news_before_minutes: int | None = None,
    news_after_minutes: int | None = None,
    risk_per_trade_percent: float | None = None,
    atr_stop_multiplier: float | None = None,
    rsi_short_trigger: float | None = None,
    ema_mid: int | None = None,
    ema_slow: int | None = None,
    final_target_r: float | None = None,
    partial_take_profit_r: float | None = None,
    breakeven_after_r: float | None = None,
    trailing_atr_multiplier: float | None = None,
    enable_long: bool | None = None,
    session_timezone: str | None = None,
    session_windows: list[dict] | None = None,
) -> StrategyConfig:
    if normalised_tick_path:
        config.data["normalised_tick_path"] = normalised_tick_path
    if candle_path:
        config.data["candle_path"] = candle_path
    if report_output_path:
        config.reporting["output_path"] = report_output_path
    if news_guard_enabled is not None:
        config.news_guard["enabled"] = news_guard_enabled
    if news_calendar_file:
        config.news_guard["calendar_file"] = news_calendar_file
    if news_before_minutes is not None:
        config.news_guard["before_minutes"] = news_before_minutes
    if news_after_minutes is not None:
        config.news_guard["after_minutes"] = news_after_minutes
    if risk_per_trade_percent is not None:
        config.risk["risk_per_trade_percent"] = risk_per_trade_percent
    if atr_stop_multiplier is not None:
        config.stop_loss["atr_multiplier"] = atr_stop_multiplier
    if rsi_short_trigger is not None:
        config.entry["short"]["rsi_cross_down_level"] = rsi_short_trigger
    if ema_mid is not None:
        config.indicators["ema_mid"] = ema_mid
    if ema_slow is not None:
        config.indicators["ema_slow"] = ema_slow
    if final_target_r is not None:
        config.exit["runner"]["final_target_r"] = final_target_r
    if partial_take_profit_r is not None:
        config.exit["partial_take_profit"]["at_r"] = partial_take_profit_r
    if breakeven_after_r is not None:
        config.exit["move_stop_to_breakeven"]["after_r"] = breakeven_after_r
    if trailing_atr_multiplier is not None:
        config.exit["runner"]["trailing_stop"]["atr_multiplier"] = trailing_atr_multiplier
    if enable_long is not None:
        config.entry["long"]["enabled"] = enable_long
    if session_timezone is not None:
        config.session_filter["timezone"] = session_timezone
    if session_windows:
        config.session_filter["entry_windows"] = session_windows
    return config


def apply_weekend_policy_variant(
    config: StrategyConfig, variant_name: str, variants_path: str | Path
) -> StrategyConfig:
    variants = yaml.safe_load(Path(variants_path).read_text())["variants"]
    variant = next((item for item in variants if item["name"] == variant_name), None)
    if variant is None:
        raise ValueError(f"Unknown weekend policy variant: {variant_name}")

    def merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for key, value in override.items():
            result[key] = merge(result.get(key, {}), value) if isinstance(value, dict) else value
        return result

    config.weekend_policy = merge(config.weekend_policy, variant["weekend_policy"])
    config.weekend_policy["policy_name"] = variant_name
    return config
