from src.broker_guardrails.broker_rules import rules_from_config
from src.broker_guardrails.distance_validator import price_distance_pips, validate_distances
from src.strategies.fx_swing_trend_reclaim import generate_signals


def test_usdjpy_pip_conversion_and_buy_sell_distances(strategy_config):
    settings = strategy_config.broker_execution_guardrails
    rules = rules_from_config(settings)
    assert price_distance_pips(160.25, 160.23) == 2
    settings["minimum_initial_risk"]["default_min_initial_risk_pips"] = 2
    for stop, target, accepted in (
        (160.23, 160.27, True), (160.235, 160.27, False),
        (160.27, 160.23, True), (160.265, 160.23, False),
        (160.23, 160.265, False), (160.27, 160.235, False),
    ):
        assert validate_distances(160.25, stop, target, settings, rules).accepted is accepted


def test_configured_minimum_initial_risk(strategy_config):
    settings = strategy_config.broker_execution_guardrails
    rules = rules_from_config(settings)
    settings["minimum_initial_risk"]["default_min_initial_risk_pips"] = 5
    result = validate_distances(160.25, 160.27, 160.23, settings, rules)
    assert "REJECT_BELOW_MIN_INITIAL_RISK_PIPS" in result.rejection_reasons


def test_tiny_risk_strategy_setup_is_rejected_before_execution(strategy_config):
    import polars as pl
    from datetime import datetime, timezone

    times = [datetime(2025, 1, 6, 9, tzinfo=timezone.utc), datetime(2025, 1, 6, 10, tzinfo=timezone.utc)]
    entry = pl.DataFrame({
        "timestamp": times, "timestamp_london": times, "symbol": ["USDJPY"] * 2,
        "mid_open": [150.1, 150.1], "mid_high": [150.001, 150.001],
        "mid_low": [149.9, 149.9], "mid_close": [150.0, 150.0], "spread_avg": [.001, .001],
        "ema_20": [150.0, 150.0], "ema_50": [150.1, 150.1], "rsi_14": [45.0, 40.0],
        "atr_14": [.001, .001], "atr_14_pips": [.1, .1],
    })
    trend = pl.DataFrame({"timestamp": times, "mid_close": [149.0, 149.0], "ema_200": [150.0, 150.0]})
    signals, rejected = generate_signals(entry, trend, strategy_config)
    assert not signals
    assert any(row["rejection_reason"] == "REJECT_BELOW_MIN_INITIAL_RISK_PIPS" for row in rejected)
