import json
from copy import deepcopy
from pathlib import Path

import yaml

from src.backtest.backtest_engine import run_backtest
from src.config.config_loader import apply_weekend_policy_variant

from .robustness_metrics import collect_variant_metrics


PARAMETER_PATHS = {
    "ema_fast": ("indicators", "ema_fast"),
    "ema_mid": ("indicators", "ema_mid"),
    "ema_slow": ("indicators", "ema_slow"),
    "rsi_period": ("indicators", "rsi_period"),
    "atr_period": ("indicators", "atr_period"),
    "rsi_short_trigger": ("entry", "short", "rsi_cross_down_level"),
    "atr_stop_multiplier": ("stop_loss", "atr_multiplier"),
    "trailing_atr_multiplier": ("exit", "runner", "trailing_stop", "atr_multiplier"),
    "partial_take_profit_r": ("exit", "partial_take_profit", "at_r"),
    "final_target_r": ("exit", "runner", "final_target_r"),
    "breakeven_after_r": ("exit", "move_stop_to_breakeven", "after_r"),
    "max_trade_duration_days": ("max_trade_duration_days",),
    "pullback_atr_limit": ("entry", "short", "max_pullback_atr"),
}


def apply_parameter_overrides(config, overrides: dict):
    result = deepcopy(config)
    for parameter, value in overrides.items():
        path = PARAMETER_PATHS.get(parameter)
        if path is None:
            raise ValueError(f"Unsupported robustness parameter: {parameter}")
        target = result
        for key in path[:-1]:
            target = getattr(target, key) if not isinstance(target, dict) else target[key]
        if isinstance(target, dict):
            target[path[-1]] = value
        else:
            setattr(target, path[-1], value)
    return result


class VariantBacktestRunner:
    def __init__(self, base_config, output: Path, variants_config_path="config/weekend_policy_variants.usdjpy.yaml"):
        self.base_config = base_config
        self.output = Path(output)
        self.variants_config_path = variants_config_path

    def run(self, variant) -> dict:
        folder = self.output / "variants" / variant.variant_name
        folder.mkdir(parents=True, exist_ok=True)
        metadata = {
            "variant_id": variant.variant_id, "variant_name": variant.variant_name,
            "test_type": variant.test_type, "parameter_overrides": variant.parameter_overrides,
            "is_baseline": variant.is_baseline, "run_status": "RUNNING", "error_message": "",
            "report_path": str(folder / "html_report.html"),
        }
        try:
            config = apply_parameter_overrides(self.base_config, variant.parameter_overrides)
            config = apply_weekend_policy_variant(config, "force_close_friday_20_30", self.variants_config_path)
            snapshot = config.model_dump(exclude={"base_dir"}, mode="json")
            (folder / "variant_config_snapshot.yaml").write_text(yaml.safe_dump(snapshot, sort_keys=False))
            _, metrics, _ = run_backtest(config, output_override=folder)
            metadata["run_status"] = "SUCCESS"
            row = collect_variant_metrics(variant, metrics)
        except Exception as exc:
            metadata["run_status"], metadata["error_message"] = "ERROR", str(exc)
            row = collect_variant_metrics(variant, None, "ERROR", str(exc))
        (folder / "variant_metadata.json").write_text(json.dumps(metadata, indent=2))
        return row
