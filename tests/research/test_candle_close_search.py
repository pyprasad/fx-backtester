from src.research.candle_close_search import apply_candidate, build_candidates


def test_build_candidates_uses_filesystem_safe_names():
    candidates = build_candidates(
        direction_modes=["long_only"],
        session_presets=["tokyo"],
        rsi_levels=[55],
        pullback_atrs=[0.8],
        fixed_take_profit_pips=[6.0],
    )

    assert len(candidates) == 1
    assert candidates[0].name == "long_only_tokyo_rsi55_pullback0_8_tp6_0_bodynone_atrnone_hoursall_hours"


def test_apply_candidate_sets_candle_close_timing_and_variant_controls(strategy_config):
    candidate = build_candidates(
        direction_modes=["long_only"],
        session_presets=["london_combined"],
        rsi_levels=[55],
        pullback_atrs=[1.0],
        fixed_take_profit_pips=[8.0],
    )[0]

    config = apply_candidate(strategy_config, candidate)

    assert config.execution["signal_timing_mode"] == "candle_close_timestamp"
    assert config.entry["long"]["enabled"] is True
    assert config.entry["short"]["enabled"] is False
    assert config.entry["long"]["rsi_cross_up_level"] == 55
    assert config.entry["short"]["rsi_cross_down_level"] == 55
    assert config.entry["long"]["max_pullback_atr"] == 1.0
    assert config.entry["short"]["max_pullback_atr"] == 1.0
    assert config.exit["fixed_take_profit"]["target_pips"] == 8.0
    assert [item["name"] for item in config.session_filter["entry_windows"]] == [
        "London morning",
        "London New York overlap",
    ]


def test_apply_candidate_sets_entry_quality_filters(strategy_config):
    candidate = build_candidates(
        direction_modes=["short_only"],
        session_presets=["overlap"],
        rsi_levels=[40],
        pullback_atrs=[1.0],
        fixed_take_profit_pips=[6.0],
        min_body_atrs=[0.2],
        min_atr_pips_values=[8.0],
        hour_presets={"overlap_utc": (13, 14, 15, 16)},
    )[0]

    config = apply_candidate(strategy_config, candidate)

    assert config.entry["quality_filters"] == {
        "enabled": True,
        "min_body_atr": 0.2,
        "min_atr_pips": 8.0,
        "allowed_signal_hours_utc": [13, 14, 15, 16],
    }
