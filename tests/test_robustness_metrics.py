from src.robustness.parameter_space import ParameterVariant
from src.robustness.robustness_metrics import collect_variant_metrics


def _metrics(**overrides):
    return {
        "total_return_percent": 10, "profit_factor": 1.5, "average_r": 0.2,
        "max_drawdown_percent": 2, "worst_trade_r": -2, "total_trades": 60,
        "average_trade_duration": 24, "median_trade_duration": 12, **overrides,
    }


def test_variant_pass_and_fail_reasons():
    variant = ParameterVariant("x", "x", "baseline", {}, "", True)
    assert collect_variant_metrics(variant, _metrics())["pass_flag"]
    assert "NEGATIVE_RETURN" in collect_variant_metrics(
        variant, _metrics(total_return_percent=-1)
    )["fail_reason"]
    assert "WORST_TRADE_TOO_LARGE" in collect_variant_metrics(
        variant, _metrics(worst_trade_r=-3)
    )["fail_reason"]
