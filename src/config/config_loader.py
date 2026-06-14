from pathlib import Path

import yaml

from .schemas import DataQualityConfig, StrategyConfig


def _load(path: str | Path) -> tuple[dict, Path]:
    path = Path(path).resolve()
    with path.open() as handle:
        data = yaml.safe_load(handle)
    if data.get("extends"):
        parent_path = (path.parent / data.pop("extends")).resolve()
        parent, _ = _load(parent_path)

        def merge(base: dict, override: dict) -> dict:
            result = dict(base)
            for key, value in override.items():
                result[key] = merge(result.get(key, {}), value) if isinstance(value, dict) else value
            return result

        data = merge(parent, data)
    return data, path.parent.parent


def load_data_quality_config(path: str | Path) -> DataQualityConfig:
    data, base_dir = _load(path)
    return DataQualityConfig(**data, base_dir=base_dir)


def load_strategy_config(path: str | Path) -> StrategyConfig:
    data, base_dir = _load(path)
    return StrategyConfig(**data, base_dir=base_dir)


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
) -> StrategyConfig:
    if normalised_tick_path:
        config.data["normalised_tick_path"] = normalised_tick_path
    if candle_path:
        config.data["candle_path"] = candle_path
    if report_output_path:
        config.reporting["output_path"] = report_output_path
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
