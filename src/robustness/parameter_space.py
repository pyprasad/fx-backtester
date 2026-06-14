from dataclasses import dataclass
from itertools import product
import re


@dataclass(frozen=True)
class ParameterVariant:
    variant_id: str
    variant_name: str
    test_type: str
    parameter_overrides: dict
    description: str
    is_baseline: bool = False


def _settings(config) -> dict:
    return config if isinstance(config, dict) and "baseline_parameters" in config else config.parameter_robustness


def _safe(value) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value)).strip("_").lower().replace(".", "_")


class ParameterSpaceBuilder:
    def build_baseline_variant(self, config) -> ParameterVariant:
        return ParameterVariant(
            "baseline_original", "baseline_original", "baseline",
            dict(_settings(config)["baseline_parameters"]),
            "Current approved baseline reference.", True,
        )

    def build_one_factor_variants(self, config) -> list[ParameterVariant]:
        settings = _settings(config)
        baseline = settings["baseline_parameters"]
        variants = []
        for parameter, values in settings.get("parameter_grid", {}).items():
            for value in values:
                if value == baseline.get(parameter):
                    continue
                name = f"ofat_{_safe(parameter)}_{_safe(value)}"
                variants.append(ParameterVariant(name, name, "one_factor_at_a_time", {parameter: value},
                                                 f"One-factor sensitivity for {parameter}={value}."))
        return variants

    def build_paired_sensitivity_variants(self, config) -> list[ParameterVariant]:
        variants = []
        baseline = _settings(config)["baseline_parameters"]
        for pair in _settings(config).get("paired_sensitivity_tests", []):
            parameters = list(pair["parameters"])
            x, y = parameters
            for x_value, y_value in product(pair["parameters"][x], pair["parameters"][y]):
                overrides = {x: x_value, y: y_value}
                is_baseline = all(baseline.get(key) == value for key, value in overrides.items())
                name = f"paired_{_safe(pair['name'])}_{_safe(x_value)}_{_safe(y_value)}"
                variants.append(ParameterVariant(name, name, "paired_sensitivity", overrides,
                                                 f"Paired sensitivity: {pair['name']}.", is_baseline))
        return variants

    def build_local_neighbourhood_variants(self, config) -> list[ParameterVariant]:
        baseline = _settings(config)["baseline_parameters"]
        return [
            ParameterVariant(
                _safe(item["name"]), _safe(item["name"]), "local_neighbourhood",
                dict(item["overrides"]), "Broad nearby parameter shift.",
                item["overrides"] == baseline or item["name"] == "baseline_original",
            )
            for item in _settings(config).get("local_neighbourhood_tests", [])
        ]

    def build_all_variants(self, config) -> list[ParameterVariant]:
        settings = _settings(config)
        variants = [self.build_baseline_variant(config)]
        if settings.get("test_modes", {}).get("one_factor_at_a_time", {}).get("enabled", True):
            variants += self.build_one_factor_variants(config)
        if settings.get("test_modes", {}).get("paired_sensitivity", {}).get("enabled", True):
            variants += self.build_paired_sensitivity_variants(config)
        if settings.get("test_modes", {}).get("local_neighbourhood", {}).get("enabled", True):
            variants += self.build_local_neighbourhood_variants(config)
        if settings.get("test_modes", {}).get("full_grid", {}).get("enabled", False):
            keys = list(settings["parameter_grid"])
            for values in product(*(settings["parameter_grid"][key] for key in keys)):
                overrides = dict(zip(keys, values))
                name = "full_grid_" + "_".join(f"{_safe(k)}_{_safe(v)}" for k, v in overrides.items())
                variants.append(ParameterVariant(name, name, "full_grid", overrides, "Explicit full grid."))
        valid = self.validate_variants(variants)
        baseline = settings["baseline_parameters"]
        unique, seen = [], set()
        for variant in valid:
            effective = tuple(sorted({**baseline, **variant.parameter_overrides}.items()))
            if effective in seen:
                continue
            seen.add(effective)
            unique.append(variant)
        return unique

    def validate_variants(self, variants: list[ParameterVariant]) -> list[ParameterVariant]:
        unique, seen = [], set()
        for variant in variants:
            key = tuple(sorted(variant.parameter_overrides.items()))
            if key in seen:
                continue
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", variant.variant_name):
                raise ValueError(f"Variant name is not filesystem-safe: {variant.variant_name}")
            seen.add(key)
            unique.append(variant)
        return unique
