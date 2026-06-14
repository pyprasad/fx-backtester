from src.robustness.parameter_space import ParameterSpaceBuilder


def test_baseline_full_grid_disabled_and_duplicates_removed(strategy_config):
    variants = ParameterSpaceBuilder().build_all_variants(strategy_config)
    assert variants[0].variant_name == "baseline_original"
    assert not any(variant.test_type == "full_grid" for variant in variants)
    assert len({tuple(sorted(variant.parameter_overrides.items())) for variant in variants}) == len(variants)


def test_paired_variants_are_deterministic(strategy_config):
    variants = ParameterSpaceBuilder().build_paired_sensitivity_variants(strategy_config)
    ema = [variant for variant in variants if "ema_mid_vs_ema_slow" in variant.variant_name]
    assert len(ema) == 9
    assert all(" " not in variant.variant_name for variant in ema)
