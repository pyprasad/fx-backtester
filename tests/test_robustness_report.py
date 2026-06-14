from src.robustness.robustness_report import write_robustness_report


def test_robustness_report(tmp_path):
    path = write_robustness_report(
        tmp_path, {"worst_observed_trade_r": -2, "normalised_tick_path": "ticks.parquet",
        "candle_path": "candles"}, {"robustness_score": 90, "verdict": "STRONG_ROBUSTNESS",
        "profitable_variant_percent": 90, "pass_variant_percent": 80}, {}, [], [], [],
        {"baseline_isolated_flag": False},
    )
    content = path.read_text()
    assert "Executive Summary" in content
    assert "not parameter optimisation" in content
