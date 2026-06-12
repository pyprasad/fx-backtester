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
